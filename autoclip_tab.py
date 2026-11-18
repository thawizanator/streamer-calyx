import os
import json
import time
from datetime import datetime
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QSlider, QPushButton, QGroupBox, QFrame,
    QColorDialog, QScrollArea, QMessageBox, QGridLayout, QSizePolicy,
    QTabWidget, QLineEdit, QListWidget, QListWidgetItem, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtGui import QPainter, QColor, QPen

try:
    from theme_manager import theme_manager
except ImportError:
    class DummyTheme:
        def get_surface_color(self, t): return "#18181b" if t == "dark" else "#ffffff"
        def get_border_color(self, t): return "#27272a" if t == "dark" else "#e4e4e7"
        def get_text_color(self, t): return "#ffffff" if t == "dark" else "#18181b"
        def get_secondary_text_color(self, t): return "#a1a1aa" if t == "dark" else "#71717a"
        def get_accent_color(self, t): return "#0284c7"
    theme_manager = DummyTheme()

from auto_clip_engine import AutoClipEngine
from clip_vault import ClipVaultManager, ClipPreviewWidget


class SegmentedBarWidget(QWidget):
    """Segmented LED progress bar for live prosody DSP metrics (RMS, VAD, F0, Laughter, Hype)."""

    def __init__(self, active_color: str = "#22c55e", show_threshold: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
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


class DiscordVUMeterWidget(QWidget):
    """
    Discord-style interactive 4-zone Audio VU Meter.
    Renders 4 distinct color zones:
      - Green:  Normal speech / Ambient
      - Yellow: Elevated talking
      - Orange: Possible hype moment
      - Red:    Full peak trigger event
    Includes live bouncing bar, moving average baseline marker, and trigger threshold marker.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setMinimumWidth(200)

        self.current_level = 0.0
        self.display_level = 0.0
        self.current_zone = AutoClipEngine.ZONE_GREEN
        self.baseline = 0.05
        self.threshold = 0.70

        self._decay_timer = QTimer(self)
        self._decay_timer.setInterval(25)
        self._decay_timer.timeout.connect(self._on_decay_tick)
        self._decay_timer.start()

    def update_meter(self, level: float, zone: int, baseline: float, threshold: float):
        self.current_level = max(0.0, min(1.0, level))
        self.current_zone = zone
        self.baseline = baseline
        self.threshold = threshold
        if self.current_level > self.display_level:
            self.display_level = self.current_level
        self.update()

    def _on_decay_tick(self):
        if self.display_level > self.current_level:
            self.display_level = max(self.current_level, self.display_level - 0.04)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_h = 16
        bar_y = (h - bar_h) // 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#18181b"))
        painter.drawRoundedRect(0, bar_y, w, bar_h, 4, 4)

        num_segments = 40
        seg_gap = 2
        total_gaps = (num_segments - 1) * seg_gap
        seg_w = max(2.0, (w - total_gaps) / num_segments)

        lit_segments = int(self.display_level * num_segments)
        thresh_seg = int(self.threshold * num_segments)
        orange_seg = int(self.threshold * 0.78 * num_segments)
        yellow_seg = int(self.threshold * 0.42 * num_segments)

        for i in range(num_segments):
            seg_x = i * (seg_w + seg_gap)
            is_lit = i < lit_segments

            if i >= thresh_seg:
                color = QColor("#ef4444") if is_lit else QColor("#450a0a")
            elif i >= orange_seg:
                color = QColor("#f97316") if is_lit else QColor("#431407")
            elif i >= yellow_seg:
                color = QColor("#eab308") if is_lit else QColor("#422006")
            else:
                color = QColor("#22c55e") if is_lit else QColor("#052e16")

            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(seg_x, bar_y + 2, seg_w, bar_h - 4), 2, 2)

        base_x = self.baseline * w
        painter.setPen(QPen(QColor("#38bdf8"), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(base_x), bar_y - 2, int(base_x), bar_y + bar_h + 2)

        thresh_x = self.threshold * w
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(int(thresh_x), bar_y - 4, int(thresh_x), bar_y + bar_h + 4)


class AutoClipTab(QWidget):
    """
    Phase 10 Calibration GUI, Live Prosody Levels, Interactive Trigger History & Clip Vault.
    """
    settings_changed = pyqtSignal()

    def __init__(self, main_win=None, engine: AutoClipEngine = None, parent=None):
        super().__init__(parent)
        self.main_win = main_win
        self.engine = engine or AutoClipEngine(self)
        self.clip_vault = ClipVaultManager(self.engine, self)
        self._last_thump_log_ts = 0.0

        self._build_ui()
        self._load_from_engine()
        self._load_history_table()

        self.engine.level_updated.connect(self._on_level_updated)
        self.engine.dsp_telemetry_updated.connect(self._on_dsp_telemetry)
        self.engine.cooldown_tick.connect(self._on_cooldown_tick)
        self.engine.status_changed.connect(self._on_status_changed)
        self.engine.marker_triggered.connect(self._on_marker_triggered)
        self.engine.secondary_peak_logged.connect(self._on_secondary_logged)
        self.engine.possible_peak_logged.connect(self._on_possible_logged)
        self.clip_vault.clips_updated.connect(self._on_vault_clips_updated)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        content.setMinimumWidth(0)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ------------------ HEADER ------------------
        hdr = QVBoxLayout()
        hdr.setSpacing(4)

        lbl_title = QLabel("🎙️ Acoustic Prosody Auto-Clip & Clip Vault")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        hdr.addWidget(lbl_title)

        lbl_sub = QLabel(
            "20 Hz vectorized vocal prosody DSP with 8-zone reaction classification, "
            "Twitch markers, OBS/SLOBS Replay Buffer sync, and Highlight Vault."
        )
        lbl_sub.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        lbl_sub.setWordWrap(True)
        hdr.addWidget(lbl_sub)
        lay.addLayout(hdr)

        # ------------------ STREAMER MODE LOCK BANNER ------------------
        self.banner_streamer_mode = QFrame()
        self.banner_streamer_mode.setStyleSheet(
            "QFrame { background-color: #3f1d2b; border: 1px solid #f43f5e; border-radius: 6px; padding: 6px; }"
        )
        lay_banner = QHBoxLayout(self.banner_streamer_mode)
        lay_banner.setContentsMargins(8, 4, 8, 4)
        lbl_banner = QLabel("🔒 Streamer Mode is OFF: Auto-Clip is disabled until Streamer Mode or Content Creator Mode is enabled.")
        lbl_banner.setStyleSheet("color: #fda4af; font-weight: bold; font-size: 11px;")
        lbl_banner.setWordWrap(True)
        lay_banner.addWidget(lbl_banner)
        self.banner_streamer_mode.setVisible(False)
        lay.addWidget(self.banner_streamer_mode)

        # ------------------ MASTER TOGGLE + LIVE VU METER ------------------
        top_bar = QHBoxLayout()
        self.switch_master_enable = QCheckBox("Enable Acoustic Auto-Clip")
        self.switch_master_enable.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.switch_master_enable.toggled.connect(self._on_master_enable_toggled)
        top_bar.addWidget(self.switch_master_enable)
        top_bar.addStretch()

        self.btn_audio_diag = QPushButton("🔧 Audio Diagnostics")
        self.btn_audio_diag.setFixedHeight(26)
        self.btn_audio_diag.clicked.connect(self._open_audio_diagnostics)
        top_bar.addWidget(self.btn_audio_diag)

        self.lbl_status = QLabel("● Disabled")
        self.lbl_status.setStyleSheet("font-size: 10px; font-weight: bold; color: #71717a;")
        top_bar.addWidget(self.lbl_status)
        lay.addLayout(top_bar)

        self.grp_meter = QGroupBox("Live Audio Monitoring & 4-Zone Meter")
        lay_m = QVBoxLayout(self.grp_meter)
        lay_m.setSpacing(4)

        self.vu_meter = DiscordVUMeterWidget(self)
        lay_m.addWidget(self.vu_meter)

        row_m_info = QHBoxLayout()
        self.lbl_meter_legend = QLabel(
            "<span style='color:#22c55e;'>■ Normal</span> &nbsp; "
            "<span style='color:#eab308;'>■ Elevated</span> &nbsp; "
            "<span style='color:#f97316;'>■ Possible</span> &nbsp; "
            "<span style='color:#ef4444;'>■ Peak</span> &nbsp; | &nbsp; "
            "<span style='color:#38bdf8;'>--- Baseline</span> &nbsp; "
            "<span style='color:#ffffff;'>| Threshold</span>"
        )
        self.lbl_meter_legend.setStyleSheet("font-size: 10px;")
        row_m_info.addWidget(self.lbl_meter_legend)
        row_m_info.addStretch()

        self.lbl_cooldown = QLabel("Ready & Armed")
        self.lbl_cooldown.setStyleSheet("font-size: 11px; font-weight: bold; color: #22c55e;")
        row_m_info.addWidget(self.lbl_cooldown)
        lay_m.addLayout(row_m_info)
        lay.addWidget(self.grp_meter)

        # ------------------ 4-TAB CALIBRATION, HISTORY & VAULT ------------------
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setDocumentMode(True)
        self.sub_tabs.setUsesScrollButtons(True)
        self.sub_tabs.setMinimumWidth(0)

        self.sub_tabs.addTab(self._build_basic_tab(), "🎛️ Basic Tuning")
        self.sub_tabs.addTab(self._build_dsp_tab(), "🧬 Advanced DSP")
        self.sub_tabs.addTab(self._build_history_tab(), "📜 Trigger History")
        self.sub_tabs.addTab(self._build_vault_tab(), "🗄️ Clip Vault")
        lay.addWidget(self.sub_tabs)

        self.cards = [self.grp_meter, self.sub_tabs]

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_basic_tab(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(0)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(8)

        grp_sens = QGroupBox("Input Device, Thresholds & Cooldown")
        lay_s = QVBoxLayout(grp_sens)
        lay_s.setSpacing(6)

        row_dev = QHBoxLayout()
        row_dev.addWidget(QLabel("Input Device:"))
        self.combo_device = QComboBox()
        self.combo_device.setMinimumWidth(0)
        self.combo_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_device.setMinimumContentsLength(16)
        self.combo_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_device.currentIndexChanged.connect(self._on_device_changed)
        row_dev.addWidget(self.combo_device, 1)
        btn_refresh_dev = QPushButton("🔄")
        btn_refresh_dev.setFixedWidth(30)
        btn_refresh_dev.setToolTip("Refresh audio input devices")
        btn_refresh_dev.clicked.connect(self._populate_devices)
        row_dev.addWidget(btn_refresh_dev)
        lay_s.addLayout(row_dev)

        row_gain = QHBoxLayout()
        row_gain.addWidget(QLabel("Input Gain Trim:"))
        self.slider_gain = QSlider(Qt.Orientation.Horizontal)
        self.slider_gain.setRange(25, 200)
        self.slider_gain.valueChanged.connect(self._on_gain_changed)
        row_gain.addWidget(self.slider_gain, 1)
        self.lbl_gain = QLabel("100%")
        self.lbl_gain.setFixedWidth(44)
        row_gain.addWidget(self.lbl_gain)
        lay_s.addLayout(row_gain)

        self.chk_auto_sens = QCheckBox("Auto-Sensitivity (Dual-Baseline floats above ambient & speech anchor)")
        self.chk_auto_sens.toggled.connect(self._on_auto_sens_toggled)
        lay_s.addWidget(self.chk_auto_sens)

        row_off = QHBoxLayout()
        self.lbl_offset_title = QLabel("Trigger Offset (+ baseline):")
        row_off.addWidget(self.lbl_offset_title)
        self.slider_offset = QSlider(Qt.Orientation.Horizontal)
        self.slider_offset.setRange(15, 60)
        self.slider_offset.valueChanged.connect(self._on_offset_changed)
        row_off.addWidget(self.slider_offset, 1)
        self.lbl_offset = QLabel("+30%")
        self.lbl_offset.setFixedWidth(44)
        row_off.addWidget(self.lbl_offset)
        lay_s.addLayout(row_off)

        row_man = QHBoxLayout()
        self.lbl_thresh_title = QLabel("Manual Threshold:")
        row_man.addWidget(self.lbl_thresh_title)
        self.slider_thresh = QSlider(Qt.Orientation.Horizontal)
        self.slider_thresh.setRange(40, 100)
        self.slider_thresh.valueChanged.connect(self._on_manual_thresh_changed)
        row_man.addWidget(self.slider_thresh, 1)
        self.lbl_thresh = QLabel("70%")
        self.lbl_thresh.setFixedWidth(44)
        row_man.addWidget(self.lbl_thresh)
        lay_s.addLayout(row_man)

        row_dur = QHBoxLayout()
        row_dur.addWidget(QLabel("Min Peak Duration:"))
        self.slider_duration = QSlider(Qt.Orientation.Horizontal)
        self.slider_duration.setRange(100, 800)
        self.slider_duration.setSingleStep(50)
        self.slider_duration.valueChanged.connect(self._on_duration_changed)
        row_dur.addWidget(self.slider_duration, 1)
        self.lbl_duration = QLabel("250 ms")
        self.lbl_duration.setFixedWidth(52)
        row_dur.addWidget(self.lbl_duration)
        lay_s.addLayout(row_dur)

        row_cd = QHBoxLayout()
        row_cd.addWidget(QLabel("Anti-Spam Cooldown:"))
        self.slider_cooldown = QSlider(Qt.Orientation.Horizontal)
        self.slider_cooldown.setRange(15, 120)
        self.slider_cooldown.setSingleStep(5)
        self.slider_cooldown.valueChanged.connect(self._on_cooldown_cfg_changed)
        row_cd.addWidget(self.slider_cooldown, 1)
        self.lbl_cooldown_cfg = QLabel("60 s")
        self.lbl_cooldown_cfg.setFixedWidth(52)
        row_cd.addWidget(self.lbl_cooldown_cfg)
        lay_s.addLayout(row_cd)

        lay.addWidget(grp_sens)

        # Actions, Replay Buffer & Marker Templates
        grp_act = QGroupBox("Dual-Platform Dispatcher (Twitch Helix + OBS/SLOBS Replay Buffer)")
        lay_a = QVBoxLayout(grp_act)
        lay_a.setSpacing(6)

        self.chk_replay_buffer = QCheckBox("Save SLOBS / OBS Replay Buffer automatically on Primary Peak")
        self.chk_replay_buffer.toggled.connect(self._on_replay_buffer_toggled)
        lay_a.addWidget(self.chk_replay_buffer)

        self.chk_log_orange = QCheckBox("Log Orange 'Possible Moments' to cooldown_clips.txt")
        self.chk_log_orange.toggled.connect(self._on_log_orange_toggled)
        lay_a.addWidget(self.chk_log_orange)

        self.chk_flash = QCheckBox("Flash Monitor Border Alert on Peak")
        self.chk_flash.toggled.connect(self._on_flash_toggled)
        lay_a.addWidget(self.chk_flash)

        self.chk_chime = QCheckBox("Play Soft Headphone Chime on Peak")
        self.chk_chime.toggled.connect(self._on_chime_toggled)
        lay_a.addWidget(self.chk_chime)

        grid_tpl = QGridLayout()
        grid_tpl.addWidget(QLabel("Marker Template:"), 0, 0)
        self.txt_marker_template = QLineEdit()
        self.txt_marker_template.setPlaceholderText("{icon} {tag} [{game}]")
        self.txt_marker_template.textChanged.connect(self._on_marker_template_changed)
        grid_tpl.addWidget(self.txt_marker_template, 0, 1)

        grid_tpl.addWidget(QLabel("Game Title:"), 1, 0)
        self.txt_game_title = QLineEdit()
        self.txt_game_title.setPlaceholderText("Optional game name")
        self.txt_game_title.textChanged.connect(self._on_game_title_changed)
        grid_tpl.addWidget(self.txt_game_title, 1, 1)

        grid_tpl.addWidget(QLabel("Fallback Label:"), 2, 0)
        row_col = QHBoxLayout()
        self.txt_marker_desc = QLineEdit()
        self.txt_marker_desc.textChanged.connect(self._on_marker_desc_changed)
        row_col.addWidget(self.txt_marker_desc, 1)
        self.btn_color = QPushButton("Alert Color")
        self.btn_color.setFixedHeight(26)
        self.btn_color.clicked.connect(self._on_pick_color)
        row_col.addWidget(self.btn_color)
        self.btn_test_flash = QPushButton("⚡ Test Flash")
        self.btn_test_flash.setFixedHeight(26)
        self.btn_test_flash.clicked.connect(self._on_test_flash_clicked)
        row_col.addWidget(self.btn_test_flash)
        grid_tpl.addLayout(row_col, 2, 1)
        lay_a.addLayout(grid_tpl)

        lay.addWidget(grp_act)

        self.grp_scenes = QGroupBox("Active Scene Whitelist (Paused on other scenes like BRB)")
        lay_sc = QVBoxLayout(self.grp_scenes)
        self.lay_scene_grid = QGridLayout()
        self.scene_checkboxes = {}
        lay_sc.addLayout(self.lay_scene_grid)
        self._populate_scene_checkboxes()
        lay.addWidget(self.grp_scenes)

        row_log = QHBoxLayout()
        self.btn_open_log = QPushButton("📂 Open cooldown_clips.txt")
        self.btn_open_log.clicked.connect(self.engine.open_log_file)
        row_log.addWidget(self.btn_open_log)
        self.btn_clear_log = QPushButton("🗑️ Clear Log")
        self.btn_clear_log.clicked.connect(self._on_clear_log)
        row_log.addWidget(self.btn_clear_log)
        row_log.addStretch()
        lay.addLayout(row_log)

        lay.addStretch()
        return w

    def _build_dsp_tab(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(0)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(8)

        # Live Segmented Prosody Levels Display (from tester app)
        grp_levels = QGroupBox("Live Acoustic Prosody Levels (20 Hz DSP)")
        lay_lv = QVBoxLayout(grp_levels)
        lay_lv.setSpacing(6)

        # 1. Loudness (RMS/Peak)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Loudness (RMS/Peak):"))
        r1.addStretch()
        self.lbl_lv_loudness = QLabel("0%")
        self.lbl_lv_loudness.setStyleSheet("color: #eab308; font-weight: bold;")
        r1.addWidget(self.lbl_lv_loudness)
        lay_lv.addLayout(r1)
        self.bar_loudness = SegmentedBarWidget("#eab308")
        lay_lv.addWidget(self.bar_loudness)

        # 2. Voice Activity (VAD)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Voice Activity (VAD):"))
        r2.addStretch()
        self.lbl_lv_vad = QLabel("0% (Idle)")
        self.lbl_lv_vad.setStyleSheet("color: #22c55e; font-weight: bold;")
        r2.addWidget(self.lbl_lv_vad)
        lay_lv.addLayout(r2)
        self.bar_vad = SegmentedBarWidget("#22c55e")
        lay_lv.addWidget(self.bar_vad)

        # 3. Pitch Tracking (F0)
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Pitch Tracking (F0):"))
        r3.addStretch()
        self.lbl_lv_f0 = QLabel("0 Hz (Unvoiced)")
        self.lbl_lv_f0.setStyleSheet("color: #a855f7; font-weight: bold;")
        r3.addWidget(self.lbl_lv_f0)
        lay_lv.addLayout(r3)
        self.bar_f0 = SegmentedBarWidget("#a855f7")
        lay_lv.addWidget(self.bar_f0)

        # 4. Laughter Cadence (4-6Hz)
        r4 = QHBoxLayout()
        r4.addWidget(QLabel("Laughter Cadence (4-6Hz):"))
        r4.addStretch()
        self.lbl_lv_laughter = QLabel("0%")
        self.lbl_lv_laughter.setStyleSheet("color: #f97316; font-weight: bold;")
        r4.addWidget(self.lbl_lv_laughter)
        lay_lv.addLayout(r4)
        self.bar_laughter = SegmentedBarWidget("#f97316")
        lay_lv.addWidget(self.bar_laughter)

        # 5. Composite Hype Score
        r5 = QHBoxLayout()
        lbl_ch = QLabel("🔥 COMPOSITE HYPE SCORE:")
        lbl_ch.setStyleSheet("font-weight: bold;")
        r5.addWidget(lbl_ch)
        r5.addStretch()
        self.lbl_lv_hype = QLabel("0% [Thresh: 70%]")
        self.lbl_lv_hype.setStyleSheet("color: #ef4444; font-weight: bold;")
        r5.addWidget(self.lbl_lv_hype)
        lay_lv.addLayout(r5)
        self.bar_hype = SegmentedBarWidget("#ef4444", show_threshold=True)
        lay_lv.addWidget(self.bar_hype)

        row_cls = QHBoxLayout()
        self.lbl_dsp_classified = QLabel("🎙️ Classified: Idle / Ambient")
        self.lbl_dsp_classified.setStyleSheet("color: #38bdf8; font-weight: bold;")
        row_cls.addWidget(self.lbl_dsp_classified)
        row_cls.addStretch()
        self.lbl_dsp_thump = QLabel("Desk Thump Filter: Clear")
        self.lbl_dsp_thump.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        row_cls.addWidget(self.lbl_dsp_thump)
        lay_lv.addLayout(row_cls)

        lay.addWidget(grp_levels)

        # Voice Profiles & Session Anchor
        grp_vp = QGroupBox("Voice Profile & Session Anchor")
        lay_vp = QVBoxLayout(grp_vp)
        row_vp = QHBoxLayout()
        row_vp.addWidget(QLabel("Voice Profile:"))
        self.combo_voice_profile = QComboBox()
        self.combo_voice_profile.setMinimumWidth(0)
        for key, info in AutoClipEngine.VOICE_PROFILES.items():
            self.combo_voice_profile.addItem(info["label"], key)
        self.combo_voice_profile.currentIndexChanged.connect(self._on_voice_profile_changed)
        row_vp.addWidget(self.combo_voice_profile, 1)
        lay_vp.addLayout(row_vp)

        row_anc = QHBoxLayout()
        self.lbl_voice_anchor = QLabel("Session Voice Anchor: 35%")
        row_anc.addWidget(self.lbl_voice_anchor)
        row_anc.addStretch()
        self.btn_reset_voice = QPushButton("↺ Reset Voice & Pitch")
        self.btn_reset_voice.clicked.connect(self._on_reset_voice_clicked)
        row_anc.addWidget(self.btn_reset_voice)
        lay_vp.addLayout(row_anc)
        lay.addWidget(grp_vp)

        # Sub-Bass Desk Thump Rejection Slider
        grp_thump = QGroupBox("Sub-Bass Desk Thump / Mic Drop Rejection (<70 Hz)")
        lay_th = QHBoxLayout(grp_thump)
        lay_th.addWidget(QLabel("Filter Aggressiveness:"))
        self.slider_thump = QSlider(Qt.Orientation.Horizontal)
        self.slider_thump.setRange(0, 100)
        self.slider_thump.valueChanged.connect(self._on_thump_changed)
        lay_th.addWidget(self.slider_thump, 1)
        self.lbl_thump = QLabel("55%")
        self.lbl_thump.setFixedWidth(44)
        lay_th.addWidget(self.lbl_thump)
        lay.addWidget(grp_thump)

        # 1-Click Game Genre Presets (2x2 Grid so it never clips horizontally)
        grp_presets = QGroupBox("1-Click Game Genre Presets")
        grid_pr = QGridLayout(grp_presets)
        for idx, (key, info) in enumerate(AutoClipEngine.GENRE_PRESETS.items()):
            btn = QPushButton(info["label"])
            btn.clicked.connect(lambda _chk=False, k=key: self._on_genre_preset_clicked(k))
            grid_pr.addWidget(btn, idx // 2, idx % 2)
        lay.addWidget(grp_presets)

        # 8-Zone Classifier Legend
        grp_zones = QGroupBox("8-Zone Human Vocal Reaction Classifier")
        grid_z = QGridLayout(grp_zones)
        for idx, (icon, label, _slug) in enumerate(AutoClipEngine.REACTION_ZONES):
            lbl = QLabel(f"{icon}  {label}")
            lbl.setStyleSheet("font-size: 11px;")
            grid_z.addWidget(lbl, idx // 2, idx % 2)
        lay.addWidget(grp_zones)

        lay.addStretch()
        return w

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(0)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(8)

        grp_hist = QGroupBox("Interactive Trigger History & Payloads")
        lay_h = QVBoxLayout(grp_hist)

        self.tbl_history = QTableWidget(0, 7)
        self.tbl_history.setHorizontalHeaderLabels([
            "Time", "Date", "Vocal Reaction Tag", "Hype", "Game", "Stream Pos", "Status"
        ])
        self.tbl_history.setAlternatingRowColors(True)
        self.tbl_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_history.setMinimumHeight(240)
        hdr = self.tbl_history.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        self.tbl_history.setColumnWidth(0, 68)
        self.tbl_history.setColumnWidth(1, 84)
        self.tbl_history.setColumnWidth(2, 165)
        self.tbl_history.setColumnWidth(3, 52)
        self.tbl_history.setColumnWidth(4, 95)
        self.tbl_history.setColumnWidth(5, 80)
        lay_h.addWidget(self.tbl_history)

        row_btns = QHBoxLayout()
        btn_clear = QPushButton("🗑️ Clear Events")
        btn_clear.clicked.connect(self._on_clear_history_events)
        row_btns.addWidget(btn_clear)

        btn_export_json = QPushButton("💾 Export Session Log (.json)")
        btn_export_json.clicked.connect(self._on_export_history_json)
        row_btns.addWidget(btn_export_json)
        row_btns.addStretch()
        lay_h.addLayout(row_btns)

        lay.addWidget(grp_hist)
        return w

    def _build_vault_tab(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(0)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 4)
        lay.setSpacing(8)

        grp_dir = QGroupBox("OBS / Streamlabs Replay Folder Watcher")
        lay_d = QVBoxLayout(grp_dir)
        row_dir = QHBoxLayout()
        self.txt_replay_dir = QLineEdit()
        self.txt_replay_dir.setPlaceholderText("Select OBS / Streamlabs Replay Buffer folder...")
        self.txt_replay_dir.editingFinished.connect(self._on_replay_dir_changed)
        row_dir.addWidget(self.txt_replay_dir, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_replay_dir)
        row_dir.addWidget(btn_browse)

        btn_rescan = QPushButton("🔄 Scan")
        btn_rescan.clicked.connect(self.clip_vault.scan_clips)
        row_dir.addWidget(btn_rescan)
        lay_d.addLayout(row_dir)

        self.chk_auto_rename = QCheckBox("Auto-tag matched replay filenames (e.g., 2026-11-17_21-40-48_😱_High_Pitched_Scream.mp4)")
        self.chk_auto_rename.toggled.connect(self._on_auto_rename_toggled)
        lay_d.addWidget(self.chk_auto_rename)
        lay.addWidget(grp_dir)

        self.list_clips = QListWidget()
        self.list_clips.setMinimumHeight(110)
        self.list_clips.setMaximumHeight(160)
        self.list_clips.currentItemChanged.connect(self._on_clip_selected)
        lay.addWidget(self.list_clips)

        self.preview_widget = ClipPreviewWidget(self)
        lay.addWidget(self.preview_widget)

        grp_exp = QGroupBox("Video Editor Export Assistant (Session & Reaction Markers)")
        row_exp = QHBoxLayout(grp_exp)
        btn_yt = QPushButton("📺 YouTube (.txt)")
        btn_yt.clicked.connect(lambda: self._export_markers("yt"))
        row_exp.addWidget(btn_yt)

        btn_edl = QPushButton("🎬 DaVinci/Premiere (.edl)")
        btn_edl.clicked.connect(lambda: self._export_markers("edl"))
        row_exp.addWidget(btn_edl)

        btn_csv = QPushButton("📊 CapCut/CSV (.csv)")
        btn_csv.clicked.connect(lambda: self._export_markers("csv"))
        row_exp.addWidget(btn_csv)
        lay.addWidget(grp_exp)

        return w

    # ------------------ UI Helpers & Load / Save ------------------

    def _populate_devices(self):
        self.combo_device.blockSignals(True)
        self.combo_device.clear()
        devices = self.engine.get_available_devices()
        selected_idx = 0
        for i, d in enumerate(devices):
            desc = d.description()
            tag = " (Default)" if d.isDefault() else ""
            self.combo_device.addItem(f"{desc}{tag}", desc)
            if self.engine.selected_device_name and desc.strip() == self.engine.selected_device_name.strip():
                selected_idx = i
        self.combo_device.setCurrentIndex(selected_idx)
        self.combo_device.blockSignals(False)

    def _populate_scene_checkboxes(self):
        scenes = ["In-Game", "Banter", "BRB", "Starting", "Ending", "Scene 6"]
        if self.main_win and hasattr(self.main_win, "settings_window") and hasattr(self.main_win.settings_window, "tab_director"):
            dir_scenes = self.main_win.settings_window.tab_director.scenes
            if dir_scenes:
                scenes = [s.get("name") for s in dir_scenes if s.get("name")]

        while self.lay_scene_grid.count():
            item = self.lay_scene_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.scene_checkboxes.clear()

        cols = 2
        for i, sc_name in enumerate(scenes):
            chk = QCheckBox(sc_name)
            chk.setToolTip(sc_name)
            chk.setChecked(sc_name in self.engine.active_scenes)
            chk.toggled.connect(self._on_scene_toggled)
            self.scene_checkboxes[sc_name] = chk
            self.lay_scene_grid.addWidget(chk, i // cols, i % cols)

    def _load_from_engine(self):
        self._populate_devices()

        self.switch_master_enable.blockSignals(True)
        self.switch_master_enable.setChecked(self.engine.enabled)
        self.switch_master_enable.blockSignals(False)

        self.slider_gain.blockSignals(True)
        self.slider_gain.setValue(int(self.engine.input_gain * 100))
        self.slider_gain.blockSignals(False)
        self.lbl_gain.setText(f"{int(self.engine.input_gain * 100)}%")

        self.chk_auto_sens.blockSignals(True)
        self.chk_auto_sens.setChecked(self.engine.auto_sensitivity)
        self.chk_auto_sens.blockSignals(False)

        self.slider_offset.blockSignals(True)
        self.slider_offset.setValue(int(self.engine.trigger_offset * 100))
        self.slider_offset.blockSignals(False)
        self.lbl_offset.setText(f"+{int(self.engine.trigger_offset * 100)}%")

        self.slider_thresh.blockSignals(True)
        self.slider_thresh.setValue(int(self.engine.manual_threshold * 100))
        self.slider_thresh.blockSignals(False)
        self.lbl_thresh.setText(f"{int(self.engine.manual_threshold * 100)}%")

        self.slider_duration.blockSignals(True)
        self.slider_duration.setValue(self.engine.min_duration_ms)
        self.slider_duration.blockSignals(False)
        self.lbl_duration.setText(f"{self.engine.min_duration_ms} ms")

        self.slider_cooldown.blockSignals(True)
        self.slider_cooldown.setValue(int(self.engine.cooldown_duration_sec))
        self.slider_cooldown.blockSignals(False)
        self.lbl_cooldown_cfg.setText(f"{int(self.engine.cooldown_duration_sec)} s")

        self.chk_replay_buffer.setChecked(getattr(self.engine, "save_replay_buffer", True))
        self.chk_log_orange.setChecked(self.engine.log_orange_moments)
        self.chk_flash.setChecked(self.engine.flash_overlay)
        self.chk_chime.setChecked(self.engine.play_chime)

        self.txt_marker_template.blockSignals(True)
        self.txt_marker_template.setText(getattr(self.engine, "marker_template", "{icon} {tag} [{game}]"))
        self.txt_marker_template.blockSignals(False)

        self.txt_game_title.blockSignals(True)
        self.txt_game_title.setText(getattr(self.engine, "game_title", ""))
        self.txt_game_title.blockSignals(False)

        self.txt_marker_desc.blockSignals(True)
        self.txt_marker_desc.setText(self.engine.marker_description)
        self.txt_marker_desc.blockSignals(False)
        self._update_color_preview(self.engine.alert_color)

        vp_idx = self.combo_voice_profile.findData(getattr(self.engine, "voice_profile", "dynamic"))
        if vp_idx >= 0:
            self.combo_voice_profile.blockSignals(True)
            self.combo_voice_profile.setCurrentIndex(vp_idx)
            self.combo_voice_profile.blockSignals(False)

        self.slider_thump.blockSignals(True)
        self.slider_thump.setValue(int(getattr(self.engine, "desk_thump_sensitivity", 0.55) * 100))
        self.slider_thump.blockSignals(False)
        self.lbl_thump.setText(f"{int(getattr(self.engine, 'desk_thump_sensitivity', 0.55) * 100)}%")

        self.txt_replay_dir.setText(getattr(self.engine, "replay_dir", ""))
        self.chk_auto_rename.setChecked(getattr(self.engine, "auto_rename_replays", False))
        if getattr(self.engine, "replay_dir", ""):
            self.clip_vault.set_replay_dir(self.engine.replay_dir, self.engine.auto_rename_replays)

        self._on_auto_sens_toggled(self.engine.auto_sensitivity)
        self._on_master_enable_toggled(self.engine.enabled)

    def _update_color_preview(self, hex_color: str):
        self.btn_color.setStyleSheet(
            f"background-color: {hex_color}; color: #000000; font-weight: bold; border-radius: 4px; padding: 4px 10px;"
        )

    # ------------------ History Table Helpers ------------------

    def _load_history_table(self):
        self.tbl_history.setRowCount(0)
        for entry in self.engine.get_reaction_history():
            self._append_history_row(
                created_at=entry.get("created_at", ""),
                tag=f"{entry.get('reaction_icon', '💬')} {entry.get('reaction_label', 'Highlight')}",
                hype_pct=f"{int(round(float(entry.get('level', 0.0)) * 100))}%",
                game=getattr(self.engine, "game_title", "") or "Local Session",
                stream_pos=entry.get("timestamp_str", "00:00"),
                status="Primary Trigger" if entry.get("kind") == "primary" else "Cooldown Secondary",
                color_hex="#f59e0b" if entry.get("kind") == "primary" else "#38bdf8",
            )

    def _append_history_row(self, created_at: str, tag: str, hype_pct: str, game: str,
                            stream_pos: str, status: str, color_hex: str = "#e4e4e7"):
        try:
            dt = datetime.fromisoformat(created_at) if created_at else datetime.now()
            t_str = dt.strftime("%H:%M:%S")
            d_str = dt.strftime("%Y-%m-%d")
        except Exception:
            t_str = datetime.now().strftime("%H:%M:%S")
            d_str = datetime.now().strftime("%Y-%m-%d")

        row = self.tbl_history.rowCount()
        self.tbl_history.insertRow(row)
        vals = [t_str, d_str, tag, hype_pct, game, stream_pos, status]
        col = QColor(color_hex)
        for c_idx, text in enumerate(vals):
            item = QTableWidgetItem(str(text))
            if c_idx in (2, 3, 6):
                item.setForeground(col)
            self.tbl_history.setItem(row, c_idx, item)
        self.tbl_history.scrollToBottom()

    def _on_clear_history_events(self):
        self.engine.clear_reaction_history()
        self.tbl_history.setRowCount(0)

    def _on_export_history_json(self):
        history = self.engine.get_reaction_history()
        out_path, _ = QFileDialog.getSaveFileName(self, "Export Session Trigger Log", "calyx_trigger_history.json", "JSON (*.json)")
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
            QMessageBox.information(self, "Export Complete", f"Exported {len(history)} trigger event(s) to:\n{out_path}")

    # ------------------ Slots ------------------

    def _on_master_enable_toggled(self, checked: bool):
        self.engine.enabled = checked
        if checked:
            self.engine.start_monitoring()
        else:
            self.engine.stop_monitoring()
        for c in self.cards:
            if c != self.grp_meter:
                c.setEnabled(checked)
        self.settings_changed.emit()

    def _open_audio_diagnostics(self):
        if self.main_win and hasattr(self.main_win, "show_audio_diagnostics"):
            self.main_win.show_audio_diagnostics()
        elif self.main_win and hasattr(self.main_win, "overlay") and hasattr(self.main_win.overlay, "show_audio_diagnostics"):
            self.main_win.overlay.show_audio_diagnostics()

    def _on_device_changed(self):
        name = self.combo_device.currentData()
        if name:
            self.engine.set_device_by_name(name)
            self.settings_changed.emit()

    def _on_gain_changed(self, val: int):
        self.engine.input_gain = val / 100.0
        self.lbl_gain.setText(f"{val}%")
        self.settings_changed.emit()

    def _on_auto_sens_toggled(self, checked: bool):
        self.engine.auto_sensitivity = checked
        self.slider_offset.setEnabled(checked)
        self.lbl_offset_title.setEnabled(checked)
        self.lbl_offset.setEnabled(checked)
        self.slider_thresh.setEnabled(not checked)
        self.lbl_thresh_title.setEnabled(not checked)
        self.lbl_thresh.setEnabled(not checked)
        self.settings_changed.emit()

    def _on_offset_changed(self, val: int):
        self.engine.trigger_offset = val / 100.0
        self.lbl_offset.setText(f"+{val}%")
        self.settings_changed.emit()

    def _on_manual_thresh_changed(self, val: int):
        self.engine.manual_threshold = val / 100.0
        self.lbl_thresh.setText(f"{val}%")
        self.settings_changed.emit()

    def _on_duration_changed(self, val: int):
        self.engine.min_duration_ms = val
        self.lbl_duration.setText(f"{val} ms")
        self.settings_changed.emit()

    def _on_cooldown_cfg_changed(self, val: int):
        self.engine.cooldown_duration_sec = val
        self.lbl_cooldown_cfg.setText(f"{val} s")
        self.settings_changed.emit()

    def _on_replay_buffer_toggled(self, checked: bool):
        self.engine.save_replay_buffer = checked
        self.settings_changed.emit()

    def _on_log_orange_toggled(self, checked: bool):
        self.engine.log_orange_moments = checked
        self.settings_changed.emit()

    def _on_flash_toggled(self, checked: bool):
        self.engine.flash_overlay = checked
        self.settings_changed.emit()

    def _on_chime_toggled(self, checked: bool):
        self.engine.play_chime = checked
        self.settings_changed.emit()

    def _on_marker_template_changed(self, text: str):
        self.engine.marker_template = text.strip() or "{icon} {tag} [{game}]"
        self.settings_changed.emit()

    def _on_game_title_changed(self, text: str):
        self.engine.game_title = text.strip()
        self.settings_changed.emit()

    def _on_marker_desc_changed(self, text: str):
        self.engine.marker_description = text.strip() or "Auto-Clip/Markers"
        self.settings_changed.emit()

    def _on_pick_color(self):
        col = QColorDialog.getColor(QColor(self.engine.alert_color), self, "Select Peak Border Alert Color")
        if col.isValid():
            self.engine.alert_color = col.name()
            self._update_color_preview(col.name())
            self.settings_changed.emit()

    def _on_test_flash_clicked(self):
        if self.main_win and hasattr(self.main_win, "overlay") and self.main_win.overlay:
            self.main_win.overlay.flash_temporary_alert(duration_ms=1500, color=QColor(self.engine.alert_color))

    def _on_scene_toggled(self):
        selected = [name for name, chk in self.scene_checkboxes.items() if chk.isChecked()]
        self.engine.active_scenes = selected
        self.settings_changed.emit()

    def _on_clear_log(self):
        reply = QMessageBox.question(self, "Clear Clips Log", "Clear all entries in cooldown_clips.txt?")
        if reply == QMessageBox.StandardButton.Yes:
            self.engine.clear_log_file()

    def _on_voice_profile_changed(self):
        key = self.combo_voice_profile.currentData()
        if key:
            self.engine.apply_voice_profile(key)
            self.settings_changed.emit()

    def _on_thump_changed(self, val: int):
        self.engine.desk_thump_sensitivity = val / 100.0
        self.lbl_thump.setText(f"{val}%")
        self.settings_changed.emit()

    def _on_genre_preset_clicked(self, key: str):
        self.engine.apply_genre_preset(key)
        self._load_from_engine()
        self.settings_changed.emit()

    def _on_reset_voice_clicked(self):
        self.engine.reset_session_voice()
        self.lbl_voice_anchor.setText("Session Voice Anchor: 35% (Reset)")
        self.settings_changed.emit()

    def _browse_replay_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select OBS / Streamlabs Replay Buffer Folder", self.txt_replay_dir.text())
        if d:
            self.txt_replay_dir.setText(d)
            self._on_replay_dir_changed()

    def _on_replay_dir_changed(self):
        d = self.txt_replay_dir.text().strip()
        self.engine.replay_dir = d
        self.clip_vault.set_replay_dir(d, self.chk_auto_rename.isChecked())
        self.settings_changed.emit()

    def _on_auto_rename_toggled(self, checked: bool):
        self.engine.auto_rename_replays = checked
        self.clip_vault.set_replay_dir(self.txt_replay_dir.text().strip(), checked)
        self.settings_changed.emit()

    def _on_vault_clips_updated(self, clips: list):
        self.list_clips.clear()
        for c in clips:
            txt = f"{c['reaction_icon']}  {c['filename']}  |  {c['reaction_label']}  ({c['size_mb']} MB, {c['date_str']})"
            item = QListWidgetItem(txt)
            item.setData(Qt.ItemDataRole.UserRole, c["path"])
            self.list_clips.addItem(item)

    def _on_clip_selected(self, current: QListWidgetItem, _previous):
        if current:
            self.preview_widget.load_clip(current.data(Qt.ItemDataRole.UserRole))

    def _export_markers(self, fmt: str):
        history = self.engine.get_reaction_history()
        if not history:
            QMessageBox.information(self, "No Markers Yet", "No reaction peaks have been recorded yet in reaction_history.json.")
            return
        ext_map = {
            "yt": ("YouTube Chapters (*.txt)", "youtube_chapters.txt", ClipVaultManager.export_youtube_chapters),
            "edl": ("EDL Timeline Markers (*.edl)", "calyx_markers.edl", ClipVaultManager.export_edl_markers),
            "csv": ("CSV Timeline Markers (*.csv)", "calyx_markers.csv", ClipVaultManager.export_csv_markers),
        }
        flt, default_name, exporter = ext_map[fmt]
        out_path, _ = QFileDialog.getSaveFileName(self, "Export Highlight Markers", default_name, flt)
        if out_path:
            count = exporter(history, out_path)
            QMessageBox.information(self, "Export Complete", f"Exported {count} highlight marker(s) to:\n{out_path}")

    def _on_level_updated(self, level: float, zone: int, baseline: float, threshold: float):
        self.vu_meter.update_meter(level, zone, baseline, threshold)
        anchor_pct = int(getattr(self.engine, "session_voice_anchor", 0.35) * 100)
        self.lbl_voice_anchor.setText(f"Session Voice Anchor: {anchor_pct}%")

        # Update Loudness bar & threshold marker
        lvl_pct = int(round(level * 100))
        self.bar_loudness.set_value(level)
        self.lbl_lv_loudness.setText(f"{lvl_pct}%")
        self._last_threshold = threshold

    def _on_dsp_telemetry(self, tel: dict):
        f0 = tel.get("f0_hz", 0.0)
        vocal_vad = bool(tel.get("vocal_vad", False))
        vocal_ratio = float(tel.get("vocal_ratio", 0.0))
        laugh_cad = float(tel.get("laughter_cadence", 0.0))
        comp_hype = float(tel.get("composite_hype", 0.0))
        thresh = getattr(self, "_last_threshold", self.engine.current_threshold)

        vad_val = float(tel.get("vad_confidence", 0.0)) if vocal_vad else 0.0
        self.bar_vad.set_value(vad_val)
        self.lbl_lv_vad.setText(f"{int(round(vad_val * 100))}% (Human Voice)" if vocal_vad else "0% (Idle)")

        self.bar_f0.set_value(min(1.0, f0 / 550.0) if f0 > 0 else 0.0)
        self.lbl_lv_f0.setText(f"{f0:.0f} Hz ({tel.get('f0_ratio', 1.0):.2f}x)" if f0 > 0 else "0 Hz (Unvoiced)")

        self.bar_laughter.set_value(laugh_cad)
        self.lbl_lv_laughter.setText(f"{int(round(laugh_cad * 100))}%")

        self.bar_hype.set_value(comp_hype, thresh)
        self.lbl_lv_hype.setText(f"{int(round(comp_hype * 100))}% [Thresh: {int(round(thresh * 100))}%]")

        if tel.get("thump_rejected"):
            self.lbl_dsp_thump.setText("Desk Thump Filter: 🛡️ Rejected")
            self.lbl_dsp_thump.setStyleSheet("font-size: 11px; color: #f97316; font-weight: bold;")
            now = time.time()
            if now - self._last_thump_log_ts >= 3.0:
                self._last_thump_log_ts = now
                self._append_history_row(
                    created_at=datetime.now().isoformat(timespec="seconds"),
                    tag="🛑 Noise Filtered",
                    hype_pct="--",
                    game=getattr(self.engine, "game_title", "") or "Local Session",
                    stream_pos="--",
                    status="Desk Bump / Click Rejected",
                    color_hex="#71717a",
                )
        else:
            self.lbl_dsp_thump.setText("Desk Thump Filter: Clear")
            self.lbl_dsp_thump.setStyleSheet("font-size: 11px; color: #a1a1aa;")

        last_rx = tel.get("last_reaction", "")
        if last_rx:
            self.lbl_dsp_classified.setText(f"🎙️ Classified: {last_rx}")
        elif vocal_vad:
            self.lbl_dsp_classified.setText("🎙️ Classified: Normal Speech")
        else:
            self.lbl_dsp_classified.setText("🎙️ Classified: Idle / Ambient")

    def _on_cooldown_tick(self, rem: int):
        if rem > 0:
            self.lbl_cooldown.setText(f"⏱️ Cooldown: {rem}s")
            self.lbl_cooldown.setStyleSheet("font-size: 11px; font-weight: bold; color: #f59e0b;")
        else:
            self.lbl_cooldown.setText("Ready & Armed")
            self.lbl_cooldown.setStyleSheet("font-size: 11px; font-weight: bold; color: #22c55e;")

    def _on_status_changed(self, msg: str, is_active: bool):
        col = "#22c55e" if is_active else "#71717a"
        if "Paused" in msg:
            col = "#f59e0b"
        elif "Error" in msg:
            col = "#ef4444"
        tag = "Active" if is_active else ("Paused" if "Paused" in msg else ("Error" if "Error" in msg else "Disabled"))
        self.lbl_status.setText(f"● {tag}")
        self.lbl_status.setToolTip(f"Auto-Clip Status: {msg}")
        self.lbl_status.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {col};")

    def _on_marker_triggered(self, payload: dict):
        icon = payload.get("reaction_icon", "🔥")
        label = payload.get("reaction_label", "Peak")
        self.lbl_cooldown.setText(f"{icon} {label}! Cooldown: {self.engine.cooldown_duration_sec}s")
        self.lbl_cooldown.setStyleSheet("font-size: 11px; font-weight: bold; color: #ef4444;")
        self._append_history_row(
            created_at=payload.get("created_at", ""),
            tag=f"{icon} {label}",
            hype_pct=f"{int(round(float(payload.get('level', 0.0)) * 100))}%",
            game=getattr(self.engine, "game_title", "") or "Local Session",
            stream_pos=payload.get("timestamp_str", "00:00"),
            status="Primary Trigger (Marker + Replay)",
            color_hex="#f59e0b",
        )
        self.clip_vault.scan_clips()

    def _on_secondary_logged(self, payload: dict):
        icon = payload.get("reaction_icon", "⏱️")
        label = payload.get("reaction_label", "Secondary Peak")
        self._append_history_row(
            created_at=payload.get("created_at", ""),
            tag=f"{icon} {label}",
            hype_pct=f"{int(round(float(payload.get('level', 0.0)) * 100))}%",
            game=getattr(self.engine, "game_title", "") or "Local Session",
            stream_pos=payload.get("timestamp_str", "00:00"),
            status="Cooldown Secondary",
            color_hex="#38bdf8",
        )

    def _on_possible_logged(self, payload: dict):
        self._append_history_row(
            created_at="",
            tag="⚡ Possible Moment",
            hype_pct=f"{int(round(float(payload.get('level', 0.0)) * 100))}%",
            game=getattr(self.engine, "game_title", "") or "Local Session",
            stream_pos=payload.get("timestamp_str", "00:00"),
            status="Orange Possible Moment",
            color_hex="#f97316",
        )

    def set_streamer_mode(self, enabled: bool):
        is_active = bool(enabled)
        self.banner_streamer_mode.setVisible(not is_active)
        self.engine.set_streamer_mode(is_active)
        if not is_active:
            self.lbl_status.setText("● Locked (Streamer Mode OFF)")
            self.lbl_status.setStyleSheet("font-size: 10px; font-weight: bold; color: #71717a;")
            for c in self.cards:
                c.setEnabled(False)
            self.switch_master_enable.setEnabled(False)
            self.btn_audio_diag.setEnabled(False)
        else:
            self.switch_master_enable.setEnabled(True)
            self.btn_audio_diag.setEnabled(True)
            for c in self.cards:
                c.setEnabled(self.engine.enabled)
            self._on_master_enable_toggled(self.engine.enabled)
