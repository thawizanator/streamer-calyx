import os
import sys
import time
import math
import struct
import json
from collections import deque
from datetime import datetime
import numpy as np

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QIODevice
from PyQt6.QtMultimedia import QMediaDevices, QAudioSource, QAudioFormat, QAudioDevice

try:
    from debug_logger import log_debug
except ImportError:
    def log_debug(tag, msg):
        print(f"[{tag}] {msg}")

try:
    from streamlabs_client import get_streamlabs_client
except ImportError:
    def get_streamlabs_client():
        return None


class AutoClipEngine(QObject):
    """
    Background engine for real-time audio peak reaction & hype moment detection.
    
    Features:
    - Continuous sampling of user-selected audio input (physical mic or VoiceMeeter VAIO).
    - 10-second rolling moving average baseline buffer.
    - 4-Zone level classification: Green (Normal), Yellow (Elevated), Orange (Possible Peak), Red (Full Peak).
    - Discord-style automatic sensitivity calibration floating above ambient baseline.
    - Sustained duration filter preventing mouse clicks or desk bumps from false-triggering.
    - 60-second cooldown timer preventing spam during a single loud moment.
    - Primary peak event dispatch: Twitch Stream Marker, audio chime, and monitor border alert.
    - Secondary peak event logging to cooldown_clips.txt with calculated 40/20 split (40s pre-context / 20s aftermath).
    - Optional orange 'Possible Moments' logging.
    - Scene scoping filtering: monitoring pauses on non-whitelisted scenes (e.g., BRB).
    """

    # Signals for UI & System Integration
    level_updated = pyqtSignal(float, int, float, float)  # (current_level, zone 1-4, baseline, threshold)
    dsp_telemetry_updated = pyqtSignal(dict)              # Live prosody DSP telemetry (F0, laughter, VAD, thump)
    marker_triggered = pyqtSignal(dict)                   # Primary peak event payload
    secondary_peak_logged = pyqtSignal(dict)              # Secondary peak during cooldown
    possible_peak_logged = pyqtSignal(dict)               # Orange possible peak event
    cooldown_tick = pyqtSignal(int)                       # Remaining cooldown seconds (0 when idle)
    status_changed = pyqtSignal(str, bool)                # (status_message, is_active)

    ZONE_GREEN = 1
    ZONE_YELLOW = 2
    ZONE_ORANGE = 3
    ZONE_RED = 4

    VOICE_PROFILES = {
        "dynamic": {"label": "Dynamic Auto-Adapt", "f0_base": 165.0, "adapt": True},
        "deep": {"label": "Deep Voice (85-150 Hz)", "f0_base": 115.0, "adapt": False},
        "mid": {"label": "Mid / Conversational (140-210 Hz)", "f0_base": 170.0, "adapt": False},
        "high": {"label": "High / Expressive (190-320 Hz)", "f0_base": 235.0, "adapt": False},
    }

    GENRE_PRESETS = {
        "default": {"label": "Default Balanced", "trigger_offset": 0.30, "min_duration_ms": 250, "desk_thump_sensitivity": 0.55,
                    "w_vol": 0.40, "w_vad": 0.25, "w_pitch": 0.20, "w_laugh": 0.15},
        "horror": {"label": "😱 Horror (Fast Jump-Scare)", "trigger_offset": 0.24, "min_duration_ms": 140, "desk_thump_sensitivity": 0.45,
                   "w_vol": 0.35, "w_vad": 0.15, "w_pitch": 0.40, "w_laugh": 0.10},
        "comedy": {"label": "😂 Comedy (Laugh Cadence)", "trigger_offset": 0.26, "min_duration_ms": 280, "desk_thump_sensitivity": 0.65,
                   "w_vol": 0.25, "w_vad": 0.20, "w_pitch": 0.15, "w_laugh": 0.40},
        "fps": {"label": "📢 FPS Shout (Anti-Thump)", "trigger_offset": 0.34, "min_duration_ms": 220, "desk_thump_sensitivity": 0.80,
                "w_vol": 0.50, "w_vad": 0.30, "w_pitch": 0.15, "w_laugh": 0.05},
    }

    REACTION_ZONES = [
        ("🔥", "Pure Hype Explosion", "Pure_Hype_Explosion"),
        ("😂", "Hysterical Laughter Fit", "Hysterical_Laughter_Fit"),
        ("😱", "High-Pitched Scream / Shriek", "High_Pitched_Scream"),
        ("📢", "Victory Shout / Callout", "Victory_Shout_Callout"),
        ("😆", "Hyped Laughing Burst", "Hyped_Laughing_Burst"),
        ("🗣️", "Intense Rapid Banter", "Intense_Rapid_Banter"),
        ("😮", "Loud Gasp / Shock", "Loud_Gasp_Shock"),
        ("💬", "Elevated Excitement", "Elevated_Excitement"),
    ]

    def __init__(self, parent=None, app_dir=None):
        super().__init__(parent)
        self.app_dir = app_dir or os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "StreamerCalyx")
        os.makedirs(self.app_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.app_dir, "cooldown_clips.txt")
        self.history_file_path = os.path.join(self.app_dir, "reaction_history.json")

        # Engine Settings
        self.enabled = False
        self.selected_device_name = ""
        self.auto_sensitivity = True
        self.input_gain = 1.0              # 0.25 to 2.0 (Input Gain Trim)
        self.trigger_offset = 0.30         # 0.15 to 0.60 (Offset above baseline)
        self.manual_threshold = 0.75       # 0.40 to 1.0 (matches Tester 75% default)
        self.min_duration_ms = 250         # 100 to 800ms
        self.weight_volume = 0.40
        self.weight_vad = 0.25
        self.weight_pitch = 0.20
        self.weight_laughter = 0.15
        self.log_orange_moments = True
        self.flash_overlay = True
        self.alert_color = "#f59e0b"       # Gold default
        self.play_chime = True
        self.cooldown_duration_sec = 60
        self.active_scenes = ["In-Game", "Banter"]
        self.marker_description = "Auto-Clip/Markers"
        self.marker_template = "{icon} {tag} [{game}]"
        self.game_title = ""
        self.save_replay_buffer = True
        self.replay_dir = ""
        self.auto_rename_replays = False
        self.voice_profile = "dynamic"
        self.genre_preset = "default"
        self.desk_thump_sensitivity = 0.55 # 0.0 (off) to 1.0 (strict)
        self.event_log_filter = {
            "mode": "all",       # "all" | "reactions" | "hype" | "status"
            "reactions": [],
            "hype_ranges": [],
            "statuses": [],
        }
        self.streamer_mode = False

        # Audio Capture State
        self.audio_source = None
        self.audio_io = None
        self.current_device = None
        self._sample_format = None
        self._sample_rate = 48000
        self._channels = 2

        # Level & Baseline Buffer (10 seconds @ 50ms = 200 samples)
        self._buffer_capacity = 200
        self.level_buffer = deque(maxlen=self._buffer_capacity)
        for _ in range(self._buffer_capacity):
            self.level_buffer.append(0.08)  # Seed initial quiet baseline

        # Prosody Envelope & Pitch Buffers (2.0s @ 20Hz = 40 frames)
        self._envelope_buffer = deque(maxlen=40)
        self._pitch_baseline = 165.0
        self._pitch_count = 0
        self._last_dsp = {
            "f0_hz": 0.0,
            "f0_ratio": 1.0,
            "pitch_baseline": 165.0,
            "laughter_cadence": 0.0,
            "banter_cadence": 0.0,
            "vocal_vad": False,
            "vocal_ratio": 0.0,
            "subbass_ratio": 0.0,
            "thump_rejected": False,
            "crest_factor": 1.0,
            "last_reaction": "",
        }
        self._peak_max_level = 0.0
        self._peak_max_f0 = 0.0
        self._peak_max_laughter = 0.0
        self._peak_max_banter = 0.0
        self._peak_max_crest = 1.0
        self._reaction_history = self._load_reaction_history()

        self.current_level = 0.0
        self.current_baseline = 0.08
        self.current_threshold = 0.68

        # Dual-Baseline: Session Voice Anchor (Long-term speech profile for quiet gaming)
        self.session_voice_anchor = 0.35   # Standard speech profile (35% default)
        self.session_voice_count = 0

        # Peak Detection & Duration Tracking
        self._spike_start_time = None
        self._peak_latched = False
        self._last_orange_log_time = 0.0
        self._last_secondary_log_time = 0.0

        # Cooldown State
        self.is_in_cooldown = False
        self.cooldown_remaining = 0
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.setInterval(1000)
        self._cooldown_timer.timeout.connect(self._on_cooldown_tick)

        # Sampling Timer (50ms = 20Hz level updates)
        self._sample_timer = QTimer(self)
        self._sample_timer.setInterval(50)
        self._sample_timer.timeout.connect(self._process_audio_samples)

        # Session & Scene Tracking
        self._session_start_time = time.time()
        self._current_scene_name = ""
        self._current_scene_id = ""
        self._scene_paused = False
        self.slobs_client = get_streamlabs_client()
        if self.slobs_client:
            self.slobs_client.scene_switched.connect(self._on_scene_switched)

        # Start listening if enabled
        if self.enabled:
            QTimer.singleShot(500, self.start_audio_capture)

    # ------------------ Audio Device Management ------------------

    def get_available_devices(self) -> list:
        """Returns a list of QAudioDevice input devices."""
        try:
            return QMediaDevices.audioInputs()
        except Exception as e:
            log_debug("AUTOCLIP", f"Error enumerating audio inputs: {e}")
            return []

    def set_device_by_name(self, name: str):
        """Switches the listening input device to the specified device name."""
        self.selected_device_name = name
        log_debug("AUTOCLIP", f"Switching audio input device to: '{name}'")
        self.restart_audio_capture()

    def _resolve_target_device(self) -> QAudioDevice:
        """Finds matching QAudioDevice, prioritizing VoiceMeeter VAIO if nothing specified."""
        devices = self.get_available_devices()
        if not devices:
            return None

        # 1. Match explicitly configured name
        if self.selected_device_name:
            for d in devices:
                if d.description().strip() == self.selected_device_name.strip():
                    return d

        # 2. Prefer VoiceMeeter Output (B1/B2/VAIO)
        for d in devices:
            desc = d.description().lower()
            if "voicemeeter out b" in desc or "voicemeeter vaio" in desc:
                return d

        # 3. Fallback to system default
        return QMediaDevices.defaultAudioInput()

    def restart_audio_capture(self):
        """Restarts the audio capture stream on the target device."""
        self.stop_audio_capture()
        if self.enabled:
            self.start_audio_capture()

    def start_audio_capture(self):
        """Initializes and begins listening to the audio input device."""
        if not self.enabled:
            return

        if not getattr(self, "streamer_mode", False):
            log_debug("AUTOCLIP", "Audio capture skipped: Streamer Mode is disabled.")
            self.status_changed.emit("Paused (Streamer Mode disabled)", False)
            return

        # Check scene scoping
        if not self.is_scene_active():
            self._scene_paused = True
            self.status_changed.emit(f"Paused (Scene '{self._current_scene_name}' not active)", False)
        else:
            self._scene_paused = False

        device = self._resolve_target_device()
        if not device or device.isNull():
            log_debug("AUTOCLIP", "No valid audio input device found.")
            self.status_changed.emit("No audio input device found", False)
            return

        self.current_device = device
        fmt = device.preferredFormat()
        self._sample_rate = fmt.sampleRate() or 48000
        self._channels = max(1, fmt.channelCount())
        self._sample_format = fmt.sampleFormat()

        try:
            self.audio_source = QAudioSource(device, fmt, self)
            self.audio_io = self.audio_source.start()
            self._sample_timer.start()
            dev_label = device.description()
            log_debug("AUTOCLIP", f"Audio capture active on: {dev_label} ({self._sample_rate}Hz, {self._channels}ch)")
            if not self._scene_paused:
                self.status_changed.emit(f"Active ({dev_label})", True)
        except Exception as e:
            log_debug("AUTOCLIP", f"Failed to start QAudioSource: {e}")
            self.status_changed.emit(f"Error: {e}", False)

    def stop_audio_capture(self):
        """Stops the audio capture stream."""
        self._sample_timer.stop()
        if self.audio_source:
            try:
                self.audio_source.stop()
                self.audio_source.deleteLater()
            except Exception:
                pass
            self.audio_source = None
            self.audio_io = None

    def set_streamer_mode(self, enabled: bool):
        """Toggles streamer mode gating. Pauses capture when disabled to save CPU."""
        self.streamer_mode = bool(enabled)
        log_debug("AUTOCLIP", f"Streamer Mode set to {self.streamer_mode}")
        if not self.streamer_mode:
            self.stop_audio_capture()
            self.status_changed.emit("Paused (Streamer Mode disabled)", False)
        else:
            if self.enabled and self.is_scene_active():
                self.start_audio_capture()

    # ------------------ Scene Scoping ------------------

    def _on_scene_switched(self, scene_id: str, scene_name: str):
        # Resolve scene name cleanly (slobs emits scene_id, scene_name)
        resolved_name = scene_name or scene_id or ""
        self._current_scene_name = resolved_name
        self._current_scene_id = scene_id or ""
        is_active = self.is_scene_active()
        log_debug("AUTOCLIP", f"Scene switched to '{resolved_name}' (ID: '{scene_id}') | Auto-Clip Allowed={is_active}")

        if not self.enabled or not getattr(self, "streamer_mode", False):
            return

        if is_active:
            self._scene_paused = False
            dev_label = self.current_device.description() if self.current_device else "Active"
            self.status_changed.emit(f"Active ({dev_label})", True)
            if not self._sample_timer.isActive() or not self.audio_source:
                self.start_audio_capture()
        else:
            self._scene_paused = True
            self.status_changed.emit(f"Paused (Scene '{resolved_name}')", False)

    def is_scene_active(self) -> bool:
        """Checks if current scene is in the active_scenes whitelist."""
        if not self.active_scenes:
            return True  # If empty, allow all scenes
        if not self._current_scene_name and not getattr(self, "_current_scene_id", ""):
            return True
        curr_name = (self._current_scene_name or "").lower().strip()
        curr_id = getattr(self, "_current_scene_id", "").lower().strip()
        for allowed in self.active_scenes:
            a = allowed.lower().strip()
            if not a:
                continue
            if a in curr_name or curr_name in a or (curr_id and a == curr_id):
                return True
        return False

    # ------------------ Audio Sampling & Peak Analysis ------------------

    def _process_audio_samples(self, override_level: float = None):
        """Reads pending PCM audio data, runs vectorized prosody DSP, and tests thresholds."""
        if override_level is not None:
            level_val = override_level
            dsp = dict(self._last_dsp)
        else:
            if not self.audio_io:
                return

            try:
                raw_bytes = self.audio_io.readAll().data()
            except Exception:
                return

            if not raw_bytes:
                return

            # If paused by scene filter, drain buffer to prevent overflow, show 0 level and skip triggers
            if getattr(self, "_scene_paused", False):
                self.current_level = 0.0
                self.level_updated.emit(0.0, self.ZONE_GREEN, self.current_baseline, self.current_threshold)
                return

            # Vectorized Acoustic Prosody DSP (level + <70Hz thump rejection + VAD + F0 + 4-6Hz cadence)
            dsp = self._analyze_audio_frame(raw_bytes)
            level_val = dsp["level"]
            self._last_dsp.update(dsp)
            self.dsp_telemetry_updated.emit(dict(self._last_dsp))

        self.current_level = level_val

        # Update 10-second rolling baseline only from non-peak audio (ambient + normal talking)
        # Prevents screaming or loud laughter from dragging the baseline up and canceling triggers
        if level_val < (self.current_threshold * 0.85):
            self.level_buffer.append(level_val)
            self.current_baseline = sum(self.level_buffer) / len(self.level_buffer)

        # Update Session Voice Anchor (Cumulative Speech EMA)
        if 0.22 <= level_val <= 0.55 and dsp.get("vocal_vad", True):
            alpha = 0.05 if self.session_voice_count < 100 else 0.005
            self.session_voice_anchor = (1.0 - alpha) * self.session_voice_anchor + alpha * level_val
            self.session_voice_anchor = max(0.25, min(0.52, self.session_voice_anchor))
            self.session_voice_count += 1

        # Calculate dynamic or manual thresholds with Dual-Baseline floor
        if self.auto_sensitivity:
            effective_baseline = max(self.current_baseline, self.session_voice_anchor)
            offset = self.trigger_offset
            red_thresh = min(0.98, max(0.48, effective_baseline + offset))
            orange_thresh = min(0.90, max(0.36, red_thresh * 0.78))
            yellow_thresh = min(0.60, max(0.20, red_thresh * 0.42))
        else:
            red_thresh = max(0.40, min(1.0, self.manual_threshold))
            orange_thresh = red_thresh * 0.78
            yellow_thresh = red_thresh * 0.42

        self.current_threshold = red_thresh

        # Determine current zone
        if level_val >= red_thresh:
            zone = self.ZONE_RED
        elif level_val >= orange_thresh:
            zone = self.ZONE_ORANGE
        elif level_val >= yellow_thresh:
            zone = self.ZONE_YELLOW
        else:
            zone = self.ZONE_GREEN

        # Emit live level for VU meter
        self.level_updated.emit(level_val, zone, self.current_baseline, red_thresh)

        # Handle Orange "Possible Moment" (debounced 15s)
        if zone == self.ZONE_ORANGE and self.log_orange_moments:
            now = time.time()
            if now - self._last_orange_log_time >= 15.0:
                self._last_orange_log_time = now
                self._handle_orange_possible_peak()

        # Handle Red Peak Event with Sustained Duration Filter & Hysteresis Latch
        if zone == self.ZONE_RED:
            if not self._peak_latched:
                if self._spike_start_time is None:
                    self._spike_start_time = time.time()
                    self._peak_max_level = level_val
                    self._peak_max_f0 = dsp.get("f0_hz", 0.0)
                    self._peak_max_laughter = dsp.get("laughter_cadence", 0.0)
                    self._peak_max_banter = dsp.get("banter_cadence", 0.0)
                    self._peak_max_crest = dsp.get("crest_factor", 1.0)
                else:
                    self._peak_max_level = max(self._peak_max_level, level_val)
                    self._peak_max_f0 = max(self._peak_max_f0, dsp.get("f0_hz", 0.0))
                    self._peak_max_laughter = max(self._peak_max_laughter, dsp.get("laughter_cadence", 0.0))
                    self._peak_max_banter = max(self._peak_max_banter, dsp.get("banter_cadence", 0.0))
                    self._peak_max_crest = max(self._peak_max_crest, dsp.get("crest_factor", 1.0))

                elapsed_ms = (time.time() - self._spike_start_time) * 1000.0
                if elapsed_ms >= self.min_duration_ms:
                    self._trigger_peak_event()
                    self._peak_latched = True
                    self._spike_start_time = None
        else:
            self._spike_start_time = None
            if zone in (self.ZONE_GREEN, self.ZONE_YELLOW):
                self._peak_latched = False

    def _decode_pcm_mono(self, raw_bytes: bytes) -> np.ndarray:
        """Decodes Float32, Int32, or Int16 PCM bytes into a mono float32 numpy array (-1.0 to 1.0)."""
        fmt = getattr(self, "_sample_format", None)
        if fmt == QAudioFormat.SampleFormat.Float:
            n = (len(raw_bytes) // 4) * 4
            if n < 4:
                return np.empty(0, dtype=np.float32)
            arr = np.frombuffer(raw_bytes[:n], dtype=np.float32)
        elif fmt == QAudioFormat.SampleFormat.Int32:
            n = (len(raw_bytes) // 4) * 4
            if n < 4:
                return np.empty(0, dtype=np.float32)
            arr = np.frombuffer(raw_bytes[:n], dtype=np.int32).astype(np.float32) / 2147483647.0
        else:
            n = (len(raw_bytes) // 2) * 2
            if n < 2:
                return np.empty(0, dtype=np.float32)
            arr = np.frombuffer(raw_bytes[:n], dtype=np.int16).astype(np.float32) / 32767.0

        ch = max(1, int(getattr(self, "_channels", 1) or 1))
        if ch > 1 and arr.size >= ch:
            usable = (arr.size // ch) * ch
            arr = arr[:usable].reshape(-1, ch).mean(axis=1)
        return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)

    def _analyze_audio_frame(self, raw_bytes: bytes) -> dict:
        """
        Vectorized 20 Hz Acoustic Prosody DSP pipeline:
        1. Sub-bass desk thump / mic drop rejection (<70 Hz)
        2. Human vocal tract Voice Activity Detection (80 Hz - 3500 Hz)
        3. Stevens' power-law perceptual loudness expansion (RMS^0.5 + Peak^0.5)
        4. Autocorrelation pitch tracking (F0 80-550 Hz) + >1.35x baseline inflection
        5. Human laughter envelope cadence tracking (4-6 Hz) & rapid banter (6-10 Hz)
        """
        result = {
            "level": 0.0,
            "f0_hz": 0.0,
            "f0_ratio": 1.0,
            "pitch_baseline": self._pitch_baseline,
            "laughter_cadence": 0.0,
            "banter_cadence": 0.0,
            "vocal_vad": False,
            "vocal_ratio": 0.0,
            "subbass_ratio": 0.0,
            "thump_rejected": False,
            "crest_factor": 1.0,
        }
        try:
            mono = self._decode_pcm_mono(raw_bytes)
            if mono.size < 32:
                return result

            sr = max(8000, int(getattr(self, "_sample_rate", 48000) or 48000))
            gain = getattr(self, "input_gain", 1.0) * 2.5

            # Remove DC offset
            mono = mono - np.mean(mono)
            scaled = mono * gain

            # Spectral analysis via rFFT for sub-bass thump rejection (<70Hz) & Vocal VAD (80-3500Hz)
            win = np.hanning(scaled.size).astype(np.float32)
            spec = np.abs(np.fft.rfft(scaled * win))
            freqs = np.fft.rfftfreq(scaled.size, d=1.0 / sr)
            power = spec * spec
            total_power = float(np.sum(power)) + 1e-12

            sub_mask = freqs < 70.0
            vocal_mask = (freqs >= 80.0) & (freqs <= 3500.0)
            sub_power = float(np.sum(power[sub_mask]))
            vocal_power = float(np.sum(power[vocal_mask]))

            subbass_ratio = sub_power / total_power
            vocal_ratio = vocal_power / total_power
            result["subbass_ratio"] = subbass_ratio
            result["vocal_ratio"] = vocal_ratio

            # Band-filtered signal in vocal tract (zero out <70 Hz in FFT domain)
            fft_full = np.fft.rfft(scaled)
            fft_hp = fft_full.copy()
            fft_hp[freqs < 70.0] = 0.0
            hp_sig = np.fft.irfft(fft_hp, n=scaled.size)

            # Raw RMS & Peak on <70Hz-filtered vocal signal
            rms_raw = float(np.sqrt(np.mean(hp_sig * hp_sig)))
            peak_raw = float(np.max(np.abs(hp_sig))) if hp_sig.size else 0.0
            crest = (peak_raw / max(rms_raw, 1e-5)) if rms_raw > 0.002 else 1.0
            result["crest_factor"] = min(12.0, crest)

            # Desk thump / mic drop rejection: if sub-bass (<70Hz) dominates vocal band
            thump_sens = float(getattr(self, "desk_thump_sensitivity", 0.55))
            thump_cutoff = 0.72 - (thump_sens * 0.35)  # 0.72 (lenient) down to 0.37 (strict)
            is_thump = (subbass_ratio > thump_cutoff) and (vocal_ratio < 0.35) and (thump_sens > 0.05)
            result["thump_rejected"] = is_thump

            rms = min(1.0, rms_raw)
            peak = min(1.0, peak_raw)
            if is_thump:
                rms *= 0.25
                peak *= 0.25

            # Stevens' power-law perceptual loudness expansion (RMS^0.5 + Peak^0.5)
            p_rms = math.sqrt(rms) if rms > 0.0 else 0.0
            p_peak = math.sqrt(peak) if peak > 0.0 else 0.0
            level = min(1.0, max(0.0, (0.65 * p_rms) + (0.35 * p_peak)))
            result["level"] = level

            # Voice Activity Detection in 80-3500 Hz + SNR-weighted confidence (avoids pinning at 100%)
            vocal_vad = (vocal_ratio >= 0.38) and (level >= 0.14) and (not is_thump)
            result["vocal_vad"] = vocal_vad
            if vocal_vad:
                snr_score = min(1.0, max(0.0, (level - max(0.08, self.current_baseline)) / 0.35))
                result["vad_confidence"] = min(1.0, (0.55 * vocal_ratio) + (0.45 * snr_score))
            else:
                result["vad_confidence"] = 0.0

            # Update 20 Hz envelope buffer & compute 4-6 Hz laughter + 6-10 Hz banter cadence
            self._envelope_buffer.append(level)
            if vocal_vad and len(self._envelope_buffer) >= 16:
                env = np.array(self._envelope_buffer, dtype=np.float32)
                env_std = float(np.std(env))
                if env_std >= 0.035 and level >= 0.22:
                    env_zm = env - np.mean(env)
                    env_spec = np.abs(np.fft.rfft(env_zm)) ** 2
                    env_freqs = np.fft.rfftfreq(env_zm.size, d=0.05)  # 20 Hz frame rate
                    env_total = float(np.sum(env_spec[1:])) + 1e-9
                    laugh_mask = (env_freqs >= 4.2) & (env_freqs <= 6.0)
                    banter_mask = (env_freqs > 6.0) & (env_freqs <= 10.0)
                    raw_laugh = float(np.sum(env_spec[laugh_mask])) / env_total
                    raw_banter = float(np.sum(env_spec[banter_mask])) / env_total
                    # Subtract normal speech syllable floor (~24%) and require rhythmic depth
                    depth_gain = min(1.0, env_std / 0.08)
                    result["laughter_cadence"] = min(1.0, max(0.0, (raw_laugh - 0.24) / 0.38) * depth_gain)
                    result["banter_cadence"] = min(1.0, max(0.0, (raw_banter - 0.18) / 0.35) * depth_gain)

            # Autocorrelation Pitch Tracking (F0: 80 - 550 Hz) when vocal activity present
            if vocal_vad and hp_sig.size >= (sr // 40):
                # Limit to 1024-2048 samples for fast vectorized autocorrelation
                seg = hp_sig[-min(hp_sig.size, 2048):]
                seg_energy = float(np.dot(seg, seg))
                if seg_energy > 1e-6:
                    # FFT-based autocorrelation: O(N log N)
                    n_fft = 1 << int(math.ceil(math.log2(seg.size * 2)))
                    f_seg = np.fft.rfft(seg, n=n_fft)
                    acf = np.fft.irfft(f_seg * np.conj(f_seg), n=n_fft)[:seg.size]
                    acf = acf / (acf[0] + 1e-12)
                    lag_min = max(1, sr // 550)
                    lag_max = min(seg.size - 1, sr // 80)
                    if lag_max > lag_min + 2:
                        sub_acf = acf[lag_min:lag_max]
                        best_idx = int(np.argmax(sub_acf))
                        peak_corr = float(sub_acf[best_idx])
                        if peak_corr >= 0.32:
                            f0_hz = float(sr) / float(lag_min + best_idx)
                            result["f0_hz"] = f0_hz
                            # Adapt pitch baseline only in dynamic profile during normal speech
                            prof = self.VOICE_PROFILES.get(getattr(self, "voice_profile", "dynamic"), self.VOICE_PROFILES["dynamic"])
                            if prof["adapt"] and 0.20 <= level <= 0.62 and 80.0 <= f0_hz <= 320.0:
                                alpha = 0.08 if self._pitch_count < 60 else 0.015
                                self._pitch_baseline = (1.0 - alpha) * self._pitch_baseline + alpha * f0_hz
                                self._pitch_count += 1
                            elif not prof["adapt"]:
                                self._pitch_baseline = prof["f0_base"]
                            result["pitch_baseline"] = self._pitch_baseline
                            result["f0_ratio"] = f0_hz / max(60.0, self._pitch_baseline)

            if vocal_vad and not is_thump:
                inflect_boost = min(1.0, max(0.0, (result["f0_ratio"] - 1.0) * 1.5))
                w_vol = float(getattr(self, "weight_volume", 0.40))
                w_vad = float(getattr(self, "weight_vad", 0.25))
                w_pit = float(getattr(self, "weight_pitch", 0.20))
                w_lgh = float(getattr(self, "weight_laughter", 0.15))
                w_sum = max(0.01, w_vol + w_vad + w_pit + w_lgh)
                vad_c = float(result.get("vad_confidence", 0.0))
                result["composite_hype"] = min(1.0, (
                    w_vol * level
                    + w_vad * vad_c
                    + w_pit * inflect_boost
                    + w_lgh * result["laughter_cadence"]
                ) / w_sum)
            else:
                result["composite_hype"] = 0.0

            return result
        except Exception:
            return result

    def _calculate_level(self, raw_bytes: bytes) -> float:
        """Backward-compatible wrapper returning normalized perceptual level (0.0 to 1.0)."""
        return self._analyze_audio_frame(raw_bytes)["level"]

    def classify_vocal_reaction(self, level: float, f0_hz: float, f0_ratio: float,
                                laughter_cadence: float, banter_cadence: float, crest_factor: float) -> tuple:
        """
        8-Zone Human Vocal Reaction Classifier.
        Returns (icon, label, slug).
        """
        if level >= 0.90 and f0_ratio >= 1.25 and laughter_cadence < 0.35:
            return self.REACTION_ZONES[0]  # 🔥 Pure Hype Explosion
        if laughter_cadence >= 0.38:
            return self.REACTION_ZONES[1]  # 😂 Hysterical Laughter Fit
        if f0_hz >= 340.0 or f0_ratio >= 1.60:
            return self.REACTION_ZONES[2]  # 😱 High-Pitched Scream / Shriek
        if crest_factor >= 5.2 and f0_ratio >= 1.35 and level < 0.85:
            return self.REACTION_ZONES[6]  # 😮 Loud Gasp / Shock
        if laughter_cadence >= 0.20:
            return self.REACTION_ZONES[4]  # 😆 Hyped Laughing Burst
        if banter_cadence >= 0.28 and level < 0.86:
            return self.REACTION_ZONES[5]  # 🗣️ Intense Rapid Banter
        if level >= 0.72:
            return self.REACTION_ZONES[3]  # 📢 Victory Shout / Callout
        return self.REACTION_ZONES[7]      # 💬 Elevated Excitement

    def format_marker_text(self, payload: dict) -> str:
        """Formats Twitch marker description using customizable template ({icon} {tag} [{game}])."""
        tpl = (getattr(self, "marker_template", "") or "").strip()
        if not tpl:
            return getattr(self, "marker_description", "Auto-Clip/Markers")
        icon = payload.get("reaction_icon", "💬")
        tag = payload.get("reaction_label", getattr(self, "marker_description", "Auto-Clip"))
        game = (getattr(self, "game_title", "") or "").strip()
        text = tpl.replace("{icon}", icon).replace("{tag}", tag)
        if game:
            text = text.replace("{game}", game)
        else:
            text = text.replace("[{game}]", "").replace("({game})", "").replace("{game}", "")
        return " ".join(text.split())[:140]

    # ------------------ Peak Event & Cooldown Dispatch ------------------

    def _trigger_peak_event(self):
        """Fires when audio exceeds red threshold for min duration."""
        stream_pos_sec, timestamp_str = self._get_current_stream_timestamp()
        clip_start_sec = max(0, stream_pos_sec - 40)
        clip_end_sec = stream_pos_sec + 20
        clip_range_str = f"Start: {self._format_seconds(clip_start_sec)} | End: {self._format_seconds(clip_end_sec)}"

        peak_lvl = max(self.current_level, getattr(self, "_peak_max_level", 0.0))
        peak_f0 = max(self._last_dsp.get("f0_hz", 0.0), getattr(self, "_peak_max_f0", 0.0))
        f0_ratio = (peak_f0 / max(60.0, self._pitch_baseline)) if peak_f0 > 0 else self._last_dsp.get("f0_ratio", 1.0)
        laugh_cad = max(self._last_dsp.get("laughter_cadence", 0.0), getattr(self, "_peak_max_laughter", 0.0))
        banter_cad = max(self._last_dsp.get("banter_cadence", 0.0), getattr(self, "_peak_max_banter", 0.0))
        crest = max(self._last_dsp.get("crest_factor", 1.0), getattr(self, "_peak_max_crest", 1.0))

        icon, label, slug = self.classify_vocal_reaction(peak_lvl, peak_f0, f0_ratio, laugh_cad, banter_cad, crest)
        self._last_dsp["last_reaction"] = f"{icon} {label}"

        payload = {
            "position_seconds": stream_pos_sec,
            "timestamp_str": timestamp_str,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "clip_range_str": clip_range_str,
            "clip_start_sec": clip_start_sec,
            "clip_end_sec": clip_end_sec,
            "level": peak_lvl,
            "baseline": self.current_baseline,
            "threshold": self.current_threshold,
            "description": self.marker_description,
            "reaction_icon": icon,
            "reaction_label": label,
            "reaction_slug": slug,
            "f0_hz": round(peak_f0, 1),
            "f0_ratio": round(f0_ratio, 2),
            "laughter_cadence": round(laugh_cad, 2),
        }
        payload["formatted_marker"] = self.format_marker_text(payload)

        now = time.time()
        if not self.is_in_cooldown:
            log_debug("AUTOCLIP", f"{icon} PRIMARY PEAK ({label}) at {timestamp_str} (lvl={peak_lvl:.2f}, F0={peak_f0:.0f}Hz) -> {clip_range_str}")
            if self.should_log_event("primary", label, peak_lvl):
                self._append_reaction_history(payload, kind="primary")
            self.marker_triggered.emit(payload)
            self._start_cooldown()
            self._last_secondary_log_time = now
        else:
            if now - getattr(self, "_last_secondary_log_time", 0.0) >= 15.0:
                self._last_secondary_log_time = now
                log_debug("AUTOCLIP", f"⏱️ SECONDARY PEAK ({icon} {label}) during cooldown at {timestamp_str} -> {clip_range_str}")
                if self.should_log_event("secondary", label, peak_lvl):
                    self._log_clip_to_file(
                        f"[Secondary Peak at {timestamp_str}] {icon} {label} -> {clip_range_str} (Cooldown active: {self.cooldown_remaining}s left)"
                    )
                    self._append_reaction_history(payload, kind="secondary")
                self.secondary_peak_logged.emit(payload)

    def _handle_orange_possible_peak(self):
        """Logs an orange possible moment with vocal reaction classification."""
        stream_pos_sec, timestamp_str = self._get_current_stream_timestamp()
        clip_start_sec = max(0, stream_pos_sec - 40)
        clip_end_sec = stream_pos_sec + 20
        clip_range_str = f"Start: {self._format_seconds(clip_start_sec)} | End: {self._format_seconds(clip_end_sec)}"

        dsp = getattr(self, "_last_dsp", {}) or {}
        icon, label, slug = self.classify_vocal_reaction(
            self.current_level,
            dsp.get("f0_hz", 0.0),
            dsp.get("f0_ratio", 1.0),
            dsp.get("laughter_cadence", 0.0),
            dsp.get("banter_cadence", 0.0),
            dsp.get("crest_factor", 1.0),
        )
        payload = {
            "position_seconds": stream_pos_sec,
            "timestamp_str": timestamp_str,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "clip_range_str": clip_range_str,
            "level": max(self.current_level, dsp.get("composite_hype", 0.0)),
            "reaction_icon": icon,
            "reaction_label": label,
            "reaction_slug": slug,
        }
        log_debug("AUTOCLIP", f"{icon} ORANGE MOMENT ({label}) at {timestamp_str} -> {clip_range_str}")
        if self.should_log_event("orange", label, payload["level"]):
            self._log_clip_to_file(
                f"[Possible Peak at {timestamp_str}] {icon} {label} -> {clip_range_str} (Orange Moment)"
            )
        self.possible_peak_logged.emit(payload)

    def _start_cooldown(self):
        """Initiates the 60-second cooldown timer."""
        self.is_in_cooldown = True
        self.cooldown_remaining = self.cooldown_duration_sec
        self.cooldown_tick.emit(self.cooldown_remaining)
        self._cooldown_timer.start()

    def _on_cooldown_tick(self):
        self.cooldown_remaining -= 1
        if self.cooldown_remaining <= 0:
            self._cooldown_timer.stop()
            self.is_in_cooldown = False
            self.cooldown_remaining = 0
            self.cooldown_tick.emit(0)
            log_debug("AUTOCLIP", "Cooldown finished. Auto-Clip armed and ready.")
        else:
            self.cooldown_tick.emit(self.cooldown_remaining)

    # ------------------ Timing & File Logging ------------------

    def _get_current_stream_timestamp(self) -> tuple:
        """Calculates current elapsed stream seconds and human-readable timestamp."""
        # 1. Check Streamlabs live streaming start time
        if self.slobs_client and hasattr(self.slobs_client, "is_streaming") and self.slobs_client.is_streaming():
            start_t = getattr(self.slobs_client, "_stream_start_time", 0.0)
            if start_t > 0:
                elapsed = max(0, int(time.time() - start_t))
                return elapsed, self._format_seconds(elapsed)

        # 2. Fallback to session elapsed time
        elapsed = max(0, int(time.time() - self._session_start_time))
        # Also include wall-clock time for clear manual editing
        now_str = datetime.now().strftime("%H:%M:%S")
        return elapsed, f"{self._format_seconds(elapsed)} ({now_str})"

    def _format_seconds(self, total_seconds: int) -> str:
        """Formats integer seconds into MM:SS or HH:MM:SS."""
        hrs = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def _log_clip_to_file(self, line: str):
        """Appends a clip entry with timestamp and 40/20 window to cooldown_clips.txt."""
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            needs_header = not os.path.exists(self.log_file_path) or os.path.getsize(self.log_file_path) == 0
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                if needs_header:
                    f.write(f"=== Streamer Calyx Auto-Clip / Markers Log ({today_str}) ===\n")
                    f.write("40/20 Window: 40s pre-context + 20s aftermath relative to peak.\n\n")
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
        except Exception as e:
            log_debug("AUTOCLIP_ERR", f"Failed to write to cooldown_clips.txt: {e}")

    # ------------------ Public Control Methods ------------------

    def start_monitoring(self):
        """Starts audio capture and monitoring."""
        self.enabled = True
        self.start_audio_capture()

    def stop_monitoring(self):
        """Stops audio capture and monitoring."""
        self.enabled = False
        self.stop_audio_capture()
        self.current_level = 0.0
        self.level_updated.emit(0.0, self.ZONE_GREEN, self.current_baseline, self.current_threshold)
        self.status_changed.emit("Disabled", False)

    def open_log_file(self):
        """Opens cooldown_clips.txt in the system's default text editor."""
        try:
            if not os.path.exists(self.log_file_path):
                self._log_clip_to_file("Log file initialized.")
            os.startfile(self.log_file_path)
        except Exception as e:
            log_debug("AUTOCLIP", f"Error opening log file: {e}")

    def clear_log_file(self):
        """Empties the cooldown_clips.txt log file."""
        try:
            with open(self.log_file_path, "w", encoding="utf-8") as f:
                f.write(f"=== Streamer Calyx Auto-Clip / Markers Log ({datetime.now().strftime('%Y-%m-%d')}) ===\n")
            log_debug("AUTOCLIP", "cooldown_clips.txt cleared.")
        except Exception as e:
            log_debug("AUTOCLIP", f"Error clearing log file: {e}")

    def reset_session_voice(self):
        """Resets the learned long-term session voice anchor and pitch baseline."""
        self.session_voice_anchor = 0.35
        self.session_voice_count = 0
        prof = self.VOICE_PROFILES.get(getattr(self, "voice_profile", "dynamic"), self.VOICE_PROFILES["dynamic"])
        self._pitch_baseline = prof["f0_base"]
        self._pitch_count = 0
        log_debug("AUTOCLIP", "Session Voice Anchor and F0 pitch baseline reset.")

    def apply_voice_profile(self, profile_key: str):
        """Applies a Voice Profile preset (dynamic, deep, mid, high)."""
        if profile_key not in self.VOICE_PROFILES:
            profile_key = "dynamic"
        self.voice_profile = profile_key
        self._pitch_baseline = self.VOICE_PROFILES[profile_key]["f0_base"]
        self._pitch_count = 0
        log_debug("AUTOCLIP", f"Applied voice profile '{profile_key}' (F0={self._pitch_baseline} Hz)")

    def apply_genre_preset(self, preset_key: str):
        """Applies a 1-click Game Genre Preset (default, horror, comedy, fps)."""
        if preset_key not in self.GENRE_PRESETS:
            preset_key = "default"
        p = self.GENRE_PRESETS[preset_key]
        self.genre_preset = preset_key
        self.trigger_offset = p["trigger_offset"]
        self.min_duration_ms = p["min_duration_ms"]
        self.desk_thump_sensitivity = p["desk_thump_sensitivity"]
        self.weight_volume = p.get("w_vol", 0.40)
        self.weight_vad = p.get("w_vad", 0.25)
        self.weight_pitch = p.get("w_pitch", 0.20)
        self.weight_laughter = p.get("w_laugh", 0.15)
        log_debug("AUTOCLIP", f"Applied genre preset '{preset_key}': offset={self.trigger_offset}, dur={self.min_duration_ms}ms, thump={self.desk_thump_sensitivity}")

    # ------------------ Reaction History Persistence ------------------

    def _load_reaction_history(self) -> list:
        try:
            if os.path.exists(self.history_file_path):
                with open(self.history_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception as e:
            log_debug("AUTOCLIP", f"Could not load reaction_history.json: {e}")
        return []

    def _append_reaction_history(self, payload: dict, kind: str = "primary"):
        entry = {
            "created_at": payload.get("created_at", datetime.now().isoformat(timespec="seconds")),
            "position_seconds": int(payload.get("position_seconds", 0)),
            "timestamp_str": payload.get("timestamp_str", "00:00"),
            "clip_start_sec": int(payload.get("clip_start_sec", 0)),
            "clip_end_sec": int(payload.get("clip_end_sec", 0)),
            "reaction_icon": payload.get("reaction_icon", "💬"),
            "reaction_label": payload.get("reaction_label", "Elevated Excitement"),
            "reaction_slug": payload.get("reaction_slug", "Elevated_Excitement"),
            "formatted_marker": payload.get("formatted_marker", ""),
            "f0_hz": payload.get("f0_hz", 0.0),
            "level": round(float(payload.get("level", 0.0)), 3),
            "kind": kind,
        }
        self._reaction_history.append(entry)
        self._reaction_history = self._reaction_history[-500:]
        try:
            with open(self.history_file_path, "w", encoding="utf-8") as f:
                json.dump(self._reaction_history, f, indent=2)
        except Exception as e:
            log_debug("AUTOCLIP_ERR", f"Failed to save reaction_history.json: {e}")

    def get_reaction_history(self) -> list:
        return list(self._reaction_history)

    def clear_reaction_history(self):
        self._reaction_history = []
        try:
            with open(self.history_file_path, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception as e:
            log_debug("AUTOCLIP_ERR", f"Failed to clear reaction_history.json: {e}")

    def should_log_event(self, status_kind: str, reaction_label: str = "", level: float = 0.0) -> bool:
        """Evaluates whether an event passes the mutually-exclusive Event Log Filter."""
        flt = getattr(self, "event_log_filter", None) or {}
        mode = flt.get("mode", "all")
        if mode == "all":
            return True
        if mode == "reactions":
            sel = flt.get("reactions", [])
            return bool(sel) and (reaction_label in sel)
        if mode == "hype":
            sel = flt.get("hype_ranges", [])
            if not sel:
                return False
            pct = int(round(float(level) * 100))
            for r in sel:
                if r == "50-69" and 50 <= pct <= 69:
                    return True
                if r == "70-84" and 70 <= pct <= 84:
                    return True
                if r == "85-100" and pct >= 85:
                    return True
            return False
        if mode == "status":
            sel = flt.get("statuses", [])
            return bool(sel) and (status_kind in sel)
        return True

    # ------------------ Configuration Import / Export ------------------

    def export_settings(self) -> dict:
        return {
            "enabled": self.enabled,
            "device_name": self.selected_device_name,
            "auto_sensitivity": self.auto_sensitivity,
            "input_gain": self.input_gain,
            "trigger_offset": self.trigger_offset,
            "manual_threshold": self.manual_threshold,
            "min_duration_ms": self.min_duration_ms,
            "log_orange_moments": self.log_orange_moments,
            "flash_overlay": self.flash_overlay,
            "alert_color": self.alert_color,
            "play_chime": self.play_chime,
            "active_scenes": list(self.active_scenes),
            "cooldown_duration_sec": self.cooldown_duration_sec,
            "marker_description": self.marker_description,
            "marker_template": self.marker_template,
            "game_title": self.game_title,
            "save_replay_buffer": self.save_replay_buffer,
            "replay_dir": self.replay_dir,
            "auto_rename_replays": self.auto_rename_replays,
            "voice_profile": self.voice_profile,
            "genre_preset": self.genre_preset,
            "desk_thump_sensitivity": self.desk_thump_sensitivity,
            "weight_volume": self.weight_volume,
            "weight_vad": self.weight_vad,
            "weight_pitch": self.weight_pitch,
            "weight_laughter": self.weight_laughter,
            "event_log_filter": dict(self.event_log_filter),
            "session_voice_anchor": self.session_voice_anchor
        }

    def import_settings(self, d: dict):
        if not isinstance(d, dict):
            return
        self.enabled = d.get("enabled", False)
        self.selected_device_name = d.get("device_name", "")
        self.auto_sensitivity = d.get("auto_sensitivity", True)
        self.input_gain = d.get("input_gain", 1.0)
        self.trigger_offset = d.get("trigger_offset", 0.30)
        self.manual_threshold = d.get("manual_threshold", 0.70)
        self.min_duration_ms = d.get("min_duration_ms", 250)
        self.session_voice_anchor = d.get("session_voice_anchor", 0.35)
        self.log_orange_moments = d.get("log_orange_moments", True)
        self.flash_overlay = d.get("flash_overlay", True)
        self.alert_color = d.get("alert_color", "#f59e0b")
        self.play_chime = d.get("play_chime", True)
        self.active_scenes = list(d.get("active_scenes", ["In-Game", "Banter"]))
        self.cooldown_duration_sec = d.get("cooldown_duration_sec", 60)
        self.marker_description = d.get("marker_description", "Auto-Clip/Markers")
        self.marker_template = d.get("marker_template", "{icon} {tag} [{game}]")
        self.game_title = d.get("game_title", "")
        self.save_replay_buffer = d.get("save_replay_buffer", True)
        self.replay_dir = d.get("replay_dir", "")
        self.auto_rename_replays = d.get("auto_rename_replays", False)
        self.desk_thump_sensitivity = d.get("desk_thump_sensitivity", 0.55)
        self.weight_volume = d.get("weight_volume", 0.40)
        self.weight_vad = d.get("weight_vad", 0.25)
        self.weight_pitch = d.get("weight_pitch", 0.20)
        self.weight_laughter = d.get("weight_laughter", 0.15)
        if isinstance(d.get("event_log_filter"), dict):
            self.event_log_filter = dict(d["event_log_filter"])
        self.genre_preset = d.get("genre_preset", "default")
        self.apply_voice_profile(d.get("voice_profile", "dynamic"))
