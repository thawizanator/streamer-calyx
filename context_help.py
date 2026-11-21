import os
import sys
import json
from PyQt6.QtCore import QObject, QEvent, Qt
from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QAbstractButton, QComboBox, QCheckBox, QSlider
)
import theme_manager


def load_context_help_db() -> dict:
    """
    Loads contextual help entries from external context_help.json files,
    merging user overrides in %APPDATA%\\StreamerCalyx\\context_help.json
    over the bundled context_help.json and built-in fallback dictionary.
    """
    merged = {k: (v[0], v[1]) for k, v in CONTEXT_HELP_DB.items()}
    candidate_paths = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        meipass = getattr(sys, "_MEIPASS", exe_dir)
        candidate_paths.append(os.path.join(meipass, "context_help.json"))
        candidate_paths.append(os.path.join(exe_dir, "context_help.json"))
    else:
        candidate_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "context_help.json"))

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidate_paths.append(os.path.join(appdata, "StreamerCalyx", "context_help.json"))

    for path in candidate_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key, val in data.items():
                        if isinstance(val, dict) and "body" in val:
                            merged[key.lower().strip()] = (val.get("title", key), val["body"])
                        elif isinstance(val, str):
                            merged[key.lower().strip()] = (key, val)
            except Exception:
                pass
    return merged


# Rich contextual help entries keyed by substring/keyword match on objectName, label, or tooltip
CONTEXT_HELP_DB = {
    "streamer mode": (
        "Streamer Mode Toggle",
        "Enables live broadcast integrations including Auto-Clip audio monitoring, "
        "Stream Director remote co-host connections, and Twitch Stream Markers.\n\n"
        "Tip: Turn this OFF when you are not live to pause background audio capture and save CPU."
    ),
    "highlight hotkey": (
        "Primary Alert Highlight Hotkey",
        "Global shortcut that flashes your selected monitor's border overlay to grab attention.\n\n"
        "You can bind keyboard chords, mouse side buttons, or gamepad combos here or in the "
        "Unified Hotkeys & Peripherals tab — both stay synced automatically."
    ),
    "launchpad": (
        "Stream Launchpad & Mission Control",
        "Your pre-flight broadcast checklist and 1-Click 'GO FOR LAUNCH' trigger.\n\n"
        "Verifies OBS/Streamlabs connection, starts Chronos timers, enables Rotating Text, "
        "and takes your stream live in one action."
    ),
    "stream director": (
        "Stream Director & Remote Co-Host",
        "Allows trusted remote co-hosts or moderators to switch scenes, mute audio tracks, "
        "and adjust faders over encrypted P2P WebRTC with granular per-element permissions."
    ),
    "auto-clip": (
        "Auto-Clip & Stream Markers",
        "Monitors your microphone or VoiceMeeter input in real time to detect hype moments "
        "and automatically drop Twitch Stream Markers with pre/post clip timing."
    ),
    "soundboard": (
        "Soundboard & Anti-Spam Troll Shield",
        "Plays local audio cues and lets authorized remote directors trigger sounds. "
        "Includes rate-limiting and panic lock protection against rapid-fire spam."
    ),
    "chronos": (
        "Chronos Live Stream Timers",
        "Multi-timer suite supporting Countdowns, Stopwatches, and Interval timers with "
        "automatic OBS/SLOBS text file output (timer_display.txt)."
    ),
    "rotating text": (
        "Rotating Text & Trivia Cycler",
        "Automatically cycles rules, sponsor shoutouts, social links, or interactive Trivia Q&A "
        "to an OBS/SLOBS text file on a configurable schedule."
    ),
    "audio devices": (
        "Audio Devices & Routing",
        "Master hub for selecting your Windows WASAPI microphone/VoiceMeeter capture device "
        "and your Soundboard/Alert playback output device. Changes sync across all tabs."
    ),
    "monitor setup": (
        "Multi-Monitor Configuration",
        "Select which physical display receives the border alert overlay and configure "
        "DPI awareness mode for mixed-resolution multi-monitor setups."
    ),
    "hotkeys": (
        "Unified Hotkeys & Peripherals",
        "Central binding manager for keyboard chords, Mouse 3/4/5, and XInput gamepads. "
        "Supports hold thresholds and multi-button release shielding."
    ),
}


