import time
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QColor

try:
    from debug_logger import log_debug
except ImportError:
    def log_debug(tag, msg):
        print(f"[{tag}] {msg}")


IFTTT_TRIGGERS = [
    ("deorbit_started", "☄️ De-Orbit Sequence Starts"),
    ("deorbit_completed", "🏁 De-Orbit Countdown Completes"),
    ("stream_started", "🚀 Broadcast Goes Live"),
    ("stream_ended", "⏹️ Broadcast Goes Offline"),
    ("scene_switched", "🎬 SLOBS Switches to Scene..."),
    ("autoclip_peak", "🔥 Auto-Clip Primary Peak Triggered"),
    ("recording_started", "🔴 Local Recording Started"),
]

IFTTT_ACTIONS = [
    ("switch_scene", "🎬 Switch SLOBS Scene"),
    ("mute_mic", "🔇 Mute Audio Source"),
    ("unmute_mic", "🎙️ Unmute Audio Source"),
    ("save_replay", "💾 Save Replay Buffer"),
    ("send_twitch_chat", "💬 Send Twitch Chat Message"),
    ("flash_border", "⚡ Flash Monitor Border Alert"),
    ("play_chime", "🔔 Play Marker Chime"),
    ("log_moment", "📝 Log Offline Moment"),
    ("stop_stream", "⏹️ Stop Broadcast Stream"),
]


