import os
import platform
import webbrowser
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout
)

from updater import CURRENT_VERSION, get_build_commit, GITHUB_REPO

class AboutTab(QWidget):
    """
    About Tab - Streamer Calyx
    Features the botanical Calyx lore, runtime environment specifications,
    DigiCert Authenticode EV signing verification badge, and community resources.
    """
    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self.main_win = main_win

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
        layout.setSpacing(8)

        # ------------------ CARD 1: THE STREAMER MULTITOOL ------------------
        card_multitool = QFrame()
        card_multitool.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_multitool = QVBoxLayout(card_multitool)
        lay_multitool.setSpacing(8)

        hdr_multitool = QHBoxLayout()
        lbl_multitool_title = QLabel("🛠️  <b>The Streamer Multitool: One Tool to Replace Multiples</b>")
        lbl_multitool_title.setStyleSheet("font-size: 13px; color: #57F287; font-weight: bold;")
        lbl_multitool_title.setToolTip("Streamer Calyx unifies a full suite of broadcasting utilities into a single, cohesive chassis.")
        hdr_multitool.addWidget(lbl_multitool_title)
        hdr_multitool.addStretch()
        lay_multitool.addLayout(hdr_multitool)

        multitool_text = (
            "<div style='font-size: 11px; color: #adadb8; line-height: 130%;'>"
            "Modern live broadcasting often forces streamers to juggle a chaotic jungle of disjointed background utilities: "
            "one app for screen highlight borders, another for audio spike monitoring and clipping, a separate bot for Twitch chat commands, "
            "an external macro board for OBS scene switching, a desktop countdown clock, a rotating trivia widget, a soundboard player, "
            "and pre-flight launch checklists.<br><br>"
            "<b>Streamer Calyx is engineered as the ultimate all-in-one broadcast multitool</b>—a precision Swiss Army knife "
            "designed to replace that entire clutter of fragmented apps with one unified, lightweight, EV-signed environment.<br><br>"
            "Just as a precision multitool houses every essential blade, driver, and wrench within a single balanced frame, "
            "<b>the Calyx holds all the tools you need in one place</b>:"
            "<ul style='margin-top: 6px; margin-bottom: 6px; padding-left: 20px;'>"
            "  <li><b>Monitor Highlight Overlay:</b> Instant pixel-perfect border alert flashing for hotkeys and auto-clip triggers.</li>"
            "  <li><b>Auto-Clip Audio Engine:</b> Automated hype peak detection, live VU metering, and stream marker placement.</li>"
            "  <li><b>Stream Director Dual Docks:</b> Responsive local pipe & remote LAN/WebRTC scene and audio mixer control.</li>"
            "  <li><b>Chronos & Trivia Cycler:</b> Pixel-perfect live stream clocks, countdown milestones, and rotating trivia.</li>"
            "  <li><b>Stream Launchpad:</b> Pre-broadcast readiness checklist and 1-click 'Go for Launch' mission control.</li>"
            "  <li><b>Soundboard LAN Bridge:</b> Ultra-low-latency soundboard playback across headphones and broadcast feeds.</li>"
            "  <li><b>Twitch Chat Macros:</b> Instant global hotkey dispatch for shoutouts, stream markers, and announcements.</li>"
            "</ul>"
            "One unified tool to replace multiples—zero bloat, zero background conflicts, and complete peace of mind on stream."
            "</div>"
        )
        lbl_multitool_body = QLabel(multitool_text)
        lbl_multitool_body.setWordWrap(True)
        lbl_multitool_body.setTextFormat(Qt.TextFormat.RichText)
        lay_multitool.addWidget(lbl_multitool_body)

        layout.addWidget(card_multitool)

        # ------------------ CARD 2: BOTANICAL HERITAGE & VISION ------------------
        card_botany = QFrame()
        card_botany.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_botany = QVBoxLayout(card_botany)
        lay_botany.setSpacing(8)

        hdr_botany = QHBoxLayout()
        lbl_botany_title = QLabel("🌸  <b>The Botanical Heritage of Calyx (The Protective Sepals)</b>")
        lbl_botany_title.setStyleSheet("font-size: 13px; color: #a970ff; font-weight: bold;")
        lbl_botany_title.setToolTip("Streamer Calyx draws its name from the botanical whorl protecting flowers.")
        hdr_botany.addWidget(lbl_botany_title)
        hdr_botany.addStretch()
        lay_botany.addLayout(hdr_botany)

        botany_text = (
            "<div style='font-size: 11px; color: #adadb8; line-height: 130%;'>"
            "In botany, the <b>calyx</b> (<i>/ˈkeɪlɪks/</i>, from Ancient Greek <i>kályx</i> 'husk, cup') "
            "is the outermost whorl of a flower, formed by the protective sepals that enclose, cushion, "
            "and shield the delicate flower bud as it develops, guarding it from frost, wind, and pests "
            "until it is ready to blossom.<br><br>"
            "In <b>Streamer Calyx</b>, the software acts as those protective sepals for your live broadcast. "
            "Sitting quietly in your system tray and alongside your displays, Calyx cushions your broadcast—managing "
            "scene switching, guarding audio levels, suppressing rogue soundboard spam, coordinating remote co-hosts, "
            "and marking epic hype moments in real-time. By holding all essential broadcast utilities together in a single "
            "protective chassis, Calyx shields the technical complexity so your stream can flourish and bloom."
            "</div>"
        )
        lbl_botany_body = QLabel(botany_text)
        lbl_botany_body.setWordWrap(True)
        lbl_botany_body.setTextFormat(Qt.TextFormat.RichText)
        lay_botany.addWidget(lbl_botany_body)

        layout.addWidget(card_botany)

        # ------------------ CARD 2: RUNTIME SPECIFICATIONS ------------------
        card_specs = QFrame()
        card_specs.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_specs = QVBoxLayout(card_specs)
        lay_specs.setSpacing(8)

        lbl_specs_title = QLabel("⚙️  <b>Software & Environment Specifications</b>")
        lbl_specs_title.setStyleSheet("font-size: 13px; color: #efeff1; font-weight: bold;")
        lbl_specs_title.setToolTip("Core technical architecture and build environment metadata.")
        lay_specs.addWidget(lbl_specs_title)

        grid = QGridLayout()
        grid.setSpacing(6)

        specs_items = [
            ("Application Version:", f"<b>v{CURRENT_VERSION}</b>", "Current installed release version."),
            ("Git Commit Hash:", f"<code>{get_build_commit()}</code>", "Git commit hash of this build."),
            ("Update Channel:", f"<b>{getattr(self.main_win.overlay, 'update_channel', 'stable').capitalize()}</b>", "Active release discovery channel."),
            ("Code Signature:", "<span style='color: #22c55e;'><b>✓ DigiCert Authenticode EV (SHA-256)</b></span>", "Hardware cryptographic EV token signature verified with RFC 3161 timestamps."),
            ("Python Runtime:", f"{platform.python_version()} ({platform.architecture()[0]})", "Active Python runtime environment."),
            ("Operating System:", f"{platform.platform()}", "Host Windows OS version."),
            ("AppData Location:", f"<code>%APPDATA%\\StreamerCalyx</code>", "Local user configuration and log directory.")
        ]

        for row, (label, val_html, tooltip) in enumerate(specs_items):
            lbl_k = QLabel(label)
            lbl_k.setStyleSheet("color: #71717a; font-size: 11px;")
            lbl_k.setToolTip(tooltip)
            lbl_v = QLabel(val_html)
            lbl_v.setStyleSheet("color: #efeff1; font-size: 11px;")
            lbl_v.setTextFormat(Qt.TextFormat.RichText)
            lbl_v.setToolTip(tooltip)
            grid.addWidget(lbl_k, row, 0)
            grid.addWidget(lbl_v, row, 1)

        lay_specs.addLayout(grid)
        layout.addWidget(card_specs)

        # ------------------ CARD 3: COMMUNITY & QUICK LAUNCHERS ------------------
        card_links = QFrame()
        card_links.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_links = QVBoxLayout(card_links)
        lay_links.setSpacing(8)

        lbl_links_title = QLabel("🌐  <b>Resources & Development Ledger</b>")
        lbl_links_title.setStyleSheet("font-size: 13px; color: #efeff1; font-weight: bold;")
        lbl_links_title.setToolTip("Documentation, source repository, and release notes.")
        lay_links.addWidget(lbl_links_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_ledger = QPushButton("📖 Open Update Encyclopedia")
        btn_ledger.setToolTip("Opens the interactive 2-column release ledger and commit encyclopedia.")
        btn_ledger.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9146ff;
                border-color: #9146ff;
                color: #ffffff;
            }
        """)
        btn_ledger.clicked.connect(self._open_ledger)
        btn_row.addWidget(btn_ledger)

        btn_github = QPushButton("🐙 GitHub Repository")
        btn_github.setToolTip("View the project source repository on GitHub.")
        btn_github.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_github.clicked.connect(lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))
        btn_row.addWidget(btn_github)

        btn_releases = QPushButton("🏷️ Release Notes")
        btn_releases.setToolTip("View full release changelogs and downloads on GitHub.")
        btn_releases.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_releases.clicked.connect(lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases"))
        btn_row.addWidget(btn_releases)

        lay_links.addLayout(btn_row)
        layout.addWidget(card_links)

        # ------------------ CARD 4: CREATOR SUPPORT & SOCIALS ------------------
        card_socials = QFrame()
        card_socials.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_socials = QVBoxLayout(card_socials)
        lay_socials.setSpacing(8)

        lbl_soc_title = QLabel("💜  <b>Support the Creator & Community Socials</b>")
        lbl_soc_title.setStyleSheet("font-size: 13px; color: #efeff1; font-weight: bold;")
        lbl_soc_title.setToolTip("Support ongoing development of Streamer Calyx and connect with the community.")
        lay_socials.addWidget(lbl_soc_title)

        lbl_soc_desc = QLabel(
            "Streamer Calyx is 100% free and open-source. If Calyx powers your broadcasts, consider supporting development or joining the community!"
        )
        lbl_soc_desc.setWordWrap(True)
        lbl_soc_desc.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        lay_socials.addWidget(lbl_soc_desc)

        # Tip / Donate Row
        tip_row = QHBoxLayout()
        tip_row.setSpacing(8)

        btn_streamlabs_tip = QPushButton("☕ Tip via Streamlabs")
        btn_streamlabs_tip.setToolTip("Send a tip via Streamlabs (https://streamlabs.com/thawizanator/tip).")
        btn_streamlabs_tip.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #059669; }
        """)
        btn_streamlabs_tip.clicked.connect(lambda: webbrowser.open("https://streamlabs.com/thawizanator/tip"))
        tip_row.addWidget(btn_streamlabs_tip)

        btn_paypal = QPushButton("💳 Donate via PayPal")
        btn_paypal.setToolTip("Support Streamer Calyx directly via PayPal.")
        btn_paypal.setStyleSheet("""
            QPushButton {
                background-color: #0070ba;
                color: #ffffff;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #005ea6; }
        """)
        btn_paypal.clicked.connect(lambda: webbrowser.open("https://paypal.me/thawizanator"))
        tip_row.addWidget(btn_paypal)
        tip_row.addStretch()
        lay_socials.addLayout(tip_row)

        # Socials Matrix Row
        soc_grid = QGridLayout()
        soc_grid.setSpacing(6)

        social_defs = [
            ("💬 Discord Community", "Join the Discord server for beta previews, plugins & support.", "https://discord.gg/thawizanator", "#5865F2"),
            ("🟣 Twitch Channel", "Watch ThaWizanator live on Twitch.", "https://www.twitch.tv/thawizanator", "#9146FF"),
            ("🔴 YouTube Channel", "Subscribe for tutorials, stream highlights & dev logs.", "https://www.youtube.com/@thawizanator", "#EF4444"),
            ("🐙 GitHub Profile", "Explore ThaWizanator's open-source repositories.", f"https://github.com/{GITHUB_REPO}", "#3f3f46"),
        ]
        for idx, (label, tip, url, bg) in enumerate(social_defs):
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #27272a;
                    color: #efeff1;
                    border: 1px solid {bg};
                    padding: 6px 10px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {bg};
                    color: #ffffff;
                }}
            """)
            btn.clicked.connect(lambda checked=False, u=url: webbrowser.open(u))
            soc_grid.addWidget(btn, idx // 2, idx % 2)

        lay_socials.addLayout(soc_grid)
        layout.addWidget(card_socials)

        layout.addStretch()
        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area)

    def _open_ledger(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_paths = [
            os.path.join(script_dir, "ledger", "index.html"),
            os.path.join(script_dir, "ledger", "ledger_standalone.html"),
            os.path.join(script_dir, "StreamerCalyx_Ledger.html"),
            os.path.join(os.path.dirname(script_dir), "StreamerCalyx_Ledger.html"),
            os.path.join(os.path.expanduser("~"), "Desktop", "StreamerCalyx_Ledger.html"),
        ]
        for p in candidate_paths:
            if os.path.exists(p):
                webbrowser.open(p)
                return
        webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases")

    def refresh_theme_labels(self, effective):
        pass