class ContextHelpDialog(QDialog):
    """Floating 'What is this?' help card triggered via Shift + Right-Click."""

    def __init__(self, title: str, body: str, section: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("What is this? — Streamer Calyx Help")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(360)
        self.setMaximumWidth(480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # Header badge
        hdr_row = QHBoxLayout()
        lbl_badge = QLabel("💡 CONTEXT HELP")
        lbl_badge.setStyleSheet(
            "background-color: #9146ff; color: white; font-size: 10px; "
            "font-weight: bold; padding: 2px 8px; border-radius: 4px;"
        )
        hdr_row.addWidget(lbl_badge)
        if section:
            lbl_sec = QLabel(section)
            lbl_sec.setStyleSheet("font-size: 11px; color: #a1a1aa;")
            hdr_row.addWidget(lbl_sec)
        hdr_row.addStretch()
        lay.addLayout(hdr_row)

        lbl_title = QLabel(f"<b>{title}</b>")
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet("font-size: 14px;")
        lay.addWidget(lbl_title)

        lbl_body = QLabel(body.replace("\n", "<br>"))
        lbl_body.setWordWrap(True)
        lbl_body.setTextFormat(Qt.TextFormat.RichText)
        lbl_body.setStyleSheet("font-size: 12px; line-height: 1.45;")
        lay.addWidget(lbl_body)

        lbl_hint = QLabel("<i>Tip: Shift + Right-Click any control in Streamer Calyx for quick help.</i>")
        lbl_hint.setStyleSheet("font-size: 10px; color: #71717a;")
        lay.addWidget(lbl_hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("Got it")
        btn_ok.setDefault(True)
        btn_ok.setStyleSheet(
            "background-color: #9146ff; color: white; font-weight: bold; "
            "padding: 5px 16px; border-radius: 4px;"
        )
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        try:
            theme_manager.apply_theme_to_window(self, "system")
        except Exception:
            pass


class ContextHelpFilter(QObject):
    """
    Application-level event filter listening for Shift + Right-Click on any
    widget inside the SettingsWindow to open a contextual 'What is this?' help card.
    """

    def __init__(self, settings_win):
        super().__init__(settings_win)
        self.settings_win = settings_win

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if (
                event.button() == Qt.MouseButton.RightButton
                and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                and isinstance(obj, QWidget)
            ):
                if obj.window() is self.settings_win:
                    self._show_help_for_widget(obj)
                    return True
        return False

    def _show_help_for_widget(self, widget: QWidget):
        title = ""
        tooltip = ""
        section = ""

        # Walk up widget tree to gather best title, tooltip, and GroupBox section
        cur = widget
        while cur is not None and cur is not self.settings_win:
            if not tooltip and cur.toolTip():
                tooltip = cur.toolTip().strip()
            if not title:
                if isinstance(cur, (QAbstractButton, QCheckBox, QLabel)):
                    txt = cur.text().strip()
                    if txt and len(txt) < 80:
                        title = txt.replace("&&", "&")
                elif isinstance(cur, QGroupBox) and cur.title():
                    title = cur.title().strip()
            if not section and isinstance(cur, QGroupBox) and cur.title():
                section = cur.title().strip()
            cur = cur.parentWidget()

        if not section and hasattr(self.settings_win, "lbl_page_title"):
            section = self.settings_win.lbl_page_title.text().strip()

        # Check external JSON + built-in database
        search_blob = f"{title} {tooltip} {section} {widget.objectName()}".lower()
        body = ""
        help_db = load_context_help_db()
        for key, (db_title, db_body) in sorted(help_db.items(), key=lambda kv: len(kv[0]), reverse=True):
            if key in search_blob:
                if not title:
                    title = db_title
                body = db_body
                break

        if not body:
            if tooltip:
                body = tooltip
            else:
                body = (
                    f"This control belongs to <b>{section or 'Streamer Calyx'}</b>. "
                    "Hover over individual buttons or sliders to see quick tooltips, "
                    "or check the Logs & System tabs for diagnostics."
                )

        if not title:
            title = section or "Streamer Calyx Control"

        dlg = ContextHelpDialog(title=title, body=body, section=section, parent=self.settings_win)
        dlg.exec()
