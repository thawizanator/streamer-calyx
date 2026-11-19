"""
Phase 13 UI: Multi-Platform Broadcast Gateway Tab (YouTube Live & Kick)
"""
from __future__ import annotations

import os
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from platform_gateway import (
    KickOAuthWorker,
    MultiPlatformGateway,
    YOUTUBE_MARKERS_FILE,
    YouTubeOAuthWorker,
)


class MultiPlatformGatewayTab(QWidget):
    """Settings tab for Phase 13: Multi-Platform Broadcast Gateway."""

    def __init__(self, main_window, gateway: MultiPlatformGateway):
        super().__init__()
        self.main_win = main_window
        self.overlay = getattr(main_window, "overlay", None)
        self.gateway = gateway
        self._yt_oauth_worker = None
        self._kick_oauth_worker = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root_layout.addWidget(scroll)

        container = QWidget()
        container.setMinimumWidth(0)
        container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 18, 12)
        layout.setSpacing(10)
        scroll.setWidget(container)

        # ------------------------------------------------------------------
        # 1. Header & Simulation Mode Banner
        # ------------------------------------------------------------------
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet(
            "QFrame { background: rgba(145, 70, 255, 0.10); border: 1px solid rgba(145, 70, 255, 0.35); border-radius: 8px; }"
        )
        hdr_lay = QVBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(12, 10, 12, 10)
        hdr_lay.setSpacing(6)

        top_row = QHBoxLayout()
        lbl_title = QLabel("🌐 <b>Multi-Platform Broadcast Gateway</b>")
        lbl_title.setStyleSheet("font-size: 13px; border: none; background: transparent;")
        top_row.addWidget(lbl_title, 1)

        self.lbl_active_dests = QLabel("Active: Twitch")
        self.lbl_active_dests.setStyleSheet(
            "font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px; "
            "background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35);"
        )
        top_row.addWidget(self.lbl_active_dests)
        hdr_lay.addLayout(top_row)

        lbl_sub = QLabel(
            "Route stream markers, titles, categories, and chat announcements concurrently to "
            "<b>Twitch</b>, <b>YouTube Live</b>, and <b>Kick</b>."
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("font-size: 11px; opacity: 0.85; border: none; background: transparent;")
        hdr_lay.addWidget(lbl_sub)

        self.chk_dry_run = QCheckBox("🧪 Dry-Run / Simulation Mode (test offline or without Kick)")
        self.chk_dry_run.setChecked(self.gateway.dry_run_mode)
        self.chk_dry_run.setStyleSheet("font-size: 11px; font-weight: bold; border: none; background: transparent;")
        self.chk_dry_run.toggled.connect(self._on_config_changed)
        hdr_lay.addWidget(self.chk_dry_run)

        layout.addWidget(hdr_frame)

        # ------------------------------------------------------------------
        # 2. Twitch Destination Card
        # ------------------------------------------------------------------
        grp_tw = QGroupBox("🟣 Twitch Destination")
        lay_tw = QVBoxLayout(grp_tw)
        lay_tw.setSpacing(6)

        tw_row = QHBoxLayout()
        self.chk_tw_enabled = QCheckBox("Include Twitch in Dispatcher")
        self.chk_tw_enabled.setChecked(self.gateway.twitch_enabled)
        self.chk_tw_enabled.toggled.connect(self._on_config_changed)
        tw_row.addWidget(self.chk_tw_enabled)
        tw_row.addStretch()

        btn_open_tw = QPushButton("Open Twitch Tab")
        btn_open_tw.clicked.connect(lambda: self.main_win.set_view_index(3) if hasattr(self.main_win, "set_view_index") else None)
        tw_row.addWidget(btn_open_tw)
        lay_tw.addLayout(tw_row)

        self.lbl_tw_status = QLabel()
        self.lbl_tw_status.setWordWrap(True)
        self.lbl_tw_status.setStyleSheet("font-size: 11px;")
        lay_tw.addWidget(self.lbl_tw_status)
        layout.addWidget(grp_tw)

        # ------------------------------------------------------------------
        # 3. YouTube Gaming / YouTube Live Card (13.1)
        # ------------------------------------------------------------------
        grp_yt = QGroupBox("🔴 YouTube Gaming / YouTube Live (Google OAuth2 && Health Watchdog)")
        lay_yt = QVBoxLayout(grp_yt)
        lay_yt.setSpacing(8)

        yt_top = QHBoxLayout()
        self.chk_yt_enabled = QCheckBox("Include YouTube Live in Dispatcher")
        self.chk_yt_enabled.setChecked(self.gateway.youtube_enabled)
        self.chk_yt_enabled.toggled.connect(self._on_config_changed)
        yt_top.addWidget(self.chk_yt_enabled, 1)

        self.lbl_yt_account = QLabel("Not linked")
        self.lbl_yt_account.setStyleSheet("font-size: 11px; font-weight: bold;")
        yt_top.addWidget(self.lbl_yt_account)
        lay_yt.addLayout(yt_top)

        yt_form = QFormLayout()
        yt_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        yt_form.setSpacing(6)
        self.txt_yt_client_id = QLineEdit(self.gateway.yt_client_id)
        self.txt_yt_client_id.setMinimumWidth(0)
        self.txt_yt_client_id.setPlaceholderText("Google OAuth2 Desktop Client ID")
        self.txt_yt_client_id.editingFinished.connect(self._on_config_changed)
        yt_form.addRow("Google Client ID:", self.txt_yt_client_id)

        self.txt_yt_client_secret = QLineEdit(self.gateway.yt_client_secret)
        self.txt_yt_client_secret.setMinimumWidth(0)
        self.txt_yt_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_yt_client_secret.setPlaceholderText("Optional Client Secret")
        self.txt_yt_client_secret.editingFinished.connect(self._on_config_changed)
        yt_form.addRow("Client Secret:", self.txt_yt_client_secret)
        lay_yt.addLayout(yt_form)

        yt_btns_1 = QHBoxLayout()
        self.btn_yt_login = QPushButton("🔑 Sign In with Google")
        self.btn_yt_login.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        self.btn_yt_login.clicked.connect(self._start_youtube_oauth)
        yt_btns_1.addWidget(self.btn_yt_login)

        self.btn_yt_unlink = QPushButton("Disconnect")
        self.btn_yt_unlink.clicked.connect(self._unlink_youtube)
        yt_btns_1.addWidget(self.btn_yt_unlink)

        self.btn_yt_health = QPushButton("🔄 Check Health")
        self.btn_yt_health.clicked.connect(self._check_yt_health_clicked)
        yt_btns_1.addWidget(self.btn_yt_health)

        btn_yt_markers = QPushButton("📄 VOD Markers")
        btn_yt_markers.setToolTip("Open local YouTube VOD timestamp chapter markers log.")
        btn_yt_markers.clicked.connect(self._open_yt_markers_file)
        yt_btns_1.addWidget(btn_yt_markers)
        yt_btns_1.addStretch()
        lay_yt.addLayout(yt_btns_1)

        yt_opts = QHBoxLayout()
        self.chk_yt_watchdog = QCheckBox("20s Health Watchdog")
        self.chk_yt_watchdog.setChecked(self.gateway.yt_watchdog_enabled)
        self.chk_yt_watchdog.toggled.connect(self._on_config_changed)
        yt_opts.addWidget(self.chk_yt_watchdog)

        self.chk_yt_chat_marker = QCheckBox("Post Markers to Live Chat")
        self.chk_yt_chat_marker.setChecked(self.gateway.yt_post_marker_to_chat)
        self.chk_yt_chat_marker.toggled.connect(self._on_config_changed)
        yt_opts.addWidget(self.chk_yt_chat_marker)
        yt_opts.addStretch()
        lay_yt.addLayout(yt_opts)

        self.lbl_yt_health = QLabel("Health: Idle")
        self.lbl_yt_health.setWordWrap(True)
        self.lbl_yt_health.setStyleSheet("font-size: 11px;")
        lay_yt.addWidget(self.lbl_yt_health)

        layout.addWidget(grp_yt)

        # ------------------------------------------------------------------
        # 4. Kick Streaming Target Card (13.2)
        # ------------------------------------------------------------------
        grp_kick = QGroupBox("🟢 Kick Streaming Target (Metadata Sync, OAuth2 && Webhook Bridge)")
        lay_kick = QVBoxLayout(grp_kick)
        lay_kick.setSpacing(8)

        k_top = QHBoxLayout()
        self.chk_kick_enabled = QCheckBox("Include Kick in Dispatcher")
        self.chk_kick_enabled.setChecked(self.gateway.kick_enabled)
        self.chk_kick_enabled.toggled.connect(self._on_config_changed)
        k_top.addWidget(self.chk_kick_enabled, 1)

        self.lbl_kick_status = QLabel("Status: Not synced")
        self.lbl_kick_status.setStyleSheet("font-size: 11px; font-weight: bold;")
        k_top.addWidget(self.lbl_kick_status)
        lay_kick.addLayout(k_top)

        k_form = QFormLayout()
        k_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        k_form.setSpacing(6)

        slug_row = QHBoxLayout()
        self.txt_kick_slug = QLineEdit(self.gateway.kick_channel_slug)
        self.txt_kick_slug.setMinimumWidth(0)
        self.txt_kick_slug.setPlaceholderText("e.g. xqc (no Kick account needed)")
        self.txt_kick_slug.editingFinished.connect(self._on_config_changed)
        slug_row.addWidget(self.txt_kick_slug, 1)

        self.btn_kick_sync = QPushButton("🔍 Sync Public")
        self.btn_kick_sync.setToolTip("Fetch public Kick channel metadata without signing in.")
        self.btn_kick_sync.clicked.connect(self._sync_kick_public)
        slug_row.addWidget(self.btn_kick_sync)
        k_form.addRow("Channel Slug:", slug_row)

        self.txt_kick_webhook = QLineEdit(self.gateway.kick_webhook_url)
        self.txt_kick_webhook.setMinimumWidth(0)
        self.txt_kick_webhook.setPlaceholderText("Optional Webhook Bridge URL (Botrix / Kicklet / n8n)")
        self.txt_kick_webhook.editingFinished.connect(self._on_config_changed)
        k_form.addRow("Webhook URL:", self.txt_kick_webhook)

        self.txt_kick_client_id = QLineEdit(self.gateway.kick_client_id)
        self.txt_kick_client_id.setMinimumWidth(0)
        self.txt_kick_client_id.setPlaceholderText("Optional Kick OAuth2 Client ID")
        self.txt_kick_client_id.editingFinished.connect(self._on_config_changed)
        k_form.addRow("Kick Client ID:", self.txt_kick_client_id)

        self.txt_kick_token = QLineEdit(self.gateway.kick_access_token)
        self.txt_kick_token.setMinimumWidth(0)
        self.txt_kick_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_kick_token.setPlaceholderText("Kick Bearer Token (auto-filled or paste)")
        self.txt_kick_token.editingFinished.connect(self._on_config_changed)
        k_form.addRow("Access Token:", self.txt_kick_token)
        lay_kick.addLayout(k_form)

        k_btns = QHBoxLayout()
        self.btn_kick_login = QPushButton("🔑 Link Kick OAuth")
        self.btn_kick_login.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        self.btn_kick_login.clicked.connect(self._start_kick_oauth)
        k_btns.addWidget(self.btn_kick_login)

        self.btn_kick_unlink = QPushButton("Clear Token")
        self.btn_kick_unlink.clicked.connect(self._unlink_kick)
        k_btns.addWidget(self.btn_kick_unlink)
        k_btns.addStretch()
        lay_kick.addLayout(k_btns)

        layout.addWidget(grp_kick)

        # ------------------------------------------------------------------
        # 5. Multi-Stream Unified Event Dispatcher Card (13.3)
        # ------------------------------------------------------------------
        grp_disp = QGroupBox("🚀 Multi-Stream Unified Event Dispatcher")
        lay_disp = QVBoxLayout(grp_disp)
        lay_disp.setSpacing(8)

        meta_form = QFormLayout()
        meta_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        meta_form.setSpacing(6)
        self.txt_meta_title = QLineEdit()
        self.txt_meta_title.setMinimumWidth(0)
        self.txt_meta_title.setPlaceholderText("Stream Title to push to all active destinations...")
        meta_form.addRow("Broadcast Title:", self.txt_meta_title)

        self.txt_meta_category = QLineEdit()
        self.txt_meta_category.setMinimumWidth(0)
        self.txt_meta_category.setPlaceholderText("Game / Category (e.g. Just Chatting, Minecraft)")
        meta_form.addRow("Game / Category:", self.txt_meta_category)
        lay_disp.addLayout(meta_form)

        self.btn_sync_meta = QPushButton("🚀 Sync Title && Category to All Active Platforms")
        self.btn_sync_meta.setStyleSheet("background-color: #6d28d9; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_sync_meta.clicked.connect(self._on_sync_metadata)
        lay_disp.addWidget(self.btn_sync_meta)

        marker_row = QHBoxLayout()
        self.txt_test_marker = QLineEdit()
        self.txt_test_marker.setMinimumWidth(0)
        self.txt_test_marker.setPlaceholderText("Marker description (e.g. Epic Clutch!)")
        marker_row.addWidget(self.txt_test_marker, 1)

        self.btn_drop_marker = QPushButton("📍 Drop Unified Marker")
        self.btn_drop_marker.clicked.connect(self._on_drop_marker)
        marker_row.addWidget(self.btn_drop_marker)
        lay_disp.addLayout(marker_row)

        ann_row = QHBoxLayout()
        self.txt_test_announce = QLineEdit()
        self.txt_test_announce.setMinimumWidth(0)
        self.txt_test_announce.setPlaceholderText("Chat announcement message...")
        ann_row.addWidget(self.txt_test_announce, 1)

        self.btn_send_announce = QPushButton("📣 Announce to All")
        self.btn_send_announce.clicked.connect(self._on_send_announce)
        ann_row.addWidget(self.btn_send_announce)
        lay_disp.addLayout(ann_row)

        self.txt_dispatch_log = QTextEdit()
        self.txt_dispatch_log.setReadOnly(True)
        self.txt_dispatch_log.setFixedHeight(140)
        self.txt_dispatch_log.setPlaceholderText("Unified dispatcher activity will appear here...")
        lay_disp.addWidget(self.txt_dispatch_log)

        layout.addWidget(grp_disp)
        layout.addStretch()

        # Connect gateway signals
        self.gateway.dispatch_logged.connect(self._on_dispatch_logged)
        self.gateway.youtube_health_updated.connect(self._on_yt_health_updated)
        self.gateway.kick_status_updated.connect(self._on_kick_status_updated)

        self.refresh_status()

    # ------------------------------------------------------------------
    # State Sync
    # ------------------------------------------------------------------
    def _on_config_changed(self):
        self.gateway.twitch_enabled = self.chk_tw_enabled.isChecked()
        self.gateway.youtube_enabled = self.chk_yt_enabled.isChecked()
        self.gateway.kick_enabled = self.chk_kick_enabled.isChecked()
        self.gateway.dry_run_mode = self.chk_dry_run.isChecked()

        self.gateway.yt_client_id = self.txt_yt_client_id.text().strip()
        self.gateway.yt_client_secret = self.txt_yt_client_secret.text().strip()
        self.gateway.yt_watchdog_enabled = self.chk_yt_watchdog.isChecked()
        self.gateway.yt_post_marker_to_chat = self.chk_yt_chat_marker.isChecked()

        self.gateway.kick_channel_slug = self.txt_kick_slug.text().strip()
        self.gateway.kick_webhook_url = self.txt_kick_webhook.text().strip()
        self.gateway.kick_client_id = self.txt_kick_client_id.text().strip()
        self.gateway.kick_access_token = self.txt_kick_token.text().strip()

        self.gateway.start_watchdog_if_ready()
        self.gateway.gateway_status_changed.emit()
        self.refresh_status()
        if self.overlay and hasattr(self.overlay, "save_settings"):
            self.overlay.save_settings()

    def refresh_status(self):
        dests = self.gateway.get_active_destinations()
        dest_names = [d.capitalize() for d in dests] if dests else ["None"]
        mode_tag = " [DRY-RUN]" if self.gateway.dry_run_mode else ""
        self.lbl_active_dests.setText(f"Active: {', '.join(dest_names)}{mode_tag}")

        # Twitch status
        if self.overlay and getattr(self.overlay, "twitch_token", ""):
            ch = getattr(self.overlay, "twitch_display_name", "") or getattr(self.overlay, "twitch_channel", "")
            self.lbl_tw_status.setText(f"✅ Linked as <b>{ch}</b>")
        else:
            self.lbl_tw_status.setText("⚠️ Not linked in Twitch tab")

        # YouTube status
        if self.gateway.yt_access_token:
            yt_name = self.gateway.yt_channel_title or self.gateway.yt_channel_id or "YouTube Connected"
            self.lbl_yt_account.setText(f"✅ {yt_name}")
            self.lbl_yt_account.setStyleSheet("font-size: 11px; font-weight: bold; color: #34d399;")
        else:
            self.lbl_yt_account.setText("Not linked")
            self.lbl_yt_account.setStyleSheet("font-size: 11px; font-weight: bold; color: #9ca3af;")

    # ------------------------------------------------------------------
    # OAuth & Platform Actions
    # ------------------------------------------------------------------
    def _start_youtube_oauth(self):
        cid = self.txt_yt_client_id.text().strip()
        csec = self.txt_yt_client_secret.text().strip()
        if not cid:
            QMessageBox.warning(self, "Google Client ID Needed", "Enter your Google Cloud OAuth2 Desktop Client ID first.")
            return
        self.btn_yt_login.setEnabled(False)
        self.btn_yt_login.setText("Authorizing...")
        self._yt_oauth_worker = YouTubeOAuthWorker(cid, csec)
        self._yt_oauth_worker.auth_success.connect(self._on_yt_auth_success)
        self._yt_oauth_worker.auth_error.connect(self._on_yt_auth_error)
        self._yt_oauth_worker.start()

    def _on_yt_auth_success(self, data: dict):
        self.btn_yt_login.setEnabled(True)
        self.btn_yt_login.setText("🔑 Sign In with Google")
        self.gateway.yt_access_token = data.get("access_token", "")
        self.gateway.yt_refresh_token = data.get("refresh_token", "") or self.gateway.yt_refresh_token
        self.gateway.yt_token_expires_at = float(data.get("expires_at", 0.0))
        self.gateway.yt_channel_id = data.get("channel_id", "")
        self.gateway.yt_channel_title = data.get("channel_title", "")
        self._on_config_changed()
        self.gateway.poll_youtube_health_async()

    def _on_yt_auth_error(self, err: str):
        self.btn_yt_login.setEnabled(True)
        self.btn_yt_login.setText("🔑 Sign In with Google")
        QMessageBox.warning(self, "YouTube Auth Error", err)

    def _unlink_youtube(self):
        self.gateway.yt_access_token = ""
        self.gateway.yt_refresh_token = ""
        self.gateway.yt_channel_id = ""
        self.gateway.yt_channel_title = ""
        self.gateway.yt_active_broadcast = {}
        self.lbl_yt_health.setText("Health: Idle")
        self._on_config_changed()

    def _check_yt_health_clicked(self):
        if self.gateway.dry_run_mode and not self.gateway.yt_access_token:
            info = self.gateway.check_youtube_health_sync()
            self._on_yt_health_updated(info)
            return
        self.lbl_yt_health.setText("Health: Checking...")
        self.gateway.poll_youtube_health_async()

    def _on_yt_health_updated(self, info: dict):
        if info.get("is_live"):
            hs = info.get("healthStatus", "good")
            title = info.get("title", "")
            self.lbl_yt_health.setText(f"🔴 LIVE ({hs}) — {title}")
            self.lbl_yt_health.setStyleSheet("font-size: 11px; color: #34d399; font-weight: bold;")
        elif info.get("error"):
            self.lbl_yt_health.setText(f"⚠️ {info['error']}")
            self.lbl_yt_health.setStyleSheet("font-size: 11px; color: #f87171;")
        else:
            self.lbl_yt_health.setText("⚪ No active YouTube live broadcast")
            self.lbl_yt_health.setStyleSheet("font-size: 11px; color: #9ca3af;")

    def _open_yt_markers_file(self):
        os.makedirs(os.path.dirname(YOUTUBE_MARKERS_FILE), exist_ok=True)
        if not os.path.exists(YOUTUBE_MARKERS_FILE):
            with open(YOUTUBE_MARKERS_FILE, "w", encoding="utf-8") as f:
                f.write("[]\n")
        QDesktopServices.openUrl(QUrl.fromLocalFile(YOUTUBE_MARKERS_FILE))

    def _start_kick_oauth(self):
        cid = self.txt_kick_client_id.text().strip()
        if not cid:
            QMessageBox.warning(
                self,
                "Kick Client ID Needed",
                "Enter a Kick Developer Client ID, or use Public Metadata Sync / Webhook Bridge / Dry-Run Mode.",
            )
            return
        self.btn_kick_login.setEnabled(False)
        self.btn_kick_login.setText("Authorizing...")
        self._kick_oauth_worker = KickOAuthWorker(cid)
        self._kick_oauth_worker.auth_success.connect(self._on_kick_auth_success)
        self._kick_oauth_worker.auth_error.connect(self._on_kick_auth_error)
        self._kick_oauth_worker.start()

    def _on_kick_auth_success(self, data: dict):
        self.btn_kick_login.setEnabled(True)
        self.btn_kick_login.setText("🔑 Link Kick OAuth")
        self.txt_kick_token.setText(data.get("access_token", ""))
        self.gateway.kick_refresh_token = data.get("refresh_token", "")
        self._on_config_changed()

    def _on_kick_auth_error(self, err: str):
        self.btn_kick_login.setEnabled(True)
        self.btn_kick_login.setText("🔑 Link Kick OAuth")
        QMessageBox.warning(self, "Kick Auth Error", err)

    def _unlink_kick(self):
        self.txt_kick_token.clear()
        self.gateway.kick_access_token = ""
        self.gateway.kick_refresh_token = ""
        self._on_config_changed()

    def _sync_kick_public(self):
        slug = self.txt_kick_slug.text().strip()
        if not slug:
            QMessageBox.information(self, "Kick Slug", "Enter a Kick channel slug (e.g. xqc) to fetch public metadata.")
            return
        self.lbl_kick_status.setText("Syncing...")
        self.gateway.sync_kick_public_async(slug)

    def _on_kick_status_updated(self, info: dict):
        if not info.get("ok"):
            self.lbl_kick_status.setText(f"⚠️ {info.get('error', 'Sync failed')}")
            self.lbl_kick_status.setStyleSheet("font-size: 11px; color: #f87171;")
            return
        if info.get("is_live"):
            self.lbl_kick_status.setText(
                f"🟢 LIVE: {info.get('title', '')} [{info.get('category', '')}] • {info.get('viewers', 0)} viewers"
            )
            self.lbl_kick_status.setStyleSheet("font-size: 11px; font-weight: bold; color: #4ade80;")
        else:
            self.lbl_kick_status.setText(f"⚪ {info.get('slug')} (Offline • {info.get('followers', 0)} followers)")
            self.lbl_kick_status.setStyleSheet("font-size: 11px; color: #9ca3af;")

        # Pre-fill metadata inputs if empty
        if info.get("title") and not self.txt_meta_title.text().strip():
            self.txt_meta_title.setText(info["title"])
        if info.get("category") and not self.txt_meta_category.text().strip():
            self.txt_meta_category.setText(info["category"])

    # ------------------------------------------------------------------
    # Unified Dispatcher Actions
    # ------------------------------------------------------------------
    def _on_sync_metadata(self):
        title = self.txt_meta_title.text().strip()
        cat = self.txt_meta_category.text().strip()
        if not title and not cat:
            QMessageBox.information(self, "Metadata", "Enter a Broadcast Title and/or Game/Category first.")
            return
        self.gateway.dispatch_metadata_update(title, cat)

    def _on_drop_marker(self):
        desc = self.txt_test_marker.text().strip() or "Manual Highlight"
        self.gateway.dispatch_marker(desc)

    def _on_send_announce(self):
        msg = self.txt_test_announce.text().strip()
        if not msg:
            return
        self.gateway.dispatch_announcement(msg)

    def _on_dispatch_logged(self, entry: dict):
        ts = entry.get("timestamp", "")
        summary = entry.get("summary", "")
        results = entry.get("results", {})
        parts = []
        for plat, res in results.items():
            icon = "✅" if res.get("ok") else "❌"
            parts.append(f"{icon} {plat.upper()}: {res.get('message', '')}")
        line = f"[{ts}] {summary}\n   " + " | ".join(parts)
        self.txt_dispatch_log.append(line)
