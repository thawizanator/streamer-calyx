"""
Streamer Calyx - Audio Input Diagnostics & Live Calibration Suite
Combines Tester-Harness live 20 Hz prosody gauges with a configurable
X-minute sample test (Markers, Clips, Possibilities, Desk Bumps, Noise Ignores)
and automated calibration recommendations.
Does NOT record or save any audio files (privacy-safe).
"""

import os
import sys
import math
import time
import datetime
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressBar, QTextEdit, QMessageBox, QFrame,
    QGroupBox, QGridLayout, QScrollArea, QWidget
)
from PyQt6.QtGui import QColor, QPainter, QPen, QGuiApplication
from PyQt6.QtMultimedia import QMediaDevices, QAudioSource, QAudioDevice, QAudioFormat

from updater import CURRENT_VERSION, get_build_commit, get_full_version_string
from debug_logger import log_debug
import theme_manager

APP_DIR = os.path.join(os.environ.get("APPDATA", ""), "StreamerCalyx")


class DiagSegmentedBar(QWidget):
    """Segmented LED gauge for Audio Diagnostics live prosody display."""

    def __init__(self, active_color: str = "#22c55e", show_threshold: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self.setMinimumWidth(140)
        self.active_color = QColor(active_color)
        self.inactive_color = QColor("#222228")
        self.show_threshold = show_threshold
        self.value = 0.0
        self.threshold = 0.75

    def set_value(self, val: float, threshold: float = None):
        self.value = max(0.0, min(1.0, float(val)))
        if threshold is not None:
            self.threshold = max(0.0, min(1.0, float(threshold)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        num_seg = 36
        gap = 2
        seg_w = max(2.0, (w - (num_seg - 1) * gap) / num_seg)
        lit = int(round(self.value * num_seg))
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(num_seg):
            x = i * (seg_w + gap)
            painter.setBrush(self.active_color if i < lit else self.inactive_color)
            painter.drawRoundedRect(QRectF(x, 2, seg_w, h - 4), 2, 2)
        if self.show_threshold:
            tx = int(self.threshold * w)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(tx, 0, tx, h)


class MiniVUMeter(DiagSegmentedBar):
    """Backward-compatible alias."""
    def set_level(self, val: float):
        self.set_value(val)


class AudioDiagnosticsDialog(QDialog):
    """
    Live Prosody Calibration & X-Minute Sample Diagnostics Suite.
    """

    DURATION_OPTIONS = [
        ("15 Seconds (Quick Check)", 15),
        ("30 Seconds", 30),
        ("1 Minute", 60),
        ("2 Minutes", 120),
        ("3 Minutes", 180),
        ("5 Minutes", 300),
    ]

    def __init__(self, parent=None, overlay_app=None, engine=None):
        super().__init__(parent)
        self.overlay_app = overlay_app
        self.engine = engine
        self.setObjectName("AudioDiagnosticsDialog")
        self.setWindowTitle("🎙️ Audio Input Diagnostics & Calibration Suite")
        self.resize(740, 740)

        # Capture / Sampling State
        self.is_testing = False
        self.test_tick = 0
        self.total_ticks = 600  # updated from duration combo (20 Hz)
        self.audio_source = None
        self.audio_io = None
        self._using_engine_tap = False
        self._sample_format = None
        self._sample_rate = 48000
        self._channels = 2

        # Sample Telemetry Accumulators
        self._reset_sample_stats()
        self.report_text = ""
        self._recommended_settings = {}

        # 20 Hz poll timer for standalone QAudioSource capture
        self.timer_sample = QTimer(self)
        self.timer_sample.setInterval(50)
        self.timer_sample.timeout.connect(self._on_sample_tick)

        self._build_ui()
        self._populate_devices()

        pref = getattr(self.overlay_app, "theme_preference", "system") if self.overlay_app else "system"
        theme_manager.apply_theme_to_window(self, pref)

    def _reset_sample_stats(self):
        self.samples_level = []
        self.samples_speech_level = []
        self.samples_ambient_level = []
        self.samples_f0 = []
        self.samples_hype = []
        self.count_markers = 0
        self.count_secondary = 0
        self.count_possible = 0
        self.count_thumps = 0
        self.count_noise_ignored = 0
        self._last_possible_ts = 0.0
        self._last_thump_ts = 0.0
        self._sim_spike_start = None
        self._sim_cooldown_until = 0.0

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setSpacing(10)
        lay.setContentsMargins(4, 4, 4, 4)

        # Header
        lbl_title = QLabel("🎙️ AUDIO DIAGNOSTICS & LIVE PROSODY CALIBRATION")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        lay.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Run a live 20 Hz prosody sample test (15s–5m) to measure Markers, Cooldown Clips, "
            "Possible Moments, Desk Bumps, and Noise Ignores, then review tailored setting suggestions."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        lay.addWidget(lbl_desc)

        # Device & Sample Duration Controls
        grp_ctrl = QGroupBox("1. Sample Test Configuration")
        lay_c = QVBoxLayout(grp_ctrl)
        row_dev = QHBoxLayout()
        row_dev.addWidget(QLabel("Input Device:"))
        self.combo_device = QComboBox()
        self.combo_device.setMinimumWidth(0)
        self.combo_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_device.setMinimumContentsLength(18)
        row_dev.addWidget(self.combo_device, 1)
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.clicked.connect(self._populate_devices)
        row_dev.addWidget(self.btn_refresh)
        lay_c.addLayout(row_dev)

        row_dur = QHBoxLayout()
        row_dur.addWidget(QLabel("Sample Duration:"))
        self.combo_duration = QComboBox()
        for label, secs in self.DURATION_OPTIONS:
            self.combo_duration.addItem(label, secs)
        self.combo_duration.setCurrentIndex(2)  # Default 1 Minute
        row_dur.addWidget(self.combo_duration)

        self.btn_start_test = QPushButton("▶️ Start Sample Test")
        self.btn_start_test.setFixedHeight(32)
        self.btn_start_test.setStyleSheet(
            "QPushButton { background-color: #0284c7; color: #fff; font-weight: bold; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #0369a1; }"
        )
        self.btn_start_test.clicked.connect(self._toggle_sample_test)
        row_dur.addWidget(self.btn_start_test, 1)
        lay_c.addLayout(row_dur)

        row_prog = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        row_prog.addWidget(self.progress, 1)
        self.lbl_timer = QLabel("Idle")
        self.lbl_timer.setFixedWidth(110)
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_timer.setStyleSheet("font-family: monospace; font-weight: bold; color: #38bdf8;")
        row_prog.addWidget(self.lbl_timer)
        lay_c.addLayout(row_prog)
        lay.addWidget(grp_ctrl)

        # 2. Live Prosody Gauges (Tester Harness Style)
        grp_gauges = QGroupBox("2. Live Prosody Gauges (20 Hz DSP)")
        lay_g = QVBoxLayout(grp_gauges)
        lay_g.setSpacing(4)

        def _add_gauge(title: str, color: str, default_lbl: str, show_thresh: bool = False):
            r = QHBoxLayout()
            r.addWidget(QLabel(title))
            r.addStretch()
            lbl = QLabel(default_lbl)
            lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
            r.addWidget(lbl)
            lay_g.addLayout(r)
            bar = DiagSegmentedBar(color, show_threshold=show_thresh)
            lay_g.addWidget(bar)
            return lbl, bar

        self.lbl_g_loudness, self.bar_g_loudness = _add_gauge("Loudness (RMS/Peak):", "#eab308", "0%")
        self.lbl_g_vad, self.bar_g_vad = _add_gauge("Voice Activity (VAD):", "#22c55e", "0% (Idle)")
        self.lbl_g_f0, self.bar_g_f0 = _add_gauge("Pitch Tracking (F0):", "#a855f7", "0 Hz (Unvoiced)")
        self.lbl_g_laugh, self.bar_g_laugh = _add_gauge("Laughter Cadence (4-6Hz):", "#f97316", "0%")
        self.lbl_g_hype, self.bar_g_hype = _add_gauge("🔥 COMPOSITE HYPE SCORE:", "#ef4444", "0% [Thresh: 75%]", show_thresh=True)

        self.lbl_g_classified = QLabel("🎙️ Classified: Idle / Ambient")
        self.lbl_g_classified.setStyleSheet("color: #38bdf8; font-weight: bold; margin-top: 4px;")
        lay_g.addWidget(self.lbl_g_classified)
        lay.addWidget(grp_gauges)

        # 3. Sample Counters Grid
        grp_cnt = QGroupBox("3. Live Sample Event Counters")
        grid_cnt = QGridLayout(grp_cnt)
        self.lbl_cnt_markers = QLabel("🔥 Markers / Clips: 0")
        self.lbl_cnt_secondary = QLabel("⏱️ Cooldown Secondaries: 0")
        self.lbl_cnt_possible = QLabel("⚡ Possible Moments: 0")
        self.lbl_cnt_thumps = QLabel("🛑 Desk Bumps Rejected: 0")
        self.lbl_cnt_ignored = QLabel("🔇 Noise Ignores: 0")
        self.lbl_cnt_peaks = QLabel("📊 Avg Speech: --% | Peak: --%")
        for idx, lbl in enumerate([
            self.lbl_cnt_markers, self.lbl_cnt_secondary, self.lbl_cnt_possible,
            self.lbl_cnt_thumps, self.lbl_cnt_ignored, self.lbl_cnt_peaks
        ]):
            lbl.setStyleSheet("font-weight: bold; padding: 3px;")
            grid_cnt.addWidget(lbl, idx // 2, idx % 2)
        lay.addWidget(grp_cnt)

        # 4. Analysis, Suggestions & Report
        grp_rep = QGroupBox("4. Calibration Analysis & Setting Suggestions")
        lay_r = QVBoxLayout(grp_rep)
        self.txt_report = QTextEdit()
        self.txt_report.setReadOnly(True)
        self.txt_report.setMinimumHeight(170)
        self.txt_report.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        self.txt_report.setPlaceholderText("Run a sample test above to see event counts, acoustic stats, and recommended settings...")
        lay_r.addWidget(self.txt_report)
        lay.addWidget(grp_rep)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # Footer Buttons
        row_foot = QHBoxLayout()
        self.btn_apply_recs = QPushButton("✨ Apply Recommended Settings")
        self.btn_apply_recs.setEnabled(False)
        self.btn_apply_recs.setStyleSheet(
            "QPushButton:enabled { background-color: #16a34a; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px; }"
        )
        self.btn_apply_recs.clicked.connect(self._apply_recommendations)
        row_foot.addWidget(self.btn_apply_recs)

        self.btn_copy_report = QPushButton("📋 Copy Report")
        self.btn_copy_report.setEnabled(False)
        self.btn_copy_report.clicked.connect(self._copy_report)
        row_foot.addWidget(self.btn_copy_report)

        row_foot.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        row_foot.addWidget(btn_close)
        outer.addLayout(row_foot)

    def _populate_devices(self):
        self.combo_device.blockSignals(True)
        self.combo_device.clear()
        devices = QMediaDevices.audioInputs()
        target_name = getattr(self.engine, "selected_device_name", "") if self.engine else ""
        sel_idx = 0
        for i, d in enumerate(devices):
            desc = d.description()
            tag = " (Default)" if d.isDefault() else ""
            self.combo_device.addItem(f"{desc}{tag}", desc)
            if target_name and desc.strip() == target_name.strip():
                sel_idx = i
        if devices:
            self.combo_device.setCurrentIndex(sel_idx)
        self.combo_device.blockSignals(False)

    def _toggle_sample_test(self):
        if self.is_testing:
            self._finish_sample_test(stopped_early=True)
        else:
            self._start_sample_test()

    def _start_sample_test(self):
        dev_name = self.combo_device.currentData() or ""
        secs = int(self.combo_duration.currentData() or 60)
        self.total_ticks = secs * 20  # 50ms = 20 Hz
        self.test_tick = 0
        self._reset_sample_stats()
        self._recommended_settings = {}
        self.btn_apply_recs.setEnabled(False)
        self.btn_copy_report.setEnabled(False)
        self.txt_report.setPlainText(f"Sampling '{dev_name}' for {secs}s... Speak normally, laugh, or test desk bumps.")

        # If the main AutoClipEngine is already capturing the exact selected device, tap it directly!
        eng = self.engine
        if eng and eng.enabled and eng.audio_io and (not dev_name or dev_name.strip() == (eng.selected_device_name or "").strip()):
            self._using_engine_tap = True
            eng.dsp_telemetry_updated.connect(self._on_external_dsp_tick)
            eng.marker_triggered.connect(self._on_external_marker)
            eng.secondary_peak_logged.connect(self._on_external_secondary)
            eng.possible_peak_logged.connect(self._on_external_possible)
            self.timer_sample.start()
        else:
            self._using_engine_tap = False
            if not self._open_standalone_capture(dev_name):
                return
            self.timer_sample.start()

        self.is_testing = True
        self.combo_device.setEnabled(False)
        self.combo_duration.setEnabled(False)
        self.btn_start_test.setText("⏹️ Stop Sample Test")
        self.btn_start_test.setStyleSheet(
            "QPushButton { background-color: #dc2626; color: #fff; font-weight: bold; border-radius: 4px; padding: 4px 12px; }"
        )

    def _open_standalone_capture(self, dev_name: str) -> bool:
        devices = QMediaDevices.audioInputs()
        target_dev = next((d for d in devices if d.description().strip() == dev_name.strip()), None)
        if not target_dev:
            target_dev = QMediaDevices.defaultAudioInput()
        if not target_dev or target_dev.isNull():
            QMessageBox.warning(self, "No Audio Device", "No valid audio input device found.")
            return False

        fmt = target_dev.preferredFormat()
        self._sample_format = fmt.sampleFormat()
        self._sample_rate = fmt.sampleRate() or 48000
        self._channels = fmt.channelCount() or 2

        try:
            self.audio_source = QAudioSource(target_dev, fmt, self)
            self.audio_io = self.audio_source.start()
            if not self.audio_io:
                QMessageBox.warning(self, "Audio Error", f"Could not open audio stream on '{target_dev.description()}'.")
                return False
            return True
        except Exception as e:
            QMessageBox.warning(self, "Audio Error", f"Failed to start capture: {e}")
            return False

    def _on_sample_tick(self):
        if not self.is_testing:
            return
        self.test_tick += 1
        pct = min(100, int((self.test_tick / max(1, self.total_ticks)) * 100))
        self.progress.setValue(pct)
        rem_sec = max(0, int((self.total_ticks - self.test_tick) / 20))
        self.lbl_timer.setText(f"{rem_sec // 60:02d}:{rem_sec % 60:02d} left")

        if not self._using_engine_tap and self.audio_io:
            raw = self.audio_io.readAll().data()
            if raw:
                self._process_standalone_pcm(raw)

        if self.test_tick >= self.total_ticks:
            self._finish_sample_test(stopped_early=False)

    def _process_standalone_pcm(self, raw_bytes: bytes):
        # Reuse AutoClipEngine's exact vectorized DSP if available
        if self.engine:
            old_fmt, old_sr, old_ch = self.engine._sample_format, self.engine._sample_rate, self.engine._channels
            self.engine._sample_format = self._sample_format
            self.engine._sample_rate = self._sample_rate
            self.engine._channels = self._channels
            dsp = self.engine._analyze_audio_frame(raw_bytes)
            self.engine._sample_format, self.engine._sample_rate, self.engine._channels = old_fmt, old_sr, old_ch
        else:
            dsp = {"level": 0.0, "vocal_vad": False, "vad_confidence": 0.0, "f0_hz": 0.0, "f0_ratio": 1.0,
                   "laughter_cadence": 0.0, "composite_hype": 0.0, "thump_rejected": False}

        self._record_dsp_frame(dsp)

        # Simulate threshold/event counters using current engine thresholds
        lvl = float(dsp.get("level", 0.0))
        thresh = float(getattr(self.engine, "current_threshold", 0.70) if self.engine else 0.70)
        orange_thresh = thresh * 0.78
        min_dur = int(getattr(self.engine, "min_duration_ms", 250) if self.engine else 250)
        cd_sec = int(getattr(self.engine, "cooldown_duration_sec", 60) if self.engine else 60)
        now = time.time()

        if lvl >= thresh:
            if self._sim_spike_start is None:
                self._sim_spike_start = now
            elif (now - self._sim_spike_start) * 1000.0 >= min_dur:
                self._sim_spike_start = None
                if now >= self._sim_cooldown_until:
                    self.count_markers += 1
                    self._sim_cooldown_until = now + cd_sec
                else:
                    self.count_secondary += 1
                    self._sim_cooldown_until = max(self._sim_cooldown_until, now)
        else:
            self._sim_spike_start = None
            if lvl >= orange_thresh and (now - self._last_possible_ts) >= 5.0:
                self._last_possible_ts = now
                self.count_possible += 1

        self._refresh_counter_labels()

    def _on_external_dsp_tick(self, dsp: dict):
        if self.is_testing:
            self._record_dsp_frame(dsp)
            self._refresh_counter_labels()

    def _on_external_marker(self, _payload: dict):
        if self.is_testing:
            self.count_markers += 1
            self._refresh_counter_labels()

    def _on_external_secondary(self, _payload: dict):
        if self.is_testing:
            self.count_secondary += 1
            self._refresh_counter_labels()

    def _on_external_possible(self, _payload: dict):
        if self.is_testing:
            self.count_possible += 1
            self._refresh_counter_labels()

    def _record_dsp_frame(self, dsp: dict):
        lvl = float(dsp.get("level", 0.0))
        vad = bool(dsp.get("vocal_vad", False))
        vad_c = float(dsp.get("vad_confidence", 0.0))
        f0 = float(dsp.get("f0_hz", 0.0))
        laugh = float(dsp.get("laughter_cadence", 0.0))
        hype = float(dsp.get("composite_hype", 0.0))
        thump = bool(dsp.get("thump_rejected", False))
        thresh = float(getattr(self.engine, "current_threshold", 0.70) if self.engine else 0.70)

        self.samples_level.append(lvl)
        self.samples_hype.append(hype)
        if vad:
            self.samples_speech_level.append(lvl)
            if f0 > 0:
                self.samples_f0.append(f0)
        else:
            self.samples_ambient_level.append(lvl)
            if not thump:
                self.count_noise_ignored += 1

        now = time.time()
        if thump and (now - self._last_thump_ts) >= 1.5:
            self._last_thump_ts = now
            self.count_thumps += 1

        # Update Live Gauges
        self.bar_g_loudness.set_value(lvl)
        self.lbl_g_loudness.setText(f"{int(round(lvl * 100))}%")

        self.bar_g_vad.set_value(vad_c if vad else 0.0)
        self.lbl_g_vad.setText(f"{int(round(vad_c * 100))}% (Human Voice)" if vad else "0% (Idle)")

        self.bar_g_f0.set_value(min(1.0, f0 / 550.0) if f0 > 0 else 0.0)
        self.lbl_g_f0.setText(f"{f0:.0f} Hz ({dsp.get('f0_ratio', 1.0):.2f}x)" if f0 > 0 else "0 Hz (Unvoiced)")

        self.bar_g_laugh.set_value(laugh)
        self.lbl_g_laugh.setText(f"{int(round(laugh * 100))}%")

        self.bar_g_hype.set_value(hype, thresh)
        self.lbl_g_hype.setText(f"{int(round(hype * 100))}% [Thresh: {int(round(thresh * 100))}%]")

        if thump:
            self.lbl_g_classified.setText("🎙️ Classified: 🛑 Desk Bump / Sub-Bass Rejected")
        elif vad and self.engine:
            icon, label, _ = self.engine.classify_vocal_reaction(
                lvl, f0, dsp.get("f0_ratio", 1.0), laugh, dsp.get("banter_cadence", 0.0), dsp.get("crest_factor", 1.0)
            )
            self.lbl_g_classified.setText(f"🎙️ Classified: {icon} {label}")
        else:
            self.lbl_g_classified.setText("🎙️ Classified: Idle / Ambient")

    def _refresh_counter_labels(self):
        self.lbl_cnt_markers.setText(f"🔥 Markers / Clips: {self.count_markers}")
        self.lbl_cnt_secondary.setText(f"⏱️ Cooldown Secondaries: {self.count_secondary}")
        self.lbl_cnt_possible.setText(f"⚡ Possible Moments: {self.count_possible}")
        self.lbl_cnt_thumps.setText(f"🛑 Desk Bumps Rejected: {self.count_thumps}")
        self.lbl_cnt_ignored.setText(f"🔇 Noise Ignores: {self.count_noise_ignored}")
        avg_sp = int(round((sum(self.samples_speech_level) / len(self.samples_speech_level)) * 100)) if self.samples_speech_level else 0
        pk = int(round(max(self.samples_level) * 100)) if self.samples_level else 0
        self.lbl_cnt_peaks.setText(f"📊 Avg Speech: {avg_sp}% | Peak: {pk}%")

    def _finish_sample_test(self, stopped_early: bool = False):
        self.timer_sample.stop()
        self.is_testing = False

        if self._using_engine_tap and self.engine:
            for sig, slot in [
                (self.engine.dsp_telemetry_updated, self._on_external_dsp_tick),
                (self.engine.marker_triggered, self._on_external_marker),
                (self.engine.secondary_peak_logged, self._on_external_secondary),
                (self.engine.possible_peak_logged, self._on_external_possible),
            ]:
                try:
                    sig.disconnect(slot)
                except Exception:
                    pass
        if self.audio_source:
            try:
                self.audio_source.stop()
            except Exception:
                pass
            self.audio_source = None
            self.audio_io = None

        self.combo_device.setEnabled(True)
        self.combo_duration.setEnabled(True)
        self.btn_start_test.setText("▶️ Start Sample Test")
        self.btn_start_test.setStyleSheet(
            "QPushButton { background-color: #0284c7; color: #fff; font-weight: bold; border-radius: 4px; padding: 4px 12px; }"
        )
        self.progress.setValue(100 if not stopped_early else self.progress.value())
        self.lbl_timer.setText("Stopped" if stopped_early else "Complete")

        self._generate_analysis_report()

    def _generate_analysis_report(self):
        elapsed_sec = max(1, int(self.test_tick / 20))
        dev_name = self.combo_device.currentData() or "Default"
        avg_amb = (sum(self.samples_ambient_level) / len(self.samples_ambient_level)) if self.samples_ambient_level else 0.0
        avg_sp = (sum(self.samples_speech_level) / len(self.samples_speech_level)) if self.samples_speech_level else 0.0
        peak_lvl = max(self.samples_level) if self.samples_level else 0.0
        med_f0 = sorted(self.samples_f0)[len(self.samples_f0) // 2] if self.samples_f0 else 0.0

        recs = []
        self._recommended_settings = {}

        if avg_amb >= 0.22:
            recs.append(f"- High ambient noise floor ({int(avg_amb*100)}%): lower Input Gain Trim to 90% or raise Trigger Offset to +36%.")
            self._recommended_settings["input_gain"] = 0.90
            self._recommended_settings["trigger_offset"] = 0.36
        elif peak_lvl < 0.45 and self.samples_speech_level:
            recs.append(f"- Quiet peak levels (max {int(peak_lvl*100)}%): raise Input Gain Trim to 125% so reactions reach the Red zone.")
            self._recommended_settings["input_gain"] = 1.25

        if self.count_markers == 0 and peak_lvl >= 0.45:
            new_off = max(0.22, round((peak_lvl - max(0.30, avg_sp)) * 0.85, 2))
            recs.append(f"- 0 Markers triggered during test (Peak {int(peak_lvl*100)}%): try Trigger Offset +{int(new_off*100)}% for more sensitivity.")
            self._recommended_settings["trigger_offset"] = new_off
        elif (self.count_markers + self.count_possible) / max(0.5, elapsed_sec / 60.0) > 5.0:
            recs.append("- High trigger rate (>5/min): raise Trigger Offset (+35%) or Min Peak Duration (350ms) to avoid chatty triggers.")
            self._recommended_settings["trigger_offset"] = 0.35
            self._recommended_settings["min_duration_ms"] = 350

        if self.count_thumps >= 2:
            recs.append(f"- Detected {self.count_thumps} desk bumps/mic thumps: raise Desk Thump Filter to 75%.")
            self._recommended_settings["desk_thump_sensitivity"] = 0.75

        if med_f0 > 0:
            if med_f0 < 140:
                recs.append(f"- Median speech F0 = {med_f0:.0f} Hz: Deep Voice profile fits well (or keep Dynamic Auto-Adapt).")
            elif med_f0 > 205:
                recs.append(f"- Median speech F0 = {med_f0:.0f} Hz: High/Expressive profile fits well (or keep Dynamic Auto-Adapt).")
            else:
                recs.append(f"- Median speech F0 = {med_f0:.0f} Hz: Mid/Conversational range detected.")

        if not recs:
            recs.append("- Levels and thresholds look well balanced! No changes needed.")

        lines = [
            f"=== Streamer Calyx Audio Calibration Report ({get_full_version_string()}) ===",
            f"Device: {dev_name} | Sample Duration: {elapsed_sec}s",
            f"Events: Markers={self.count_markers}, CooldownClips={self.count_secondary}, "
            f"Possible={self.count_possible}, DeskBumps={self.count_thumps}, NoiseIgnores={self.count_noise_ignored}",
            f"Acoustic Stats: Ambient={int(avg_amb*100)}%, AvgSpeech={int(avg_sp*100)}%, Peak={int(peak_lvl*100)}%, MedianF0={med_f0:.0f}Hz",
            "",
            "Suggestions:",
            *recs,
        ]
        self.report_text = "\n".join(lines)
        self.txt_report.setPlainText(self.report_text)
        self.btn_copy_report.setEnabled(True)
        self.btn_apply_recs.setEnabled(bool(self._recommended_settings))

    def _apply_recommendations(self):
        if not self.engine or not self._recommended_settings:
            return
        for k, v in self._recommended_settings.items():
            if hasattr(self.engine, k):
                setattr(self.engine, k, v)
        if self.overlay_app and hasattr(self.overlay_app, "save_settings"):
            self.overlay_app.save_settings()
        QMessageBox.information(self, "Settings Applied", "Recommended calibration settings have been applied and saved!")
        self.btn_apply_recs.setEnabled(False)

    def _copy_report(self):
        if self.report_text:
            QGuiApplication.clipboard().setText(self.report_text)
            QMessageBox.information(self, "Copied", "Calibration report copied to clipboard.")

    def closeEvent(self, event):
        if self.is_testing:
            self._finish_sample_test(stopped_early=True)
        super().closeEvent(event)