class IFTTTRuleEngine(QObject):
    """
    Universal 'If This, Then That' (IFTTT) automation engine for Streamer Calyx.
    Evaluates user-configured trigger -> action rules on live broadcast events.
    """

    rule_executed = pyqtSignal(dict)

    def __init__(self, overlay=None, slobs_client=None, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.slobs_client = slobs_client
        self.rules = []  # List of {"id", "name", "enabled", "trigger", "trigger_param", "action", "action_param"}

    def load_rules(self, rules_list: list):
        if isinstance(rules_list, list):
            self.rules = [dict(r) for r in rules_list if isinstance(r, dict)]

    def export_rules(self) -> list:
        return [dict(r) for r in self.rules]

    def fire_trigger(self, trigger_id: str, context_param: str = ""):
        """Evaluates all enabled rules matching trigger_id and executes their action."""
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("trigger") != trigger_id:
                continue
            t_param = (rule.get("trigger_param") or "").strip().lower()
            if trigger_id == "scene_switched" and t_param:
                if t_param not in (context_param or "").strip().lower():
                    continue
            self._execute_action(rule)

    def _execute_action(self, rule: dict):
        act = rule.get("action", "")
        param = (rule.get("action_param") or "").strip()
        log_debug("IFTTT", f"Executing rule '{rule.get('name', act)}': {rule.get('trigger')} -> {act}({param})")

        slobs = self.slobs_client
        ov = self.overlay

        try:
            if act == "switch_scene" and param and slobs and slobs.is_connected():
                slobs.make_scene_active(param)
            elif act == "mute_mic" and param and slobs and slobs.is_connected():
                slobs.set_audio_muted(param, True)
            elif act == "unmute_mic" and param and slobs and slobs.is_connected():
                slobs.set_audio_muted(param, False)
            elif act == "save_replay" and slobs and slobs.is_connected():
                slobs.save_replay_buffer()
            elif act == "stop_stream" and slobs and slobs.is_connected():
                slobs._call_rpc("stopStreaming", "StreamingService")
            elif act == "send_twitch_chat" and param and ov and getattr(ov, "twitch_token", ""):
                ov.dispatch_twitch_call(param, "")
            elif act == "flash_border" and ov and hasattr(ov, "flash_temporary_alert"):
                col = QColor(param) if param.startswith("#") else QColor("#9146ff")
                ov.flash_temporary_alert(duration_ms=1200, color=col)
            elif act == "play_chime" and ov and getattr(ov, "soundboard_engine", None):
                ov.soundboard_engine.play_marker_chime()
            elif act == "log_moment" and ov and getattr(ov, "moments_logger", None):
                ov.moments_logger.log_moment(description=param or "IFTTT Rule Triggered", source="IFTTT")
            self.rule_executed.emit(dict(rule))
        except Exception as e:
            log_debug("IFTTT_ERR", f"Error executing IFTTT action '{act}': {e}")


class DeOrbitSequenceEngine(QObject):
    """
    Phase 11 Automated 'De-Orbit' Stream Shutdown Sequence with Safety Abort Window.
    """

    deorbit_started = pyqtSignal(int)       # total_seconds
    deorbit_tick = pyqtSignal(int, int)     # remaining_seconds, total_seconds
    deorbit_completed = pyqtSignal()
    deorbit_aborted = pyqtSignal()

    def __init__(self, overlay=None, slobs_client=None, ifttt_engine: IFTTTRuleEngine = None, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.slobs_client = slobs_client
        self.ifttt_engine = ifttt_engine

        # Configurable De-Orbit Settings
        self.countdown_seconds = 60
        self.outro_scene_name = "Stream Ending"
        self.mute_mics = True
        self.start_credits_cycler = True
        self.stop_stream_on_finish = True
        self.farewell_chat_message = ""

        # Active State
        self.is_active = False
        self.remaining_seconds = 0
        self._muted_sources = []

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def start_deorbit(self):
        if self.is_active:
            return
        self.is_active = True
        self.remaining_seconds = max(5, int(self.countdown_seconds))
        self._muted_sources = []
        log_debug("DEORBIT", f"Initiating De-Orbit sequence ({self.remaining_seconds}s countdown).")

        # 1. Switch SLOBS to Outro / Ending scene
        if self.outro_scene_name and self.slobs_client and self.slobs_client.is_connected():
            try:
                self.slobs_client.make_scene_active(self.outro_scene_name)
                log_debug("DEORBIT", f"Switched scene to '{self.outro_scene_name}'.")
            except Exception as e:
                log_debug("DEORBIT", f"Scene switch error: {e}")

        # 2. Trigger Ending Credits / Text Scroller (CyclerEngine)
        if self.start_credits_cycler and self.overlay and getattr(self.overlay, "cycler_engine", None):
            try:
                self.overlay.cycler_engine.start()
                log_debug("DEORBIT", "Started CyclerEngine for ending scroller/credits.")
            except Exception as e:
                log_debug("DEORBIT", f"Cycler start error: {e}")

        # 3. Mute open microphones to protect backstage privacy
        if self.mute_mics and self.slobs_client and self.slobs_client.is_connected():
            self._mute_open_mics()

        # 4. Optional farewell Twitch chat message
        if self.farewell_chat_message and self.overlay and getattr(self.overlay, "twitch_token", ""):
            try:
                self.overlay.dispatch_twitch_call(self.farewell_chat_message, "")
            except Exception:
                pass

        # 5. Fire IFTTT rules for deorbit_started
        if self.ifttt_engine:
            self.ifttt_engine.fire_trigger("deorbit_started")

        if self.overlay and hasattr(self.overlay, "show_hud_toast"):
            self.overlay.show_hud_toast(f"☄️ DE-ORBIT INITIATED! Ending stream in {self.remaining_seconds}s...", True)

        self.deorbit_started.emit(self.countdown_seconds)
        self.deorbit_tick.emit(self.remaining_seconds, self.countdown_seconds)
        self._timer.start()

    def _mute_open_mics(self):
        try:
            sources = self.slobs_client.get_audio_sources()
            for src in sources:
                name = (src.get("name") or "").strip()
                low = name.lower()
                if any(k in low for k in ("mic", "aux", "voice", "podcast", "headset")) and not src.get("muted", False):
                    rid = src.get("resourceId") or src.get("id") or name
                    if self.slobs_client.set_audio_muted(rid, True):
                        self._muted_sources.append(rid)
                        log_debug("DEORBIT", f"Muted microphone '{name}' for privacy.")
        except Exception as e:
            log_debug("DEORBIT", f"Error muting mics: {e}")

    def _on_tick(self):
        if not self.is_active:
            self._timer.stop()
            return
        self.remaining_seconds -= 1
        self.deorbit_tick.emit(max(0, self.remaining_seconds), self.countdown_seconds)
        if self.remaining_seconds <= 0:
            self._complete_deorbit()

    def _complete_deorbit(self):
        self._timer.stop()
        self.is_active = False
        log_debug("DEORBIT", "De-Orbit countdown completed! Stopping broadcast.")

        if self.stop_stream_on_finish and self.slobs_client and self.slobs_client.is_connected():
            try:
                self.slobs_client._call_rpc("stopStreaming", "StreamingService")
                log_debug("DEORBIT", "Dispatched stopStreaming to Streamlabs StreamingService.")
            except Exception as e:
                log_debug("DEORBIT", f"Error stopping stream: {e}")

        if self.ifttt_engine:
            self.ifttt_engine.fire_trigger("deorbit_completed")

        if self.overlay and hasattr(self.overlay, "show_hud_toast"):
            self.overlay.show_hud_toast("🏁 DE-ORBIT COMPLETE — Broadcast ended safely.", True)

        self.deorbit_completed.emit()

    def abort_deorbit(self):
        if not self.is_active:
            return
        self._timer.stop()
        self.is_active = False
        log_debug("DEORBIT", "🛑 DE-ORBIT ABORTED by user!")

        # Unmute mics that De-Orbit muted
        if self._muted_sources and self.slobs_client and self.slobs_client.is_connected():
            for rid in self._muted_sources:
                try:
                    self.slobs_client.set_audio_muted(rid, False)
                except Exception:
                    pass
        self._muted_sources.clear()

        if self.overlay and hasattr(self.overlay, "flash_temporary_alert"):
            self.overlay.flash_temporary_alert(duration_ms=1000, color=QColor("#ef4444"))
        if self.overlay and hasattr(self.overlay, "show_hud_toast"):
            self.overlay.show_hud_toast("🛑 DE-ORBIT ABORTED — Broadcast remains live.", True)

        self.deorbit_aborted.emit()

    def export_settings(self) -> dict:
        return {
            "countdown_seconds": self.countdown_seconds,
            "outro_scene_name": self.outro_scene_name,
            "mute_mics": self.mute_mics,
            "start_credits_cycler": self.start_credits_cycler,
            "stop_stream_on_finish": self.stop_stream_on_finish,
            "farewell_chat_message": self.farewell_chat_message,
        }

    def import_settings(self, d: dict):
        if not isinstance(d, dict):
            return
        self.countdown_seconds = int(d.get("countdown_seconds", 60))
        self.outro_scene_name = d.get("outro_scene_name", "Stream Ending")
        self.mute_mics = bool(d.get("mute_mics", True))
        self.start_credits_cycler = bool(d.get("start_credits_cycler", True))
        self.stop_stream_on_finish = bool(d.get("stop_stream_on_finish", True))
        self.farewell_chat_message = str(d.get("farewell_chat_message", ""))
