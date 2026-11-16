from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QRadioButton, QButtonGroup,
    QComboBox, QFrame
)
from PyQt6.QtGui import QGuiApplication
import theme_manager
from debug_logger import log_debug


class SetupWizardDialog(QDialog):
    """
    First-Run Interactive Setup Wizard (Phase 8.5).
    Guides new users through Broadcast Mode, Multi-Monitor Selection,
    Audio Device Routing, and Streamlabs/OBS Handshake verification.
    Re-launchable anytime from System & Settings.
    """

    def __init__(self, settings_win, parent=None):
        super().__init__(parent or settings_win)
        self.settings_win = settings_win
        self.overlay = getattr(settings_win, "overlay", None)

        self.setWindowTitle("Streamer Calyx — First-Run Setup Wizard")
        self.setMinimumSize(540, 420)
        self.resize(580, 450)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        self.lbl_step_badge = QLabel("STEP 1 OF 4")
        self.lbl_step_badge.setStyleSheet(
            "background-color: #9146ff; color: white; font-size: 11px; "
            "font-weight: bold; padding: 3px 10px; border-radius: 4px;"
        )
        hdr.addWidget(self.lbl_step_badge)
        self.lbl_step_title = QLabel("<b>Welcome to Streamer Calyx</b>")
        self.lbl_step_title.setStyleSheet("font-size: 15px;")
        hdr.addWidget(self.lbl_step_title, 1)
        root.addLayout(hdr)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #3f3f46;")
        root.addWidget(div)

        # Pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_step_mode())
        self.stack.addWidget(self._build_step_monitors())
        self.stack.addWidget(self._build_step_audio())
        self.stack.addWidget(self._build_step_slobs())
        root.addWidget(self.stack, 1)

        # Footer Navigation
        nav = QHBoxLayout()
        self.btn_skip = QPushButton("Skip Wizard")
        self.btn_skip.setToolTip("Close the setup wizard without making further changes.")
        self.btn_skip.clicked.connect(self._on_finish)
        nav.addWidget(self.btn_skip)

        nav.addStretch()

        self.btn_back = QPushButton("◀ Back")
        self.btn_back.setToolTip("Return to the previous setup step.")
        self.btn_back.clicked.connect(self._go_back)
        nav.addWidget(self.btn_back)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setStyleSheet(
            "background-color: #9146ff; color: white; font-weight: bold; "
            "padding: 6px 18px; border-radius: 4px;"
        )
        self.btn_next.setToolTip("Proceed to the next setup step.")
        self.btn_next.clicked.connect(self._go_next)
        nav.addWidget(self.btn_next)

        root.addLayout(nav)

        self._update_nav_ui()
        try:
            pref = getattr(self.overlay, "theme_preference", "system")
            theme_manager.apply_theme_to_window(self, pref)
        except Exception:
            pass

    def _build_step_mode(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)

        intro = QLabel(
            "Let's get <b>Streamer Calyx</b> tailored to your setup in under 60 seconds.<br><br>"
            "First, how do you plan to use Calyx primarily?"
        )
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.mode_group = QButtonGroup(self)
        self.rad_streamer = QRadioButton("🎙️ Live Streamer Mode (Recommended for Twitch / OBS / SLOBS)")
        self.rad_streamer.setToolTip("Enables Stream Director, Auto-Clip markers, Launchpad, and Twitch integration.")
        self.rad_local = QRadioButton("🖥️ Local / Offline Mode (Border Alerts, Timers & Soundboard Only)")
        self.rad_local.setToolTip("Keeps background Twitch & audio capture idle until you turn Streamer Mode on.")

        is_streamer = bool(getattr(self.overlay, "streamer_mode", True))
        self.rad_streamer.setChecked(is_streamer)
        self.rad_local.setChecked(not is_streamer)

        self.mode_group.addButton(self.rad_streamer)
        self.mode_group.addButton(self.rad_local)

        lay.addWidget(self.rad_streamer)
        lbl_s_desc = QLabel("    <i>Activates Auto-Clip audio monitoring, Stream Director remote co-host tools, and Launchpad.</i>")
        lbl_s_desc.setWordWrap(True)
        lbl_s_desc.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        lay.addWidget(lbl_s_desc)

        lay.addSpacing(4)
        lay.addWidget(self.rad_local)
        lbl_l_desc = QLabel("    <i>Ideal for offline desktop alerts, Chronos timers, and standalone soundboard playback.</i>")
        lbl_l_desc.setWordWrap(True)
        lbl_l_desc.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        lay.addWidget(lbl_l_desc)

        lay.addStretch()
        return page

    def _build_step_monitors(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        lbl = QLabel(
            "Select which physical monitor should display your <b>Border Alert Overlay</b>:"
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        self.combo_wiz_monitor = QComboBox()
        self.combo_wiz_monitor.setToolTip("Choose the monitor where the highlight border will flash.")
        screens = QGuiApplication.screens()
        cur_idx = getattr(self.overlay, "monitor_index", 0)
        for i, scr in enumerate(screens):
            geom = scr.geometry()
            dpr = scr.devicePixelRatio()
            self.combo_wiz_monitor.addItem(
                f"Monitor {i + 1}: {scr.name()} ({geom.width()}x{geom.height()} @ {int(dpr * 100)}% DPI)",
                i
            )
        if 0 <= cur_idx < self.combo_wiz_monitor.count():
            self.combo_wiz_monitor.setCurrentIndex(cur_idx)
        lay.addWidget(self.combo_wiz_monitor)

        btn_flash = QPushButton("⚡ Test Flash Selected Monitor")
        btn_flash.setToolTip("Temporarily flash the border overlay on the selected monitor to confirm placement.")
        btn_flash.clicked.connect(self._test_flash_monitor)
        lay.addWidget(btn_flash)

        lbl_note = QLabel(
            "<i>Note: You can fine-tune border thickness, color, and Per-Monitor DPI mode anytime under "
            "<b>System & Settings → Monitor Setup</b>.</i>"
        )
        lbl_note.setWordWrap(True)
        lbl_note.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        lay.addWidget(lbl_note)

        lay.addStretch()
        return page

    def _build_step_audio(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        lbl = QLabel(
            "Choose your default <b>Input Microphone / VoiceMeeter Channel</b> and <b>Soundboard Output</b>:"
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        lay.addWidget(QLabel("<b>Broadcast Input Device (Auto-Clip):</b>"))
        self.combo_wiz_in = QComboBox()
        self.combo_wiz_in.setToolTip("Select your primary mic or VoiceMeeter B3 output.")
        ac_eng = getattr(self.overlay, "auto_clip_engine", None)
        if ac_eng:
            cur_in = (getattr(ac_eng, "selected_device_name", "") or "").strip()
            sel = 0
            for i, d in enumerate(ac_eng.get_available_devices()):
                desc = d.description() if hasattr(d, "description") else (d.get("description", "") if isinstance(d, dict) else str(d))
                self.combo_wiz_in.addItem(desc, desc)
                if cur_in and desc.strip() == cur_in:
                    sel = i
            self.combo_wiz_in.setCurrentIndex(sel)
        else:
            self.combo_wiz_in.addItem("Default System Microphone", "")
        lay.addWidget(self.combo_wiz_in)

        lay.addSpacing(6)
        lay.addWidget(QLabel("<b>Soundboard Playback Output Device:</b>"))
        self.combo_wiz_out = QComboBox()
        self.combo_wiz_out.setToolTip("Select where soundboard clips and audio cues play.")
        self.combo_wiz_out.addItem("🔊 System Default Audio Device", "")
        sb_eng = getattr(self.overlay, "soundboard_engine", None)
        if sb_eng:
            cur_out = getattr(sb_eng, "selected_device_name", "") or ""
            sel_out = 0
            for idx, dev_name in enumerate(sb_eng.get_output_devices(), start=1):
                self.combo_wiz_out.addItem(f"🎧 {dev_name}", dev_name)
                if dev_name == cur_out:
                    sel_out = idx
            self.combo_wiz_out.setCurrentIndex(sel_out)
        lay.addWidget(self.combo_wiz_out)

        lay.addStretch()
        return page

    def _build_step_slobs(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        lbl = QLabel(
            "Streamer Calyx connects directly to <b>Streamlabs Desktop</b> or <b>OBS Studio</b> "
            "for scene switching, audio faders, and Launchpad automation."
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        self.btn_test_slobs = QPushButton("🔌 Test OBS / Streamlabs Connection")
        self.btn_test_slobs.setStyleSheet(
            "background-color: #0284c7; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
        )
        self.btn_test_slobs.setToolTip("Check if Streamlabs Desktop or OBS Studio WebSocket is currently reachable.")
        self.btn_test_slobs.clicked.connect(self._test_slobs_conn)
        lay.addWidget(self.btn_test_slobs)

        self.lbl_slobs_res = QLabel("Status: Not tested yet (make sure SLOBS or OBS is open if testing now).")
        self.lbl_slobs_res.setWordWrap(True)
        self.lbl_slobs_res.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        lay.addWidget(self.lbl_slobs_res)

        lay.addSpacing(8)
        lbl_done = QLabel(
            "Click <b>Finish Setup</b> below to save your preferences and jump straight into Mission Control!"
        )
        lbl_done.setWordWrap(True)
        lay.addWidget(lbl_done)

        lay.addStretch()
        return page

    def _test_flash_monitor(self):
        idx = self.combo_wiz_monitor.currentData()
        if idx is not None and self.overlay:
            self.overlay.target_monitor_index = idx
            if hasattr(self.overlay, "update_monitor_geometry"):
                self.overlay.update_monitor_geometry(idx)
            if hasattr(self.overlay, "flash_temporary_alert"):
                color = getattr(self.overlay, "border_color", None)
                self.overlay.flash_temporary_alert(duration_ms=2000, color=color)

    def _test_slobs_conn(self):
        try:
            from streamlabs_client import get_streamlabs_client
            client = get_streamlabs_client()
            if client and getattr(client, "is_connected", False):
                self.lbl_slobs_res.setText("🟢 Connected! Streamlabs / OBS bridge is active and ready.")
                self.lbl_slobs_res.setStyleSheet("font-size: 12px; color: #22c55e; font-weight: bold;")
            elif client and hasattr(client, "connect"):
                ok = client.connect()
                if ok:
                    self.lbl_slobs_res.setText("🟢 Connected! Handshake succeeded.")
                    self.lbl_slobs_res.setStyleSheet("font-size: 12px; color: #22c55e; font-weight: bold;")
                else:
                    self.lbl_slobs_res.setText("🟡 Not reachable right now — make sure SLOBS/OBS is running, or configure it later in Stream Director.")
                    self.lbl_slobs_res.setStyleSheet("font-size: 12px; color: #eab308;")
            else:
                self.lbl_slobs_res.setText("🟡 Client ready; open SLOBS/OBS anytime to pair automatically.")
        except Exception as e:
            self.lbl_slobs_res.setText(f"🟡 Could not verify right now ({e}). You can pair anytime in Stream Director.")

    def _update_nav_ui(self):
        idx = self.stack.currentIndex()
        titles = [
            "Welcome & Broadcast Mode",
            "Display & Multi-Monitor Setup",
            "Audio Devices & Routing",
            "Streamlabs / OBS Handshake"
        ]
        self.lbl_step_badge.setText(f"STEP {idx + 1} OF {self.stack.count()}")
        self.lbl_step_title.setText(f"<b>{titles[idx]}</b>")
        self.btn_back.setEnabled(idx > 0)
        if idx == self.stack.count() - 1:
            self.btn_next.setText("✅ Finish Setup")
        else:
            self.btn_next.setText("Next ▶")

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_nav_ui()

    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx < self.stack.count() - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._update_nav_ui()
        else:
            self._on_finish()

    def _on_finish(self):
        try:
            # Apply Mode
            is_streamer = self.rad_streamer.isChecked()
            if hasattr(self.settings_win, "tab_main") and hasattr(self.settings_win.tab_main, "chk_streamer"):
                self.settings_win.tab_main.chk_streamer.setChecked(is_streamer)
            elif self.overlay:
                self.overlay.streamer_mode = is_streamer

            # Apply Monitor
            mon_idx = self.combo_wiz_monitor.currentData()
            if mon_idx is not None and self.overlay:
                self.overlay.target_monitor_index = mon_idx
                if hasattr(self.overlay, "update_monitor_geometry"):
                    self.overlay.update_monitor_geometry(mon_idx)
                if hasattr(self.settings_win, "tab_monitor"):
                    self.settings_win.tab_monitor.refresh_monitors()

            # Apply Audio
            in_dev = self.combo_wiz_in.currentData()
            ac_eng = getattr(self.overlay, "auto_clip_engine", None)
            if in_dev and ac_eng:
                ac_eng.set_device_by_name(in_dev)
            out_dev = self.combo_wiz_out.currentData()
            sb_eng = getattr(self.overlay, "soundboard_engine", None)
            if sb_eng is not None and out_dev is not None:
                sb_eng.set_output_device(out_dev)
            if hasattr(self.settings_win, "tab_audio"):
                self.settings_win.tab_audio.refresh_devices()

            if self.overlay:
                self.overlay.setup_wizard_completed = True
                if hasattr(self.overlay, "save_settings"):
                    self.overlay.save_settings()
        except Exception as e:
            log_debug("ERROR", f"SetupWizard apply error: {e}")
        self.accept()
