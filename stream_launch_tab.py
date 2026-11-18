import os
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QCheckBox, QLineEdit, QMessageBox,
    QComboBox, QSpinBox, QProgressBar, QDialog, QListWidget,
    QListWidgetItem, QGridLayout, QDialogButtonBox
)
from PyQt6.QtGui import QColor

from streamlabs_client import get_streamlabs_client
from deorbit_engine import IFTTT_TRIGGERS, IFTTT_ACTIONS
from debug_logger import log_debug

DEFAULT_CHECKLIST = [
    "Hydration prepared & water bottle filled",
    "OBS / Streamlabs Desktop running in Admin mode",
    "Game launched & tested in borderless windowed mode",
    "Discord / VoiceMeeter audio levels balanced with co-hosts",
    "Stream title, category, and Twitch tags updated",
    "Phone & peripheral notifications muted"
]


class IFTTTRulesDialog(QDialog):
    """Universal 'If This, Then That' (IFTTT) Automation Rule Builder dialog."""

    def __init__(self, ifttt_engine, parent=None):
        super().__init__(parent)
        self.ifttt_engine = ifttt_engine
        self.setWindowTitle("⚡ IFTTT Automation Rules (If This → Then That)")
        self.resize(580, 440)
        self._rules = ifttt_engine.export_rules() if ifttt_engine else []

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        lbl = QLabel(
            "Create universal <b>If This → Then That</b> automations for any streaming workflow "
            "(De-Orbit, Stream Start/End, Scene Switch, Auto-Clip Peak, Recording)."
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        self.list_rules = QListWidget()
        self.list_rules.setMinimumHeight(170)
        lay.addWidget(self.list_rules)

        # New Rule Builder
        grp = QFrame()
        grp.setStyleSheet("QFrame { background-color: #18181b; border: 1px solid #3f3f46; border-radius: 6px; padding: 6px; }")
        grid = QGridLayout(grp)
        grid.addWidget(QLabel("<b>IF THIS:</b>"), 0, 0)
        self.combo_trigger = QComboBox()
        for tid, tlabel in IFTTT_TRIGGERS:
            self.combo_trigger.addItem(tlabel, tid)
        grid.addWidget(self.combo_trigger, 0, 1)

        self.txt_trigger_param = QLineEdit()
        self.txt_trigger_param.setPlaceholderText("Scene filter (for Scene Switch, optional)")
        grid.addWidget(self.txt_trigger_param, 0, 2)

        grid.addWidget(QLabel("<b>THEN THAT:</b>"), 1, 0)
        self.combo_action = QComboBox()
        for aid, alabel in IFTTT_ACTIONS:
            self.combo_action.addItem(alabel, aid)
        grid.addWidget(self.combo_action, 1, 1)

        self.txt_action_param = QLineEdit()
        self.txt_action_param.setPlaceholderText("Target (Scene / Mic / Chat Msg / #Color / Note)")
        grid.addWidget(self.txt_action_param, 1, 2)

        btn_add = QPushButton("➕ Add Rule")
        btn_add.setStyleSheet("background-color: #9146ff; color: white; font-weight: bold; padding: 4px 10px;")
        btn_add.clicked.connect(self._add_rule)
        grid.addWidget(btn_add, 2, 2)
        lay.addWidget(grp)

        row_actions = QHBoxLayout()
        btn_toggle = QPushButton("⏯️ Toggle Enabled")
        btn_toggle.clicked.connect(self._toggle_selected)
        row_actions.addWidget(btn_toggle)

        btn_test = QPushButton("⚡ Test Rule")
        btn_test.clicked.connect(self._test_selected)
        row_actions.addWidget(btn_test)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.clicked.connect(self._delete_selected)
        row_actions.addWidget(btn_del)
        row_actions.addStretch()
        lay.addLayout(row_actions)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._refresh_list()

    def _refresh_list(self):
        self.list_rules.clear()
        trig_map = dict(IFTTT_TRIGGERS)
        act_map = dict(IFTTT_ACTIONS)
        for r in self._rules:
            st = "✅" if r.get("enabled", True) else "⏸️"
            tp = f" [{r['trigger_param']}]" if r.get("trigger_param") else ""
            ap = f" → {r['action_param']}" if r.get("action_param") else ""
            txt = f"{st} IF {trig_map.get(r.get('trigger'), r.get('trigger'))}{tp}  ==>  {act_map.get(r.get('action'), r.get('action'))}{ap}"
            self.list_rules.addItem(QListWidgetItem(txt))

    def _add_rule(self):
        tid = self.combo_trigger.currentData()
        aid = self.combo_action.currentData()
        tp = self.txt_trigger_param.text().strip()
        ap = self.txt_action_param.text().strip()
        self._rules.append({
            "id": f"rule_{len(self._rules) + 1}_{tid}",
            "enabled": True,
            "trigger": tid,
            "trigger_param": tp,
            "action": aid,
            "action_param": ap,
        })
        self.txt_trigger_param.clear()
        self.txt_action_param.clear()
        self._refresh_list()

    def _toggle_selected(self):
        idx = self.list_rules.currentRow()
        if 0 <= idx < len(self._rules):
            self._rules[idx]["enabled"] = not self._rules[idx].get("enabled", True)
            self._refresh_list()
            self.list_rules.setCurrentRow(idx)

    def _test_selected(self):
        idx = self.list_rules.currentRow()
        if 0 <= idx < len(self._rules) and self.ifttt_engine:
            self.ifttt_engine._execute_action(self._rules[idx])

    def _delete_selected(self):
        idx = self.list_rules.currentRow()
        if 0 <= idx < len(self._rules):
            self._rules.pop(idx)
            self._refresh_list()

    def get_rules(self) -> list:
        return list(self._rules)

class StreamLaunchTab(QWidget):
    """
    Stream Launch Mission Control Tab
    Features NASA-style automated pre-flight diagnostics, custom checklist items,
    and a prominent master 'GO FOR LAUNCH' action that triggers SLOBS streaming,
    starts Chronos stream timers, and activates the Trivia cycler.
    """
    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self.main_win = main_win
        self.overlay = getattr(main_win, "overlay", None)
        self.slobs_client = get_streamlabs_client()

        self._custom_checkboxes = []
        self._is_live = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 8, 12, 8)
        root_layout.setSpacing(8)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # ------------------ TOP HERO: GO FOR LAUNCH CARD ------------------
        card_launch = QFrame()
        card_launch.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #18181b, stop:1 #27272a);
                border: 2px solid #9146ff;
                border-radius: 8px;
                padding: 14px;
            }
        """)
        lay_launch = QVBoxLayout(card_launch)
        lay_launch.setSpacing(10)

        hdr_row = QHBoxLayout()
        lbl_title = QLabel("🚀  <b>MISSION CONTROL - STREAM LAUNCHPAD</b>")
        lbl_title.setStyleSheet("font-size: 14px; color: #efeff1; font-weight: bold; letter-spacing: 0.5px;")
        lbl_title.setToolTip("Central command orchestrator to verify all systems and initiate your broadcast.")
        hdr_row.addWidget(lbl_title)
        hdr_row.addStretch()

        self.lbl_stream_status = QLabel("<span style='color: #a1a1aa;'>● STANDBY</span>")
        self.lbl_stream_status.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_stream_status.setStyleSheet("font-size: 11px; font-weight: bold; padding: 2px 8px; background: #121214; border-radius: 4px; border: 1px solid #3f3f46;")
        hdr_row.addWidget(self.lbl_stream_status)
        lay_launch.addLayout(hdr_row)

        desc_lbl = QLabel(
            "Verify all pre-flight systems below. When ready, trigger the master launch to go live in Streamlabs, "
            "synchronize Chronos stream clocks, and start your Rotating Trivia cycler."
        )
        desc_lbl.setStyleSheet("font-size: 11px; color: #adadb8;")
        desc_lbl.setWordWrap(True)
        lay_launch.addWidget(desc_lbl)

        # Automated Launch Actions Options Box
        opt_box = QFrame()
        opt_box.setStyleSheet("""
            QFrame {
                background-color: rgba(18, 18, 20, 0.6);
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 10px;
            }
        """)
        opt_layout = QVBoxLayout(opt_box)
        opt_layout.setContentsMargins(6, 6, 6, 6)
        opt_layout.setSpacing(6)

        lbl_opt_title = QLabel("⚡ <b>Automated Actions on 'Go for Launch':</b>")
        lbl_opt_title.setStyleSheet("font-size: 11px; color: #efeff1;")
        lbl_opt_title.setToolTip("Select which background streamer tools trigger automatically when Go for Launch is clicked.")
        opt_layout.addWidget(lbl_opt_title)

        chk_row = QHBoxLayout()
        chk_row.setSpacing(16)

        self.chk_launch_chrono = QCheckBox("⏱️ Start Chronos Stream Timer")
        self.chk_launch_chrono.setToolTip("Automatically starts or resumes your Chronos stream timer when Go for Launch is clicked.")
        self.chk_launch_chrono.setStyleSheet("font-size: 11px; color: #efeff1;")

        self.chk_launch_trivia = QCheckBox("📜 Start Trivia / Text Cycler")
        self.chk_launch_trivia.setToolTip("Automatically starts or resumes your Rotating Trivia / Text Cycler when Go for Launch is clicked.")
        self.chk_launch_trivia.setStyleSheet("font-size: 11px; color: #efeff1;")

        # Initialize from overlay / config
        start_chrono = getattr(self.overlay, "launch_start_chrono", True) if self.overlay else True
        start_trivia = getattr(self.overlay, "launch_start_trivia", True) if self.overlay else True
        self.chk_launch_chrono.setChecked(bool(start_chrono))
        self.chk_launch_trivia.setChecked(bool(start_trivia))

        self.chk_launch_chrono.toggled.connect(self._on_launch_options_changed)
        self.chk_launch_trivia.toggled.connect(self._on_launch_options_changed)

        chk_row.addWidget(self.chk_launch_chrono)
        chk_row.addWidget(self.chk_launch_trivia)
        chk_row.addStretch()
        opt_layout.addLayout(chk_row)

        lay_launch.addWidget(opt_box)

        # Big Master Launch + De-Orbit Row
        row_launch_btns = QHBoxLayout()
        row_launch_btns.setSpacing(10)

        self.btn_master_launch = QPushButton("🚀  GO FOR LAUNCH")
        self.btn_master_launch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_master_launch.setToolTip("Initiates Streamlabs broadcast, starts Chronos count-up timer, and activates Trivia cycler.")
        self.btn_master_launch.setStyleSheet("""
            QPushButton {
                background-color: #9146ff;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 12px 20px;
                border-radius: 6px;
                border: 1px solid #a970ff;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background-color: #a970ff;
                border-color: #c084fc;
            }
            QPushButton:pressed {
                background-color: #7c3aed;
            }
        """)
        self.btn_master_launch.clicked.connect(self._on_master_launch_clicked)
        row_launch_btns.addWidget(self.btn_master_launch, 2)

        self.btn_deorbit = QPushButton("☄️  DE-ORBIT / END")
        self.btn_deorbit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_deorbit.setToolTip("Execute automated De-Orbit shutdown sequence (Outro scene, mute mics, countdown, stop stream).")
        self.btn_deorbit.setStyleSheet("""
            QPushButton {
                background-color: #b45309;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 12px 14px;
                border-radius: 6px;
                border: 1px solid #f59e0b;
            }
            QPushButton:hover { background-color: #d97706; }
        """)
        self.btn_deorbit.clicked.connect(self._on_deorbit_clicked)
        row_launch_btns.addWidget(self.btn_deorbit, 1)
        lay_launch.addLayout(row_launch_btns)

        # Safety Abort Window Banner (visible during De-Orbit countdown)
        self.banner_deorbit = QFrame()
        self.banner_deorbit.setStyleSheet(
            "QFrame { background-color: #450a0a; border: 2px solid #ef4444; border-radius: 6px; padding: 8px; }"
        )
        lay_ab = QVBoxLayout(self.banner_deorbit)
        lay_ab.setSpacing(6)
        row_ab_top = QHBoxLayout()
        self.lbl_deorbit_countdown = QLabel("☄️ DE-ORBIT IN PROGRESS — 60s remaining")
        self.lbl_deorbit_countdown.setStyleSheet("color: #fecaca; font-size: 13px; font-weight: bold;")
        row_ab_top.addWidget(self.lbl_deorbit_countdown, 1)

        self.btn_abort_deorbit = QPushButton("🛑  ABORT DE-ORBIT")
        self.btn_abort_deorbit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_abort_deorbit.setStyleSheet(
            "QPushButton { background-color: #dc2626; color: #ffffff; font-weight: bold; padding: 6px 14px; border-radius: 4px; border: 1px solid #fca5a5; }"
            "QPushButton:hover { background-color: #b91c1c; }"
        )
        self.btn_abort_deorbit.clicked.connect(self._on_abort_deorbit_clicked)
        row_ab_top.addWidget(self.btn_abort_deorbit)
        lay_ab.addLayout(row_ab_top)

        self.prog_deorbit = QProgressBar()
        self.prog_deorbit.setRange(0, 60)
        self.prog_deorbit.setValue(60)
        lay_ab.addWidget(self.prog_deorbit)
        self.banner_deorbit.setVisible(False)
        lay_launch.addWidget(self.banner_deorbit)

        layout.addWidget(card_launch)

        # ------------------ CARD 1B: DE-ORBIT & IFTTT AUTOMATION ------------------
        card_deorbit = QFrame()
        card_deorbit.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        lay_de = QVBoxLayout(card_deorbit)
        lay_de.setSpacing(6)
        hdr_de = QHBoxLayout()
        lbl_de_title = QLabel("☄️  <b>De-Orbit Sequence & IFTTT Automation</b>")
        lbl_de_title.setStyleSheet("font-size: 12px; color: #efeff1; font-weight: bold;")
        hdr_de.addWidget(lbl_de_title)
        hdr_de.addStretch()
        self.btn_ifttt_rules = QPushButton("⚡ IFTTT Rules...")
        self.btn_ifttt_rules.setStyleSheet("background-color: #27272a; color: #38bdf8; border: 1px solid #3f3f46; font-weight: bold; padding: 3px 10px; border-radius: 4px;")
        self.btn_ifttt_rules.clicked.connect(self._open_ifttt_rules_dialog)
        hdr_de.addWidget(self.btn_ifttt_rules)
        lay_de.addLayout(hdr_de)

        row_de_cfg = QHBoxLayout()
        row_de_cfg.addWidget(QLabel("Outro Scene:"))
        self.combo_deorbit_scene = QComboBox()
        self.combo_deorbit_scene.setEditable(True)
        self.combo_deorbit_scene.setMinimumWidth(140)
        self.combo_deorbit_scene.addItems(["Stream Ending", "Stream BRB", "Outro"])
        row_de_cfg.addWidget(self.combo_deorbit_scene, 1)

        row_de_cfg.addWidget(QLabel("Countdown (s):"))
        self.spin_deorbit_sec = QSpinBox()
        self.spin_deorbit_sec.setRange(10, 300)
        self.spin_deorbit_sec.setValue(60)
        row_de_cfg.addWidget(self.spin_deorbit_sec)
        lay_de.addLayout(row_de_cfg)

        row_de_chks = QHBoxLayout()
        self.chk_deorbit_mute = QCheckBox("Mute Mics")
        self.chk_deorbit_cycler = QCheckBox("Start Credits / Cycler")
        self.chk_deorbit_stop = QCheckBox("Stop Stream at 0s")
        row_de_chks.addWidget(self.chk_deorbit_mute)
        row_de_chks.addWidget(self.chk_deorbit_cycler)
        row_de_chks.addWidget(self.chk_deorbit_stop)
        row_de_chks.addStretch()
        lay_de.addLayout(row_de_chks)

        row_de_chat = QHBoxLayout()
        row_de_chat.addWidget(QLabel("Farewell Chat:"))
        self.txt_deorbit_chat = QLineEdit()
        self.txt_deorbit_chat.setPlaceholderText("Optional Twitch message on De-Orbit (e.g. Thanks for watching!)")
        row_de_chat.addWidget(self.txt_deorbit_chat, 1)
        lay_de.addLayout(row_de_chat)

        layout.addWidget(card_deorbit)

        # ------------------ CARD 2: AUTOMATED DIAGNOSTICS CHECKLIST ------------------
        card_auto = QFrame()
        card_auto.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_auto = QVBoxLayout(card_auto)
        lay_auto.setSpacing(8)

        lbl_auto_title = QLabel("🛰️  <b>Automated System Telemetry & Readiness</b>")
        lbl_auto_title.setStyleSheet("font-size: 12px; color: #efeff1; font-weight: bold;")
        lbl_auto_title.setToolTip("Live hardware, IPC pipe, and API connectivity status.")
        lay_auto.addWidget(lbl_auto_title)

        self.lbl_chk_slobs = QLabel("• 📡 Streamlabs Desktop: Checking...")
        self.lbl_chk_slobs.setToolTip("Named Pipe and WebSocket RPC connection to Streamlabs Desktop.")
        self.lbl_chk_scene = QLabel("• 🎬 Active Broadcast Scene: Checking...")
        self.lbl_chk_scene.setToolTip("Verifies active broadcast scene name.")
        self.lbl_chk_twitch = QLabel("• 🟣 Twitch Integration: Checking...")
        self.lbl_chk_twitch.setToolTip("Twitch OAuth token validity and target broadcaster channel.")
        self.lbl_chk_audio = QLabel("• 🎙️ Auto-Clip Audio Capture: Checking...")
        self.lbl_chk_audio.setToolTip("Input capture device status and background level tracking.")
        self.lbl_chk_overlay = QLabel("• 🖼️ Monitor Highlight Overlay: Checking...")
        self.lbl_chk_overlay.setToolTip("Hardware border highlight readiness.")
        self.lbl_chk_chrono = QLabel("• ⏱️ Chronos Stream Timer: Checking...")
        self.lbl_chk_chrono.setToolTip("Stream clock status and Go for Launch automation readiness.")
        self.lbl_chk_trivia = QLabel("• 📜 Trivia / Text Cycler: Checking...")
        self.lbl_chk_trivia.setToolTip("Trivia rotation status and Go for Launch automation readiness.")

        for lbl in [self.lbl_chk_slobs, self.lbl_chk_scene, self.lbl_chk_twitch, self.lbl_chk_audio, self.lbl_chk_overlay, self.lbl_chk_chrono, self.lbl_chk_trivia]:
            lbl.setStyleSheet("font-size: 11px; color: #adadb8;")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lay_auto.addWidget(lbl)

        btn_refresh = QPushButton("🔄 Refresh System Telemetry")
        btn_refresh.setToolTip("Re-poll Streamlabs, Twitch token, and audio devices.")
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_refresh.clicked.connect(self.refresh_telemetry)
        lay_auto.addWidget(btn_refresh)

        layout.addWidget(card_auto)

        # ------------------ CARD 3: STREAMER PRE-FLIGHT CHECKLIST ------------------
        card_manual = QFrame()
        card_manual.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        self.lay_manual = QVBoxLayout(card_manual)
        self.lay_manual.setSpacing(6)

        hdr_man = QHBoxLayout()
        lbl_man_title = QLabel("📝  <b>Streamer Pre-Flight Checklist</b>")
        lbl_man_title.setStyleSheet("font-size: 12px; color: #efeff1; font-weight: bold;")
        lbl_man_title.setToolTip("Personalized pre-flight routine. Checked items are saved to config.")
        hdr_man.addWidget(lbl_man_title)
        hdr_man.addStretch()

        btn_reset_chk = QPushButton("Reset Checks")
        btn_reset_chk.setToolTip("Uncheck all items for your next stream.")
        btn_reset_chk.setStyleSheet("background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-size: 10px; padding: 2px 6px; border-radius: 3px;")
        btn_reset_chk.clicked.connect(self._reset_all_checks)
        hdr_man.addWidget(btn_reset_chk)
        self.lay_manual.addLayout(hdr_man)

        self.chk_container = QVBoxLayout()
        self.chk_container.setSpacing(4)
        self.lay_manual.addLayout(self.chk_container)

        # Add custom item bar
        row_add = QHBoxLayout()
        self.txt_new_item = QLineEdit()
        self.txt_new_item.setPlaceholderText("Add custom pre-stream checklist item...")
        self.txt_new_item.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 4px 8px; font-size: 11px; border-radius: 4px;")
        self.txt_new_item.returnPressed.connect(self._add_custom_item)
        row_add.addWidget(self.txt_new_item)

        btn_add = QPushButton("➕ Add Item")
        btn_add.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 4px 10px; font-size: 11px; border-radius: 4px;")
        btn_add.clicked.connect(self._add_custom_item)
        row_add.addWidget(btn_add)
        self.lay_manual.addLayout(row_add)

        layout.addWidget(card_manual)

        layout.addStretch()
        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area)

        # Populate saved or default checklist
        self._populate_checklist()
        self.refresh_telemetry()

        # Connect periodic auto-refresh timer (every 4 seconds)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.setInterval(4000)
        self.telemetry_timer.timeout.connect(self.refresh_telemetry)
        self.telemetry_timer.start()

        # Connect Streamlabs streaming status listener to auto-reset launchpad when stream ends
        if hasattr(self.slobs_client, "streaming_status_changed"):
            self.slobs_client.streaming_status_changed.connect(self._on_slobs_streaming_status)

        self._init_deorbit_wiring()

    def refresh_telemetry(self):
        """Polls active hardware, pipe, and account states."""
        try:
            # 1. SLOBS Status & Broadcast Watchdog
            connected = self.slobs_client.is_connected()
            if connected:
                self.lbl_chk_slobs.setText("• 📡 Streamlabs Desktop: <b style='color: #22c55e;'>Connected (Live Pipe)</b>")
                sc_name = getattr(self.slobs_client, "_active_scene_name", "") or "Active"
                self.lbl_chk_scene.setText(f"• 🎬 Active Broadcast Scene: <b style='color: #38bdf8;'>{sc_name}</b>")

                # Watchdog check: Auto-reset launchpad if stream ended directly in SLOBS
                if hasattr(self.slobs_client, "get_streaming_status"):
                    slobs_status = self.slobs_client.get_streaming_status()
                    if slobs_status in ["offline", "ended"] and self._is_live:
                        log_debug("LAUNCHPAD", "Watchdog detected SLOBS stream offline. Auto-resetting Go for Launch to Standby.")
                        self.reset_to_standby(stop_timers=True)
                    elif slobs_status == "live" and not self._is_live:
                        log_debug("LAUNCHPAD", "Watchdog detected active SLOBS broadcast. Auto-updating Go for Launch to Active.")
                        self._set_live_state(True)
            else:
                self.lbl_chk_slobs.setText("• 📡 Streamlabs Desktop: <b style='color: #ef4444;'>Disconnected / Not Running</b>")
                self.lbl_chk_scene.setText("• 🎬 Active Broadcast Scene: <span style='color: #71717a;'>Waiting for SLOBS...</span>")

            # 2. Twitch Status
            token = getattr(self.overlay, "twitch_token", "")
            channel = getattr(self.overlay, "twitch_channel", "")
            if token and channel:
                self.lbl_chk_twitch.setText(f"• 🟣 Twitch Integration: <b style='color: #a855f7;'>Linked (@{channel})</b>")
            else:
                self.lbl_chk_twitch.setText("• 🟣 Twitch Integration: <span style='color: #eab308;'>Not Linked (Offline Mode)</span>")

            # 3. Audio Capture Status
            eng = getattr(self.overlay, "auto_clip_engine", None)
            if eng and getattr(eng, "enabled", False) and getattr(eng, "streamer_mode", False):
                dev_name = eng.current_device.description() if eng.current_device else "Active Input"
                self.lbl_chk_audio.setText(f"• 🎙️ Auto-Clip Audio: <b style='color: #22c55e;'>Armed ({dev_name[:28]})</b>")
            else:
                self.lbl_chk_audio.setText("• 🎙️ Auto-Clip Audio: <span style='color: #a1a1aa;'>Standby / Opt-In</span>")

            # 4. Overlay Status
            border_armed = getattr(self.overlay, "primary_hotkey_enabled", False)
            border_col = getattr(self.overlay, "border_color", None)
            col_hex = border_col.name() if border_col else "#ff0000"
            if border_armed:
                self.lbl_chk_overlay.setText(f"• 🖼️ Monitor Highlight: <b style='color: {col_hex};'>Armed (Active)</b>")
            else:
                self.lbl_chk_overlay.setText("• 🖼️ Monitor Highlight: <span style='color: #a1a1aa;'>Ready (Hotkeys Disabled)</span>")

            # 5. Chronos Status
            c_auto = self.chk_launch_chrono.isChecked() if hasattr(self, "chk_launch_chrono") else True
            auto_str_c = "<span style='color: #22c55e;'>[Auto-Start: ON]</span>" if c_auto else "<span style='color: #71717a;'>[Auto-Start: OFF]</span>"
            if hasattr(self.overlay, "chronos_engine") and self.overlay.chronos_engine:
                c_state = getattr(self.overlay.chronos_engine, "state", "stopped")
                c_mode = getattr(self.overlay.chronos_engine, "mode", "count_up")
                mode_label = "Count-Down" if c_mode == "count_down" else "Count-Up"
                if c_state == "running":
                    self.lbl_chk_chrono.setText(f"• ⏱️ Chronos Stream Timer: <b style='color: #22c55e;'>Running ({mode_label})</b> {auto_str_c}")
                else:
                    self.lbl_chk_chrono.setText(f"• ⏱️ Chronos Stream Timer: <b style='color: #38bdf8;'>Ready ({mode_label})</b> {auto_str_c}")
            else:
                self.lbl_chk_chrono.setText(f"• ⏱️ Chronos Stream Timer: <span style='color: #a1a1aa;'>Standby</span> {auto_str_c}")

            # 6. Trivia Cycler Status
            t_auto = self.chk_launch_trivia.isChecked() if hasattr(self, "chk_launch_trivia") else True
            auto_str_t = "<span style='color: #22c55e;'>[Auto-Start: ON]</span>" if t_auto else "<span style='color: #71717a;'>[Auto-Start: OFF]</span>"
            if hasattr(self.overlay, "cycler_engine") and self.overlay.cycler_engine:
                t_state = getattr(self.overlay.cycler_engine, "state", "stopped")
                item_count = len(getattr(self.overlay.cycler_engine, "items", []))
                if t_state == "running":
                    self.lbl_chk_trivia.setText(f"• 📜 Trivia / Text Cycler: <b style='color: #22c55e;'>Running ({item_count} items)</b> {auto_str_t}")
                else:
                    self.lbl_chk_trivia.setText(f"• 📜 Trivia / Text Cycler: <b style='color: #38bdf8;'>Ready ({item_count} items loaded)</b> {auto_str_t}")
            else:
                self.lbl_chk_trivia.setText(f"• 📜 Trivia / Text Cycler: <span style='color: #a1a1aa;'>Standby</span> {auto_str_t}")

        except Exception as e:
            log_debug("LAUNCHPAD", f"Telemetry refresh notice: {e}")

    def _on_launch_options_changed(self):
        c_val = self.chk_launch_chrono.isChecked()
        t_val = self.chk_launch_trivia.isChecked()
        if self.overlay:
            self.overlay.launch_start_chrono = c_val
            self.overlay.launch_start_trivia = t_val
            if hasattr(self.overlay, "save_settings"):
                self.overlay.save_settings()
        log_debug("LAUNCHPAD", f"Launch options updated: start_chrono={c_val}, start_trivia={t_val}")
        self.refresh_telemetry()

    def _populate_checklist(self):
        # Clear existing
        while self.chk_container.count() > 0:
            item = self.chk_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._custom_checkboxes = []

        saved_items = getattr(self.overlay, "launch_checklist", None)
        if not saved_items:
            cfg = getattr(self.overlay, "config", {})
            saved_items = cfg.get("launch_checklist", []) if isinstance(cfg, dict) else []
        if not saved_items:
            saved_items = [{"text": t, "checked": False} for t in DEFAULT_CHECKLIST]

        for item_data in saved_items:
            text = item_data.get("text", "") if isinstance(item_data, dict) else str(item_data)
            checked = item_data.get("checked", False) if isinstance(item_data, dict) else False
            self._add_checkbox_widget(text, checked)

    def _add_checkbox_widget(self, text: str, checked: bool = False):
        row = QHBoxLayout()
        chk = QCheckBox(text)
        chk.setChecked(checked)
        chk.setStyleSheet("font-size: 11px; color: #efeff1;")
        chk.toggled.connect(self._save_checklist_state)
        row.addWidget(chk)
        row.addStretch()

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(16, 16)
        btn_del.setToolTip("Delete this checklist item")
        btn_del.setStyleSheet("background: transparent; color: #71717a; border: none; font-size: 10px;")
        btn_del.clicked.connect(lambda: self._delete_checkbox_item(row, chk))
        row.addWidget(btn_del)

        self.chk_container.addLayout(row)
        self._custom_checkboxes.append((chk, row))

    def _add_custom_item(self):
        text = self.txt_new_item.text().strip()
        if not text:
            return
        self._add_checkbox_widget(text, False)
        self.txt_new_item.clear()
        self._save_checklist_state()

    def _delete_checkbox_item(self, row_layout, chk_widget):
        for idx, (c, r) in enumerate(self._custom_checkboxes):
            if c == chk_widget:
                self._custom_checkboxes.pop(idx)
                break
        while row_layout.count() > 0:
            it = row_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._save_checklist_state()

    def _reset_all_checks(self):
        for chk, _ in self._custom_checkboxes:
            chk.setChecked(False)
        self._save_checklist_state()

    def _save_checklist_state(self):
        items = []
        for chk, _ in self._custom_checkboxes:
            items.append({"text": chk.text(), "checked": chk.isChecked()})
        if self.overlay:
            self.overlay.launch_checklist = items
            if hasattr(self.overlay, "save_settings"):
                self.overlay.save_settings()


    def _on_master_launch_clicked(self):
        if not self._is_live:
            # Trigger Launch!
            log_debug("LAUNCHPAD", "Master 'GO FOR LAUNCH' triggered by user.")
            
            # 1. Start Stream in SLOBS if connected
            if self.slobs_client.is_connected():
                try:
                    self.slobs_client._call_rpc("toggleStreaming", "StreamingService")
                    log_debug("LAUNCHPAD", "Dispatched toggleStreaming to Streamlabs StreamingService.")
                except Exception as e:
                    log_debug("LAUNCHPAD", f"Error toggling streaming: {e}")
            else:
                log_debug("LAUNCHPAD", "Streamlabs not connected; continuing local timers.")

            # 2. Start Chronos Timers (if option enabled)
            start_chrono = self.chk_launch_chrono.isChecked() if hasattr(self, "chk_launch_chrono") else True
            if start_chrono:
                if hasattr(self.overlay, "chronos_engine") and self.overlay.chronos_engine:
                    try:
                        self.overlay.chronos_engine.start()
                        log_debug("LAUNCHPAD", "Started Chronos stream timers.")
                    except Exception as e:
                        log_debug("LAUNCHPAD", f"Chronos start error: {e}")
            else:
                log_debug("LAUNCHPAD", "Skipping Chronos start (launch option unchecked).")

            # 3. Start Rotating Trivia Cycler (if option enabled)
            start_trivia = self.chk_launch_trivia.isChecked() if hasattr(self, "chk_launch_trivia") else True
            if start_trivia:
                if hasattr(self.overlay, "cycler_engine") and self.overlay.cycler_engine:
                    try:
                        self.overlay.cycler_engine.start()
                        log_debug("LAUNCHPAD", "Started Trivia / Rotating Text cycler.")
                    except Exception as e:
                        log_debug("LAUNCHPAD", f"Cycler start error: {e}")
            else:
                log_debug("LAUNCHPAD", "Skipping Trivia Cycler start (launch option unchecked).")

            # 4. Flash temporary green confirmation border
            if hasattr(self.overlay, "flash_temporary_alert"):
                self.overlay.flash_temporary_alert(duration_ms=2000, color=QColor("#22c55e"))

            # 5. Play chime
            if hasattr(self.overlay, "soundboard_engine") and self.overlay.soundboard_engine:
                try:
                    self.overlay.soundboard_engine.play_marker_chime()
                except Exception:
                    pass

            self._set_live_state(True)
            if hasattr(self.overlay, "show_hud_toast"):
                self.overlay.show_hud_toast("🚀 STREAM LAUNCH INITIATED! Good luck with your broadcast!", True)
        else:
            # Stop broadcast
            confirm = QMessageBox.question(
                self,
                "End Stream Broadcast?",
                "Are you sure you want to stop the live stream and stop timers?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                log_debug("LAUNCHPAD", "User ended broadcast from launchpad.")
                if self.slobs_client.is_connected():
                    try:
                        self.slobs_client._call_rpc("stopStreaming", "StreamingService")
                    except Exception:
                        pass
                self.reset_to_standby(stop_timers=True)

    def _set_live_state(self, is_live: bool, stop_timers: bool = True):
        """Updates internal state, status indicator, button style, and optionally stops timers."""
        self._is_live = bool(is_live)
        if self._is_live:
            self.lbl_stream_status.setText("<span style='color: #22c55e;'>● BROADCAST ACTIVE</span>")
            self.btn_master_launch.setText("🔴  STREAM LIVE (STOP BROADCAST)")
            self.btn_master_launch.setStyleSheet("""
                QPushButton {
                    background-color: #ef4444;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 12px 20px;
                    border-radius: 6px;
                    border: 1px solid #f87171;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background-color: #dc2626;
                }
                QPushButton:pressed {
                    background-color: #b91c1c;
                }
            """)
        else:
            if stop_timers:
                if hasattr(self.overlay, "chronos_engine") and self.overlay.chronos_engine:
                    self.overlay.chronos_engine.stop()
                if hasattr(self.overlay, "cycler_engine") and self.overlay.cycler_engine:
                    self.overlay.cycler_engine.stop()

            self.lbl_stream_status.setText("<span style='color: #a1a1aa;'>● STANDBY</span>")
            self.btn_master_launch.setText("🚀  GO FOR LAUNCH")
            self.btn_master_launch.setStyleSheet("""
                QPushButton {
                    background-color: #9146ff;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 12px 20px;
                    border-radius: 6px;
                    border: 1px solid #a970ff;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background-color: #a970ff;
                    border-color: #c084fc;
                }
                QPushButton:pressed {
                    background-color: #7c3aed;
                }
            """)

    def reset_to_standby(self, stop_timers: bool = True):
        """Public method to return Launchpad to Standby mode, resetting button appearance and timers."""
        self._set_live_state(False, stop_timers=stop_timers)

    def _on_slobs_streaming_status(self, status: str):
        """Triggered on real-time SLOBS streamingStatusChange events."""
        status = str(status).lower()
        log_debug("LAUNCHPAD", f"Received SLOBS streaming status event: '{status}'")
        if status in ["offline", "ended"]:
            if self._is_live:
                log_debug("LAUNCHPAD", "Stream broadcast ended in Streamlabs Desktop. Auto-resetting Launchpad to Standby.")
                self.reset_to_standby(stop_timers=True)
                if hasattr(self.overlay, "show_hud_toast"):
                    self.overlay.show_hud_toast("⏹️ Stream broadcast ended in Streamlabs. Launchpad returned to Standby.", False)
        elif status == "live":
            if not self._is_live:
                log_debug("LAUNCHPAD", "Stream broadcast detected LIVE in Streamlabs Desktop. Updating Launchpad state.")
                self._set_live_state(True)

    def _init_deorbit_wiring(self):
        de = getattr(self.overlay, "deorbit_engine", None) if self.overlay else None
        if de:
            self.combo_deorbit_scene.setCurrentText(de.outro_scene_name)
            self.spin_deorbit_sec.setValue(int(de.countdown_seconds))
            self.chk_deorbit_mute.setChecked(bool(de.mute_mics))
            self.chk_deorbit_cycler.setChecked(bool(de.start_credits_cycler))
            self.chk_deorbit_stop.setChecked(bool(de.stop_stream_on_finish))
            self.txt_deorbit_chat.setText(de.farewell_chat_message)

            de.deorbit_started.connect(self._on_deorbit_started)
            de.deorbit_tick.connect(self._on_deorbit_tick)
            de.deorbit_completed.connect(self._on_deorbit_finished)
            de.deorbit_aborted.connect(self._on_deorbit_finished)

        self.combo_deorbit_scene.currentTextChanged.connect(self._sync_deorbit_settings)
        self.spin_deorbit_sec.valueChanged.connect(self._sync_deorbit_settings)
        self.chk_deorbit_mute.toggled.connect(self._sync_deorbit_settings)
        self.chk_deorbit_cycler.toggled.connect(self._sync_deorbit_settings)
        self.chk_deorbit_stop.toggled.connect(self._sync_deorbit_settings)
        self.txt_deorbit_chat.editingFinished.connect(self._sync_deorbit_settings)

    def _sync_deorbit_settings(self):
        de = getattr(self.overlay, "deorbit_engine", None) if self.overlay else None
        if not de:
            return
        de.outro_scene_name = self.combo_deorbit_scene.currentText().strip()
        de.countdown_seconds = int(self.spin_deorbit_sec.value())
        de.mute_mics = self.chk_deorbit_mute.isChecked()
        de.start_credits_cycler = self.chk_deorbit_cycler.isChecked()
        de.stop_stream_on_finish = self.chk_deorbit_stop.isChecked()
        de.farewell_chat_message = self.txt_deorbit_chat.text().strip()
        if hasattr(self.overlay, "save_settings"):
            self.overlay.save_settings()

    def _on_deorbit_clicked(self):
        self._sync_deorbit_settings()
        de = getattr(self.overlay, "deorbit_engine", None) if self.overlay else None
        if not de:
            return
        if de.is_active:
            return
        de.start_deorbit()

    def _on_abort_deorbit_clicked(self):
        de = getattr(self.overlay, "deorbit_engine", None) if self.overlay else None
        if de and de.is_active:
            de.abort_deorbit()

    def _on_deorbit_started(self, total_sec: int):
        self.prog_deorbit.setRange(0, max(1, total_sec))
        self.prog_deorbit.setValue(total_sec)
        self.lbl_deorbit_countdown.setText(f"☄️ DE-ORBIT IN PROGRESS — {total_sec}s remaining")
        self.banner_deorbit.setVisible(True)
        self.btn_deorbit.setEnabled(False)

    def _on_deorbit_tick(self, rem_sec: int, total_sec: int):
        self.prog_deorbit.setValue(max(0, rem_sec))
        self.lbl_deorbit_countdown.setText(f"☄️ DE-ORBIT IN PROGRESS — {rem_sec}s remaining")

    def _on_deorbit_finished(self):
        self.banner_deorbit.setVisible(False)
        self.btn_deorbit.setEnabled(True)
        de = getattr(self.overlay, "deorbit_engine", None) if self.overlay else None
        if de and not de.is_active and de.remaining_seconds <= 0:
            self.reset_to_standby(stop_timers=True)

    def _open_ifttt_rules_dialog(self):
        ifttt = getattr(self.overlay, "ifttt_engine", None) if self.overlay else None
        dlg = IFTTTRulesDialog(ifttt, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and ifttt:
            ifttt.load_rules(dlg.get_rules())
            if hasattr(self.overlay, "save_settings"):
                self.overlay.save_settings()

    def refresh_theme_labels(self, effective):
        pass

