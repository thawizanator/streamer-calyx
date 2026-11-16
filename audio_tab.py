from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSlider, QGroupBox, QScrollArea, QFrame, QSizePolicy
)
from debug_logger import log_debug


class AudioTab(QWidget):
    """
    Master Audio Devices & Routing Tab (Phase 8).
    Centralizes WASAPI microphone/capture input selection, input gain trim,
    soundboard/alert output device routing, master output volume, and
    quick access to the Audio Input Diagnostics suite.
    Keeps settings synchronized two-way with AutoClipTab and SoundboardTab.
    """

    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self.main_win = main_win
        self.overlay = getattr(main_win, "overlay", None)
        self.auto_clip_engine = getattr(self.overlay, "auto_clip_engine", None)
        self.soundboard_engine = getattr(self.overlay, "soundboard_engine", None)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root_layout.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(10)

        # Header intro
        self.lbl_intro = QLabel(
            "Configure your primary broadcast microphone, VoiceMeeter virtual channels, "
            "and soundboard/alert audio output routing in one unified location."
        )
        self.lbl_intro.setWordWrap(True)
        self.lbl_intro.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.lbl_intro)

        # ------------------ GROUP 1: INPUT CAPTURE & VOICE ------------------
        grp_in = QGroupBox("🎙️ Broadcast Input & Microphone Capture")
        lay_in = QVBoxLayout(grp_in)
        lay_in.setSpacing(8)

        row_in_dev = QHBoxLayout()
        lbl_in_dev = QLabel("Input Device:")
        lbl_in_dev.setFixedWidth(105)
        row_in_dev.addWidget(lbl_in_dev)

        self.combo_input_device = QComboBox()
        self.combo_input_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_input_device.setMinimumContentsLength(10)
        self.combo_input_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_input_device.setToolTip(
            "Select the primary microphone or VoiceMeeter output channel used by Auto-Clip & Audio Diagnostics."
        )
        self.combo_input_device.currentIndexChanged.connect(self._on_input_device_changed)
        row_in_dev.addWidget(self.combo_input_device, 1)

        self.btn_refresh_in = QPushButton("🔄 Refresh")
        self.btn_refresh_in.setToolTip("Re-scan Windows WASAPI audio capture devices.")
        self.btn_refresh_in.clicked.connect(self.refresh_devices)
        row_in_dev.addWidget(self.btn_refresh_in)
        lay_in.addLayout(row_in_dev)

        # Input Gain Trim
        row_gain = QHBoxLayout()
        lbl_gain = QLabel("Input Gain Trim:")
        lbl_gain.setFixedWidth(105)
        row_gain.addWidget(lbl_gain)

        self.slider_gain = QSlider(Qt.Orientation.Horizontal)
        self.slider_gain.setRange(25, 300)
        self.slider_gain.setValue(100)
        self.slider_gain.setToolTip("Adjust digital input pre-amplification trim (25% to 300%). Syncs with Auto-Clip.")
        self.slider_gain.valueChanged.connect(self._on_gain_changed)
        row_gain.addWidget(self.slider_gain, 1)

        self.lbl_gain_val = QLabel("100%")
        self.lbl_gain_val.setFixedWidth(44)
        self.lbl_gain_val.setStyleSheet("font-weight: bold; font-family: monospace; color: #38bdf8;")
        row_gain.addWidget(self.lbl_gain_val)

        self.btn_reset_gain = QPushButton("Reset")
        self.btn_reset_gain.setToolTip("Reset digital input gain trim back to 100% baseline.")
        self.btn_reset_gain.clicked.connect(lambda: self.slider_gain.setValue(100))
        row_gain.addWidget(self.btn_reset_gain)
        lay_in.addLayout(row_gain)

        # Diagnostics action row
        row_diag = QHBoxLayout()
        self.btn_audio_diag = QPushButton("🩺 Run 5-Second Audio Input Diagnostics")
        self.btn_audio_diag.setStyleSheet(
            "background-color: #0284c7; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;"
        )
        self.btn_audio_diag.setToolTip(
            "Launch the WASAPI Audio Input Diagnostics benchmark to verify sample rates, channels, and peak levels."
        )
        self.btn_audio_diag.clicked.connect(self._open_audio_diagnostics)
        row_diag.addWidget(self.btn_audio_diag)
        row_diag.addStretch()
        lay_in.addLayout(row_diag)

        layout.addWidget(grp_in)

        # ------------------ GROUP 2: OUTPUT & SOUNDBOARD ROUTING ------------------
        grp_out = QGroupBox("🔊 Output Playback & Soundboard Routing")
        lay_out = QVBoxLayout(grp_out)
        lay_out.setSpacing(8)

        row_out_dev = QHBoxLayout()
        lbl_out_dev = QLabel("Output Device:")
        lbl_out_dev.setFixedWidth(105)
        row_out_dev.addWidget(lbl_out_dev)

        self.combo_output_device = QComboBox()
        self.combo_output_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_output_device.setMinimumContentsLength(10)
        self.combo_output_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_output_device.setToolTip(
            "Select the Windows playback device or virtual cable used by Soundboard & Alert audio cues."
        )
        self.combo_output_device.currentIndexChanged.connect(self._on_output_device_changed)
        row_out_dev.addWidget(self.combo_output_device, 1)

        self.btn_refresh_out = QPushButton("🔄 Refresh")
        self.btn_refresh_out.setToolTip("Re-scan Windows audio playback devices.")
        self.btn_refresh_out.clicked.connect(self.refresh_devices)
        row_out_dev.addWidget(self.btn_refresh_out)
        lay_out.addLayout(row_out_dev)

        # Master Output Volume
        row_vol = QHBoxLayout()
        lbl_vol = QLabel("Master Volume:")
        lbl_vol.setFixedWidth(105)
        row_vol.addWidget(lbl_vol)

        self.slider_master_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_master_vol.setRange(0, 100)
        self.slider_master_vol.setValue(80)
        self.slider_master_vol.setToolTip("Adjust master Soundboard playback volume (0% to 100%). Syncs with Soundboard.")
        self.slider_master_vol.valueChanged.connect(self._on_master_vol_changed)
        row_vol.addWidget(self.slider_master_vol, 1)

        self.lbl_master_vol = QLabel("80%")
        self.lbl_master_vol.setFixedWidth(44)
        self.lbl_master_vol.setStyleSheet("font-weight: bold; font-family: monospace; color: #22c55e;")
        row_vol.addWidget(self.lbl_master_vol)

        self.btn_test_tone = QPushButton("🔔 Test Chime")
        self.btn_test_tone.setToolTip("Play a short synthesized test chime to verify your selected output device.")
        self.btn_test_tone.clicked.connect(self._play_test_chime)
        row_vol.addWidget(self.btn_test_tone)
        lay_out.addLayout(row_vol)

        layout.addWidget(grp_out)

        # ------------------ GROUP 3: ROUTING TIPS ------------------
        grp_tips = QGroupBox("💡 Virtual Cable & VoiceMeeter Routing Guide")
        lay_tips = QVBoxLayout(grp_tips)
        self.lbl_tips = QLabel(
            "• <b>VoiceMeeter Users:</b> Select <i>VoiceMeeter Output (VB-Audio VoiceMeeter VAIO / B3)</i> as your Input Device "
            "for isolated mic + co-host reaction capture.<br>"
            "• <b>Soundboard Separation:</b> Route Soundboard Output to a secondary Virtual Audio Cable (e.g. <i>CABLE Input</i>) "
            "so OBS/SLOBS can control soundboard volume on its own mixer track."
        )
        self.lbl_tips.setWordWrap(True)
        self.lbl_tips.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_tips.setStyleSheet("font-size: 11px; line-height: 1.4;")
        lay_tips.addWidget(self.lbl_tips)
        layout.addWidget(grp_tips)

        layout.addStretch()

        # Defer initial device enumeration slightly or populate immediately
        self.refresh_devices()

    def refresh_devices(self):
        """Synchronizes input & output dropdowns and sliders from active engines."""
        # 1. Input Device & Gain (AutoClipEngine)
        if not self.auto_clip_engine and self.overlay:
            self.auto_clip_engine = getattr(self.overlay, "auto_clip_engine", None)
        if self.auto_clip_engine:
            self.combo_input_device.blockSignals(True)
            self.combo_input_device.clear()
            try:
                devices = self.auto_clip_engine.get_available_devices()
            except Exception as e:
                log_debug("ERROR", f"AudioTab input enumeration error: {e}")
                devices = []
            selected_idx = 0
            cur_name = (getattr(self.auto_clip_engine, "selected_device_name", "") or "").strip()
            for i, d in enumerate(devices):
                desc = d.description() if hasattr(d, "description") else (d.get("description", "") if isinstance(d, dict) else str(d))
                tag = " (Recommended)" if "voicemeeter" in desc.lower() or "b3" in desc.lower() else ""
                self.combo_input_device.addItem(f"{desc}{tag}", desc)
                if cur_name and desc.strip() == cur_name:
                    selected_idx = i
            self.combo_input_device.setCurrentIndex(selected_idx)
            self.combo_input_device.blockSignals(False)

            gain_pct = int(getattr(self.auto_clip_engine, "input_gain", 1.0) * 100)
            self.slider_gain.blockSignals(True)
            self.slider_gain.setValue(max(25, min(300, gain_pct)))
            self.slider_gain.blockSignals(False)
            self.lbl_gain_val.setText(f"{self.slider_gain.value()}%")
        else:
            self.combo_input_device.clear()
            self.combo_input_device.addItem("Auto-Clip Engine Not Loaded", "")
            self.combo_input_device.setEnabled(False)

        # 2. Output Device & Master Volume (SoundboardEngine)
        if not self.soundboard_engine and self.overlay:
            self.soundboard_engine = getattr(self.overlay, "soundboard_engine", None)
        if self.soundboard_engine:
            self.combo_output_device.blockSignals(True)
            self.combo_output_device.clear()
            self.combo_output_device.addItem("🔊 System Default Audio Device", "")
            try:
                out_devs = self.soundboard_engine.get_output_devices()
            except Exception as e:
                log_debug("ERROR", f"AudioTab output enumeration error: {e}")
                out_devs = []
            sel_out_idx = 0
            cur_out = getattr(self.soundboard_engine, "selected_device_name", "") or ""
            for idx, dev_name in enumerate(out_devs, start=1):
                self.combo_output_device.addItem(f"🎧 {dev_name}", dev_name)
                if dev_name == cur_out:
                    sel_out_idx = idx
            self.combo_output_device.setCurrentIndex(sel_out_idx)
            self.combo_output_device.blockSignals(False)

            vol_pct = int(getattr(self.soundboard_engine, "master_volume", 0.8) * 100)
            self.slider_master_vol.blockSignals(True)
            self.slider_master_vol.setValue(max(0, min(100, vol_pct)))
            self.slider_master_vol.blockSignals(False)
            self.lbl_master_vol.setText(f"{self.slider_master_vol.value()}%")
        else:
            self.combo_output_device.clear()
            self.combo_output_device.addItem("Soundboard Engine Not Loaded", "")
            self.combo_output_device.setEnabled(False)

    def _on_input_device_changed(self):
        if not self.auto_clip_engine:
            return
        dev_desc = self.combo_input_device.currentData()
        if dev_desc:
            self.auto_clip_engine.set_device_by_name(dev_desc)
            # Sync AutoClipTab if present
            if hasattr(self.main_win, "tab_autoclip") and hasattr(self.main_win.tab_autoclip, "_populate_devices"):
                self.main_win.tab_autoclip._populate_devices()

    def _on_gain_changed(self, val: int):
        self.lbl_gain_val.setText(f"{val}%")
        if self.auto_clip_engine:
            self.auto_clip_engine.input_gain = val / 100.0
            if hasattr(self.main_win, "tab_autoclip") and hasattr(self.main_win.tab_autoclip, "slider_gain"):
                ac_tab = self.main_win.tab_autoclip
                ac_tab.slider_gain.blockSignals(True)
                ac_tab.slider_gain.setValue(val)
                ac_tab.slider_gain.blockSignals(False)
                if hasattr(ac_tab, "lbl_gain_val"):
                    ac_tab.lbl_gain_val.setText(f"{val}%")

    def _on_output_device_changed(self):
        if not self.soundboard_engine:
            return
        dev_name = self.combo_output_device.currentData() or ""
        self.soundboard_engine.set_output_device(dev_name)
        if hasattr(self.main_win, "tab_soundboard") and hasattr(self.main_win.tab_soundboard, "_populate_audio_devices"):
            self.main_win.tab_soundboard._populate_audio_devices()

    def _on_master_vol_changed(self, val: int):
        self.lbl_master_vol.setText(f"{val}%")
        if self.soundboard_engine:
            self.soundboard_engine.set_master_volume(val / 100.0)
            if hasattr(self.main_win, "tab_soundboard") and hasattr(self.main_win.tab_soundboard, "slider_master"):
                sb_tab = self.main_win.tab_soundboard
                sb_tab.slider_master.blockSignals(True)
                sb_tab.slider_master.setValue(val)
                sb_tab.slider_master.blockSignals(False)
                if hasattr(sb_tab, "lbl_master_val"):
                    sb_tab.lbl_master_val.setText(f"{val}%")

    def _open_audio_diagnostics(self):
        try:
            from audio_diagnostics import AudioDiagnosticsDialog
            dlg = AudioDiagnosticsDialog(self, overlay_app=self.overlay, engine=self.auto_clip_engine)
            dlg.exec()
        except Exception as e:
            log_debug("ERROR", f"AudioTab failed to open AudioDiagnosticsDialog: {e}")

    def _play_test_chime(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

    def refresh_theme_labels(self, effective: str):
        sec = "#a1a1aa" if effective == "dark" else "#52525b"
        self.lbl_intro.setStyleSheet(f"font-size: 12px; color: {sec};")
        self.lbl_tips.setStyleSheet(f"font-size: 11px; line-height: 1.4; color: {sec};")
