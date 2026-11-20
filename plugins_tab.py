"""
Phase 14.2 & 14.6 UI: 1-Click Plugin Manager, Permission Review Modal & Developer Kit Exporter
"""
from __future__ import annotations

import os
from typing import Any, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from plugin_engine import (
    PERMISSION_DESCRIPTIONS,
    PluginManager,
    create_plugin_template,
    export_folder_as_calyxplugin,
    inspect_calyxplugin_archive,
)


class PluginPermissionDialog(QDialog):
    """14.2 Permission & Safety Review Modal before mounting a .calyxplugin package."""

    def __init__(self, manifest: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plugin Permission & Safety Review")
        self.setMinimumWidth(440)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        icon = manifest.get("icon", "🧩")
        name = manifest.get("name", manifest.get("id", "Plugin"))
        ver = manifest.get("version", "1.0.0")
        author = manifest.get("author", "Unknown")
        cat = manifest.get("category", "PLUGINS")
        has_sha = manifest.get("_has_checksum", False)

        lbl_hdr = QLabel(f"<h3>{icon} {name} <span style='font-size:12px; opacity:0.8;'>v{ver}</span></h3>")
        lay.addWidget(lbl_hdr)

        lbl_meta = QLabel(f"<b>Author:</b> {author} &nbsp;•&nbsp; <b>Category:</b> {cat} &nbsp;•&nbsp; <b>ID:</b> <code>{manifest.get('id')}</code>")
        lbl_meta.setWordWrap(True)
        lay.addWidget(lbl_meta)

        sha_text = "✅ SHA-256 package integrity verified" if has_sha else "⚠️ Unchecksummed community package"
        lbl_sha = QLabel(sha_text)
        lbl_sha.setStyleSheet("color: #34d399; font-weight: bold;" if has_sha else "color: #fbbf24; font-weight: bold;")
        lay.addWidget(lbl_sha)

        if manifest.get("description"):
            lbl_desc = QLabel(manifest["description"])
            lbl_desc.setWordWrap(True)
            lay.addWidget(lbl_desc)

        grp = QGroupBox("Requested Permissions")
        p_lay = QVBoxLayout(grp)
        perms = manifest.get("permissions", [])
        if not perms:
            p_lay.addWidget(QLabel("• No special permissions requested."))
        else:
            for p in perms:
                desc = PERMISSION_DESCRIPTIONS.get(p, "Custom plugin capability")
                lbl_p = QLabel(f"• <b>{p}</b>: {desc}")
                lbl_p.setWordWrap(True)
                p_lay.addWidget(lbl_p)
        lay.addWidget(grp)

        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅ Approve && Install Plugin")
        btn_ok.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        lay.addLayout(btns)


class PluginsTab(QWidget):
    """Dedicated Plugins & Add-ons Manager Tab (Phase 14.2 & 14.6)."""

    def __init__(self, main_window, manager: PluginManager):
        super().__init__()
        self.main_win = main_window
        self.manager = manager
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroll)

        container = QWidget()
        container.setMinimumWidth(0)
        container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(container)
        lay.setContentsMargins(12, 12, 18, 12)
        lay.setSpacing(10)
        scroll.setWidget(container)

        # 1. Install / Drag & Drop Header
        drop_box = QFrame()
        drop_box.setStyleSheet(
            "QFrame { background: rgba(145, 70, 255, 0.10); border: 1px dashed rgba(145, 70, 255, 0.55); border-radius: 8px; }"
        )
        d_lay = QVBoxLayout(drop_box)
        d_lay.setContentsMargins(12, 10, 12, 10)
        d_lay.setSpacing(6)

        top_row = QHBoxLayout()
        lbl_h = QLabel("🧩 <b>Plugins & Add-ons Manager</b>")
        lbl_h.setStyleSheet("font-size: 13px; border: none; background: transparent;")
        top_row.addWidget(lbl_h, 1)

        self.btn_install = QPushButton("📦 Install .calyxplugin...")
        self.btn_install.setStyleSheet("background-color: #6d28d9; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
        self.btn_install.clicked.connect(self._on_install_clicked)
        top_row.addWidget(self.btn_install)
        d_lay.addLayout(top_row)

        lbl_drop = QLabel("Drag & drop a <code>.calyxplugin</code> package anywhere onto this window, or click <b>Install .calyxplugin...</b>")
        lbl_drop.setWordWrap(True)
        lbl_drop.setStyleSheet("font-size: 11px; opacity: 0.85; border: none; background: transparent;")
        d_lay.addWidget(lbl_drop)
        lay.addWidget(drop_box)

        # 2. Installed & First-Party Plugins List
        self.grp_list = QGroupBox("Installed & First-Party Core Plugins")
        self.list_lay = QVBoxLayout(self.grp_list)
        self.list_lay.setSpacing(8)
        lay.addWidget(self.grp_list)

        # 3. Developer Kit & 1-Click Exporter (14.6)
        grp_dev = QGroupBox("🛠️ Developer Kit && 1-Click Exporter")
        dev_lay = QVBoxLayout(grp_dev)
        dev_lay.setSpacing(6)

        lbl_dev = QLabel("Build custom Streamer Calyx add-ons with a starter template and package them into checksummed <code>.calyxplugin</code> bundles.")
        lbl_dev.setWordWrap(True)
        lbl_dev.setStyleSheet("font-size: 11px;")
        dev_lay.addWidget(lbl_dev)

        dev_btns = QHBoxLayout()
        btn_tmpl = QPushButton("📄 Create Starter Template...")
        btn_tmpl.clicked.connect(self._on_create_template)
        btn_export = QPushButton("📦 Export Folder as .calyxplugin...")
        btn_export.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
        btn_export.clicked.connect(self._on_export_plugin)
        dev_btns.addWidget(btn_tmpl)
        dev_btns.addWidget(btn_export)
        dev_btns.addStretch()
        dev_lay.addLayout(dev_btns)
        lay.addWidget(grp_dev)

        lay.addStretch()

        self.manager.plugins_changed.connect(self.refresh_list)
        self.refresh_list()

    # ------------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".calyxplugin"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".calyxplugin"):
                self.install_archive_with_review(path)
                break

    def install_archive_with_review(self, archive_path: str):
        ok, manifest, msg = inspect_calyxplugin_archive(archive_path)
        if not ok:
            QMessageBox.warning(self, "Invalid Plugin Package", msg)
            return
        dlg = PluginPermissionDialog(manifest, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            inst_ok, inst_msg = self.manager.install_calyxplugin(archive_path)
            if inst_ok:
                QMessageBox.information(self, "Plugin Installed", inst_msg)
            else:
                QMessageBox.warning(self, "Plugin Install Notice", inst_msg)

    def _on_install_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Calyx Plugin Package",
            "",
            "Calyx Plugins (*.calyxplugin);;All Files (*)",
        )
        if path:
            self.install_archive_with_review(path)

    # ------------------------------------------------------------------
    # List Rendering
    # ------------------------------------------------------------------
    def refresh_list(self):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for p in self.manager.list_plugins():
            card = QFrame()
            card.setStyleSheet("QFrame { border: 1px solid rgba(255,255,255,0.14); border-radius: 6px; padding: 6px; }")
            c_lay = QVBoxLayout(card)
            c_lay.setContentsMargins(8, 6, 8, 6)
            c_lay.setSpacing(4)

            top = QHBoxLayout()
            chk = QCheckBox(f"{p['icon']} {p['name']}  v{p['version']}")
            chk.setChecked(p["enabled"])
            chk.setStyleSheet("font-weight: bold;")
            chk.toggled.connect(lambda val, pid=p["id"]: self.manager.set_plugin_enabled(pid, val))
            top.addWidget(chk, 1)

            badge = QLabel("CORE" if p["builtin"] else "3RD PARTY")
            badge.setStyleSheet(
                "font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 4px; "
                "background: rgba(56, 189, 248, 0.18); color: #38bdf8;"
            )
            top.addWidget(badge)

            btn_open = QPushButton("Open")
            btn_open.setEnabled(p["enabled"] and p["loaded"])
            btn_open.clicked.connect(lambda _=False, pid=p["id"]: self._open_plugin_page(pid))
            top.addWidget(btn_open)

            if not p["builtin"]:
                btn_rm = QPushButton("Uninstall")
                btn_rm.clicked.connect(lambda _=False, pid=p["id"]: self.manager.uninstall_plugin(pid))
                top.addWidget(btn_rm)

            c_lay.addLayout(top)

            desc = QLabel(f"{p['description']}  <i>(by {p['author']} • {p['category']})</i>")
            desc.setWordWrap(True)
            desc.setStyleSheet("font-size: 11px; opacity: 0.85; border: none;")
            c_lay.addWidget(desc)

            if p.get("error"):
                err_lbl = QLabel(f"⚠️ Isolated Error: {p['error'].splitlines()[0]}")
                err_lbl.setWordWrap(True)
                err_lbl.setStyleSheet("font-size: 10px; color: #f87171; border: none;")
                c_lay.addWidget(err_lbl)

            self.list_lay.addWidget(card)

    def _open_plugin_page(self, plugin_id: str):
        if hasattr(self.main_win, "focus_plugin_page"):
            self.main_win.focus_plugin_page(plugin_id)

    # ------------------------------------------------------------------
    # 14.6 Developer Kit Actions
    # ------------------------------------------------------------------
    def _on_create_template(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Folder for Starter Plugin")
        if not folder:
            return
        pid, ok = QInputDialog.getText(self, "Plugin ID", "Unique Plugin ID (e.g. dev.my_plugin):", text="dev.my_plugin")
        if not ok or not pid.strip():
            return
        name, ok2 = QInputDialog.getText(self, "Plugin Name", "Display Name:", text="My Custom Plugin")
        if not ok2 or not name.strip():
            return
        target = os.path.join(folder, pid.strip().replace(".", "_"))
        res_ok, msg = create_plugin_template(target, pid.strip(), name.strip(), "Creator")
        if res_ok:
            QMessageBox.information(self, "Template Created", f"Starter plugin created at:\n{msg}")
        else:
            QMessageBox.warning(self, "Template Error", msg)

    def _on_export_plugin(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Plugin Folder (containing plugin.json & main.py)")
        if not folder:
            return
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save .calyxplugin Bundle",
            os.path.join(os.path.dirname(folder), f"{os.path.basename(folder)}.calyxplugin"),
            "Calyx Plugin (*.calyxplugin)",
        )
        if not out_path:
            return
        ok, res = export_folder_as_calyxplugin(folder, out_path)
        if ok:
            QMessageBox.information(self, "Export Complete", f"Packaged checksummed plugin:\n{res}")
        else:
            QMessageBox.warning(self, "Export Failed", res)
