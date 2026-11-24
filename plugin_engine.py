"""
Phase 14: Calyx Modular Plugin Architecture & Add-on Engine
Provides:
  - 14.1 .calyxplugin Standard Package Format (ZIP + plugin.json + main.py + SHA-256 manifest)
  - 14.4 Crash-Isolated CalyxAPI Runtime Engine & CalyxPluginBase
  - 14.6 Developer Kit & 1-Click .calyxplugin Exporter + Starter Template Generator
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import traceback
import zipfile
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

from debug_logger import log_debug

PLUGINS_ROOT_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "StreamerCalyx",
    "plugins",
)
PLUGIN_STATE_FILE = os.path.join(PLUGINS_ROOT_DIR, "plugin_state.json")

VALID_CATEGORIES = ("STREAM TOOLS", "OVERLAY & DISPLAY", "PLUGINS")

PERMISSION_DESCRIPTIONS: Dict[str, str] = {
    "overlay_toast": "Display in-game HUD toast notifications and monitor alerts",
    "config_storage": "Read and write plugin-scoped settings in %APPDATA%\\StreamerCalyx\\plugins",
    "hotkeys": "Listen to global hotkeys and peripheral button events",
    "broadcast_events": "Subscribe to stream markers, scene switches, and live broadcast events",
    "slobs_control": "Read or adjust Streamlabs / OBS scenes and audio channels",
    "audio_ducking": "Temporarily attenuate audio mixer channels via hotkey",
    "peer_chat": "Send and receive encrypted backstage messages with connected directors",
    "network": "Connect to external web alert bridges or webhooks",
    "chat_read": "Listen to incoming viewer chat messages and !commands",
    "chat_send": "Send chat replies or results back to live stream chat",
    "channel_points": "Listen to Twitch Channel Points custom reward redemptions",
    "bits": "Listen to Twitch Bits / Cheer events",
    "service_provider": "Register shared data & action services for Calyx and authorized plugins",
    "loyalty_read": "Read viewer loyalty points, ranks, and leaderboards from connected services",
    "loyalty_write": "Add, deduct, or modify viewer loyalty points on connected services",
    "alerts_read": "Read recent tips, donations, store redemptions, and alert events",
    "bot_say": "Send messages through connected StreamElements / Streamlabs bots",
}

CORE_PLUGIN_BASE_URL = "https://raw.githubusercontent.com/thawizanator/streamer-calyx/main/plugins"

CORE_PLUGIN_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "calyx.ending_credits",
        "name": "Ending Credits",
        "version": "1.0.0",
        "author": "Streamer Calyx",
        "date": "2026-11-24",
        "signed": True,
        "description": "Customizable movie-style rolling credits scroller & OBS Browser Source HTML exporter.",
        "category": "OVERLAY & DISPLAY",
        "icon": "🎬",
        "permissions": ["overlay_toast", "config_storage"],
        "download_url": f"{CORE_PLUGIN_BASE_URL}/calyx.ending_credits.calyxplugin",
    },
    {
        "id": "calyx.teleprompter",
        "name": "Backstage Teleprompter",
        "version": "1.1.0",
        "author": "Streamer Calyx",
        "date": "2026-11-24",
        "signed": True,
        "description": "Live teleprompter with smooth scrolling, custom fonts/colors, mirror mode for glass, fullscreen window, and HTML export.",
        "category": "STREAM TOOLS",
        "icon": "📜",
        "permissions": ["overlay_toast", "config_storage"],
        "download_url": f"{CORE_PLUGIN_BASE_URL}/calyx.teleprompter.calyxplugin",
    },
    {
        "id": "calyx.backstage_chat",
        "name": "Encrypted Peer Chat",
        "version": "1.0.0",
        "author": "Streamer Calyx",
        "date": "2026-11-24",
        "signed": True,
        "description": "End-to-end encrypted backstage text chat between streamer and remote directors.",
        "category": "PLUGINS",
        "icon": "🔐",
        "permissions": ["config_storage", "peer_chat", "broadcast_events"],
        "download_url": f"{CORE_PLUGIN_BASE_URL}/calyx.backstage_chat.calyxplugin",
    },
    {
        "id": "calyx.streamelements",
        "name": "StreamElements",
        "version": "1.0.1",
        "author": "Streamer Calyx",
        "date": "2026-11-24",
        "signed": True,
        "description": "Connects StreamElements Loyalty Points, real-time alerts, activity feed, and bot chat with permission-controlled plugin access.",
        "category": "STREAM TOOLS",
        "icon": "⚡",
        "permissions": ["overlay_toast", "config_storage", "network", "broadcast_events", "service_provider"],
        "download_url": f"{CORE_PLUGIN_BASE_URL}/calyx.streamelements.calyxplugin",
    },
    {
        "id": "calyx.streamlabs",
        "name": "Streamlabs",
        "version": "1.0.0",
        "author": "Streamer Calyx",
        "date": "2026-11-24",
        "signed": True,
        "description": "Connects Streamlabs Loyalty Points, Socket API real-time donations/merch alerts, and custom alerts with permission-controlled plugin access.",
        "category": "STREAM TOOLS",
        "icon": "🟢",
        "permissions": ["overlay_toast", "config_storage", "network", "broadcast_events", "service_provider"],
        "download_url": f"{CORE_PLUGIN_BASE_URL}/calyx.streamlabs.calyxplugin",
    },
]


class CalyxPluginBase:
    """Base class that all Calyx plugins inherit from in their main.py."""

    def __init__(self):
        self.api: Optional[CalyxAPI] = None

    def on_load(self, api: "CalyxAPI") -> None:
        self.api = api

    def on_unload(self) -> None:
        pass

    def create_widget(self, parent: Optional[QWidget] = None) -> Optional[QWidget]:
        return None


class CalyxAPI:
    """
    Crash-isolated runtime API passed to each loaded plugin.
    All callbacks and platform hooks are guarded with try/except boundaries.
    """

    def __init__(
        self,
        plugin_id: str,
        manifest: Dict[str, Any],
        overlay: Any,
        manager: "PluginManager",
        data_dir: str,
    ):
        self.plugin_id = plugin_id
        self.manifest = dict(manifest)
        self.permissions = set(manifest.get("permissions", []))
        self._overlay = overlay
        self._manager = manager
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self._config_path = os.path.join(self.data_dir, "config.json")
        self._event_subs: List[Tuple[str, Callable]] = []

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions

    def log(self, message: str) -> None:
        try:
            log_debug(f"PLUGIN:{self.plugin_id}", str(message))
        except Exception:
            pass

    def show_overlay_toast(self, message: str, is_success: bool = True) -> bool:
        if not self.has_permission("overlay_toast"):
            self.log("Permission denied: overlay_toast")
            return False
        try:
            if self._overlay and hasattr(self._overlay, "show_hud_toast"):
                self._overlay.show_hud_toast(str(message), bool(is_success))
                return True
        except Exception as e:
            self._manager._record_plugin_error(self.plugin_id, f"show_overlay_toast: {e}")
        return False

    def get_config(self, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.has_permission("config_storage"):
            return dict(default or {})
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    merged = dict(default or {})
                    merged.update(data)
                    return merged
        except Exception as e:
            self._manager._record_plugin_error(self.plugin_id, f"get_config: {e}")
        return dict(default or {})

    def save_config(self, data: Dict[str, Any]) -> bool:
        if not self.has_permission("config_storage"):
            return False
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            self._manager._record_plugin_error(self.plugin_id, f"save_config: {e}")
            return False

    def on_event(self, event_name: str, callback: Callable[[Any], None]) -> bool:
        perm_map = {
            "chat_message": ("chat_read", "broadcast_events"),
            "channel_points": ("channel_points", "broadcast_events"),
            "bits": ("bits", "broadcast_events"),
        }
        needed = perm_map.get(event_name, ("broadcast_events",))
        if not any(self.has_permission(p) for p in needed):
            self.log(f"Permission denied: {needed[0]} ({event_name})")
            return False
        self._manager.subscribe_event(self.plugin_id, event_name, callback)
        self._event_subs.append((event_name, callback))
        return True

    def on_command(self, command: str, callback: Callable[[Dict[str, Any]], None]) -> bool:
        """Subscribe to a standardized chat command (e.g. '!slots') across all active platforms."""
        if not (self.has_permission("chat_read") or self.has_permission("broadcast_events")):
            self.log(f"Permission denied: chat_read ({command})")
            return False
        cmd_norm = str(command or "").strip().lower()
        if not cmd_norm:
            return False
        if not cmd_norm.startswith("!"):
            cmd_norm = "!" + cmd_norm
        self._manager.subscribe_command(self.plugin_id, cmd_norm, callback)
        return True

    def send_chat_message(self, text: str, platform: str = "twitch") -> bool:
        """Send a reply back to stream chat (Twitch Helix / MultiPlatformGateway)."""
        if not self.has_permission("chat_send"):
            self.log("Permission denied: chat_send")
            return False
        msg = str(text or "").strip()
        if not msg or not self._overlay:
            return False
        try:
            plat = str(platform or "twitch").lower()
            if plat == "twitch" and hasattr(self._overlay, "dispatch_twitch_call"):
                self._overlay.dispatch_twitch_call("/chat", msg[:500])
                return True
            gw = getattr(self._overlay, "platform_gateway", None)
            if gw and hasattr(gw, "dispatch_announcement"):
                gw.dispatch_announcement(msg[:500])
                return True
        except Exception as e:
            self._manager._record_plugin_error(self.plugin_id, f"send_chat_message: {e}")
        return False

    def get_platform_capabilities(self) -> Dict[str, Any]:
        """Returns linked account capability flags (e.g. Twitch Affiliate/Partner Channel Points check)."""
        ov = self._overlay
        btype = str(getattr(ov, "twitch_broadcaster_type", "") or "").lower() if ov else ""
        tw_linked = bool(ov and getattr(ov, "twitch_token", "") and getattr(ov, "twitch_channel", ""))
        monetized = btype in ("affiliate", "partner")
        return {
            "twitch": {
                "linked": tw_linked,
                "broadcaster_type": btype or "standard",
                "chat": tw_linked,
                "channel_points": tw_linked and monetized,
                "bits": tw_linked and monetized,
            }
        }

    def register_hotkey(self, hotkey_str: str, callback: Callable[[], None]) -> bool:
        if not self.has_permission("hotkeys"):
            self.log(f"Permission denied: hotkeys ({hotkey_str})")
            return False
        return self._manager.register_plugin_hotkey(self.plugin_id, hotkey_str, callback)

    def get_slobs_client(self) -> Any:
        if not (self.has_permission("slobs_control") or self.has_permission("audio_ducking")):
            return None
        try:
            from streamlabs_client import get_streamlabs_client
            return get_streamlabs_client()
        except Exception:
            return None

    def get_overlay(self) -> Any:
        return self._overlay

    # ------------------------------------------------------------------
    # Cross-Plugin & Host Service Bus (Scoped Permissions)
    # ------------------------------------------------------------------
    def dispatch_event(self, event_name: str, payload: Any = None) -> bool:
        if not self.has_permission("broadcast_events"):
            self.log(f"Permission denied: broadcast_events ({event_name})")
            return False
        self._manager.dispatch_event(event_name, payload)
        return True

    def register_service(
        self,
        service_name: str,
        actions: Dict[str, Callable[..., Any]],
        scope_map: Optional[Dict[str, str]] = None,
        policy: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not self.has_permission("service_provider"):
            self.log(f"Permission denied: service_provider ({service_name})")
            return False
        return self._manager.register_service(
            self.plugin_id,
            service_name,
            actions,
            scope_map=scope_map,
            policy=policy,
        )

    def unregister_service(self, service_name: Optional[str] = None) -> None:
        self._manager.unregister_service(self.plugin_id, service_name)

    def set_service_policy(self, service_name: str, policy: Dict[str, Any]) -> bool:
        if not self.has_permission("service_provider"):
            return False
        return self._manager.set_service_policy(self.plugin_id, service_name, policy)

    def get_service_policy(self, service_name: str) -> Dict[str, Any]:
        return self._manager.get_service_policy(service_name)

    def call_service(self, service_name: str, action: str, **kwargs: Any) -> Dict[str, Any]:
        return self._manager.call_service(self.plugin_id, service_name, action, **kwargs)

    def list_services(self) -> List[Dict[str, Any]]:
        return self._manager.list_services()

    def list_installed_plugins(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "icon": p["icon"],
                "enabled": p["enabled"],
                "loaded": p["loaded"],
                "permissions": list(p.get("permissions", [])),
            }
            for p in self._manager.list_plugins()
            if p["id"] != self.plugin_id
        ]

    def get_viewer_points(self, username: str, provider: str = "auto") -> Dict[str, Any]:
        svc = "loyalty" if provider in ("", "auto", None) else str(provider)
        return self.call_service(svc, "get_points", username=username)

    def modify_viewer_points(
        self,
        username: str,
        delta: int,
        reason: str = "",
        provider: str = "auto",
    ) -> Dict[str, Any]:
        svc = "loyalty" if provider in ("", "auto", None) else str(provider)
        return self.call_service(svc, "add_points", username=username, amount=int(delta), reason=reason)


def validate_manifest(manifest: Any) -> Tuple[bool, str]:
    if not isinstance(manifest, dict):
        return False, "plugin.json must be a JSON object."
    for key in ("id", "name", "version", "author"):
        if not str(manifest.get(key, "")).strip():
            return False, f"Missing required manifest field: '{key}'."
    pid = str(manifest["id"]).strip()
    if any(c in pid for c in "/\\:*?\"<>| "):
        return False, "Manifest 'id' must not contain spaces or path characters."
    perms = manifest.get("permissions", [])
    if not isinstance(perms, list):
        return False, "Manifest 'permissions' must be a list."
    return True, "OK"


def inspect_calyxplugin_archive(archive_path: str) -> Tuple[bool, Dict[str, Any], str]:
    """Reads and validates plugin.json + SHA-256 checksums inside a .calyxplugin ZIP."""
    if not os.path.exists(archive_path):
        return False, {}, "Plugin file not found."
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
            if "plugin.json" not in names:
                return False, {}, "Invalid .calyxplugin: missing plugin.json at archive root."
            if "main.py" not in names:
                return False, {}, "Invalid .calyxplugin: missing main.py at archive root."
            manifest = json.loads(zf.read("plugin.json").decode("utf-8"))
            ok, msg = validate_manifest(manifest)
            if not ok:
                return False, {}, msg

            checksum_ok = True
            if "MANIFEST.sha256" in names:
                expected = json.loads(zf.read("MANIFEST.sha256").decode("utf-8"))
                for rel, digest in expected.items():
                    if rel in names:
                        actual = hashlib.sha256(zf.read(rel)).hexdigest()
                        if actual != digest:
                            checksum_ok = False
                            break
            if not checksum_ok:
                return False, manifest, "Integrity check failed: MANIFEST.sha256 mismatch."
            manifest["_has_checksum"] = "MANIFEST.sha256" in names
            return True, manifest, "OK"
    except zipfile.BadZipFile:
        return False, {}, "File is not a valid .calyxplugin ZIP archive."
    except Exception as e:
        return False, {}, f"Failed to inspect plugin: {e}"


def export_folder_as_calyxplugin(folder_path: str, output_path: str) -> Tuple[bool, str]:
    """14.6 Developer Kit: Packages a plugin folder into a checksummed .calyxplugin bundle."""
    manifest_file = os.path.join(folder_path, "plugin.json")
    entry_file = os.path.join(folder_path, "main.py")
    if not os.path.exists(manifest_file):
        return False, "Folder does not contain plugin.json."
    if not os.path.exists(entry_file):
        return False, "Folder does not contain main.py."
    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        ok, msg = validate_manifest(manifest)
        if not ok:
            return False, msg

        if not output_path.lower().endswith(".calyxplugin"):
            output_path += ".calyxplugin"

        checksums: Dict[str, str] = {}
        files_to_pack: List[Tuple[str, str]] = []
        for root, dirs, files in os.walk(folder_path):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".venv")]
            for fn in files:
                if fn.endswith(".pyc") or fn == "MANIFEST.sha256":
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, folder_path).replace("\\", "/")
                with open(full, "rb") as rf:
                    checksums[rel] = hashlib.sha256(rf.read()).hexdigest()
                files_to_pack.append((full, rel))

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for full, rel in files_to_pack:
                zf.write(full, arcname=rel)
            zf.writestr("MANIFEST.sha256", json.dumps(checksums, indent=2))
        return True, output_path
    except Exception as e:
        return False, f"Export failed: {e}"


def create_plugin_template(target_dir: str, plugin_id: str, name: str, author: str) -> Tuple[bool, str]:
    """14.6 Developer Kit: Generates a ready-to-edit starter plugin folder."""
    try:
        os.makedirs(target_dir, exist_ok=True)
        manifest = {
            "id": plugin_id,
            "name": name,
            "version": "1.0.0",
            "author": author,
            "description": "Custom Streamer Calyx plugin built with the Calyx Developer Kit.",
            "category": "PLUGINS",
            "icon": "🧩",
            "permissions": ["overlay_toast", "config_storage", "broadcast_events"],
        }
        with open(os.path.join(target_dir, "plugin.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        main_py = f'''from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from plugin_engine import CalyxPluginBase


class StarterPlugin(CalyxPluginBase):
    def on_load(self, api):
        super().on_load(api)
        api.on_event("marker_created", self.on_marker)

    def on_marker(self, payload):
        if self.api:
            self.api.log(f"Observed marker: {{payload}}")

    def create_widget(self, parent=None):
        w = QWidget(parent)
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>{name}</b> — Loaded via CalyxAPI!"))
        btn = QPushButton("Test Overlay Toast")
        btn.clicked.connect(lambda: self.api.show_overlay_toast("Hello from {name}!", True) if self.api else None)
        lay.addWidget(btn)
        lay.addStretch()
        return w
'''
        with open(os.path.join(target_dir, "main.py"), "w", encoding="utf-8") as f:
            f.write(main_py)

        readme = (
            f"# {name}\n\n"
            "1. Edit `plugin.json` and `main.py`.\n"
            "2. Open Streamer Calyx -> Plugins & Add-ons -> Export Folder as `.calyxplugin`.\n"
        )
        with open(os.path.join(target_dir, "README.md"), "w", encoding="utf-8") as f:
            f.write(readme)
        return True, target_dir
    except Exception as e:
        return False, str(e)


class PluginManager(QObject):
    """
    Manages built-in first-party plugins and user-installed .calyxplugin packages,
    handles crash-isolated lifecycle, event routing, and dynamic UI injection.
    """
    plugins_changed = pyqtSignal()
    catalog_updated = pyqtSignal()
    plugin_error = pyqtSignal(str, str)  # (plugin_id, error_msg)
    services_changed = pyqtSignal()

    def __init__(self, overlay: Any = None, plugins_dir: str = PLUGINS_ROOT_DIR, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.plugins_dir = plugins_dir
        self.state_file = os.path.join(self.plugins_dir, "plugin_state.json")
        os.makedirs(self.plugins_dir, exist_ok=True)

        self._registry: Dict[str, Dict[str, Any]] = {}  # plugin_id -> {manifest, builtin, path, enabled, instance, api, widget}
        self._enabled_state: Dict[str, bool] = {}
        self._event_listeners: Dict[str, List[Tuple[str, Callable]]] = {}
        self._command_listeners: Dict[str, List[Tuple[str, Callable]]] = {}
        self._hotkey_hooks: Dict[str, List[Any]] = {}
        self._services: Dict[str, Dict[str, Any]] = {}
        self._errors: Dict[str, str] = {}
        self._settings_window: Any = None
        self._remote_catalog: List[Dict[str, Any]] = [dict(e) for e in CORE_PLUGIN_CATALOG]

        self._load_state()
        self._discover_builtin_plugins()
        self._discover_installed_plugins()

    def _load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._enabled_state = {str(k): bool(v) for k, v in data.items()}
        except Exception:
            self._enabled_state = {}

    def _save_state(self):
        try:
            os.makedirs(self.plugins_dir, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._enabled_state, f, indent=2)
        except Exception as e:
            log_debug("PLUGIN", f"Failed to save plugin state: {e}")

    def _discover_builtin_plugins(self):
        try:
            from builtin_plugins import get_builtin_plugin_specs
            for spec in get_builtin_plugin_specs():
                manifest = spec["manifest"]
                pid = manifest["id"]
                enabled = self._enabled_state.get(pid, True)
                self._registry[pid] = {
                    "manifest": manifest,
                    "builtin": True,
                    "factory": spec["factory"],
                    "path": "",
                    "enabled": enabled,
                    "instance": None,
                    "api": None,
                    "widget": None,
                }
        except Exception as e:
            log_debug("PLUGIN", f"Error loading built-in plugins: {e}")

    def _discover_installed_plugins(self):
        if not os.path.isdir(self.plugins_dir):
            return
        for entry in os.listdir(self.plugins_dir):
            p_dir = os.path.join(self.plugins_dir, entry)
            manifest_path = os.path.join(p_dir, "plugin.json")
            if not os.path.isdir(p_dir) or not os.path.exists(manifest_path):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                ok, _ = validate_manifest(manifest)
                if not ok:
                    continue
                pid = manifest["id"]
                enabled = self._enabled_state.get(pid, True)
                self._registry[pid] = {
                    "manifest": manifest,
                    "builtin": False,
                    "factory": None,
                    "path": p_dir,
                    "enabled": enabled,
                    "instance": None,
                    "api": None,
                    "widget": None,
                }
            except Exception as e:
                log_debug("PLUGIN", f"Failed discovering plugin in {p_dir}: {e}")

    def attach_settings_window(self, settings_window: Any):
        self._settings_window = settings_window
        self.load_all_enabled()

    def load_all_enabled(self):
        for pid, info in list(self._registry.items()):
            if info["enabled"] and info["instance"] is None:
                self.load_plugin(pid)

    def _record_plugin_error(self, plugin_id: str, msg: str):
        self._errors[plugin_id] = msg
        log_debug("PLUGIN_ERR", f"[{plugin_id}] {msg}")
        self.plugin_error.emit(plugin_id, msg)

    def load_plugin(self, plugin_id: str) -> bool:
        info = self._registry.get(plugin_id)
        if not info:
            return False
        if info["instance"] is not None:
            return True

        manifest = info["manifest"]
        data_dir = os.path.join(self.plugins_dir, plugin_id)
        api = CalyxAPI(plugin_id, manifest, self.overlay, self, data_dir)

        try:
            if info["builtin"] and info.get("factory"):
                instance = info["factory"]()
            else:
                p_dir = info["path"]
                entry_file = os.path.join(p_dir, manifest.get("entry", "main.py"))
                mod_name = f"calyx_ext_plugin_{plugin_id.replace('.', '_')}"
                if p_dir not in sys.path:
                    sys.path.insert(0, p_dir)
                spec = importlib.util.spec_from_file_location(mod_name, entry_file)
                if not spec or not spec.loader:
                    raise RuntimeError(f"Could not load module spec for {entry_file}")
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                plugin_cls = None
                for attr in vars(mod).values():
                    if isinstance(attr, type) and issubclass(attr, CalyxPluginBase) and attr is not CalyxPluginBase:
                        plugin_cls = attr
                        break
                if plugin_cls is None:
                    raise RuntimeError("No CalyxPluginBase subclass found in main.py")
                instance = plugin_cls()

            instance.on_load(api)
            widget = instance.create_widget(self._settings_window)

            info["instance"] = instance
            info["api"] = api
            info["widget"] = widget
            self._errors.pop(plugin_id, None)

            if self._settings_window and widget is not None and hasattr(self._settings_window, "register_plugin_page"):
                cat = manifest.get("category", "PLUGINS")
                icon = manifest.get("icon", "🧩")
                name = manifest.get("name", plugin_id)
                self._settings_window.register_plugin_page(
                    plugin_id=plugin_id,
                    title=f"{icon}  {name}",
                    nav_label=f"{icon}  {name}",
                    category_label=cat,
                    widget=widget,
                )
            return True
        except Exception as e:
            tb = traceback.format_exc()
            self._record_plugin_error(plugin_id, f"{e}\n{tb}")
            info["instance"] = None
            info["api"] = None
            info["widget"] = None
            return False

    def unload_plugin(self, plugin_id: str):
        info = self._registry.get(plugin_id)
        if not info:
            return
        # Remove event subscriptions, command handlers, services & hotkeys
        self.unregister_service(plugin_id)
        for ev, subs in list(self._event_listeners.items()):
            self._event_listeners[ev] = [(pid, cb) for pid, cb in subs if pid != plugin_id]
        for cmd, subs in list(self._command_listeners.items()):
            self._command_listeners[cmd] = [(pid, cb) for pid, cb in subs if pid != plugin_id]
        for hk in self._hotkey_hooks.pop(plugin_id, []):
            try:
                import keyboard
                keyboard.remove_hotkey(hk)
            except Exception:
                pass

        if self._settings_window and hasattr(self._settings_window, "unregister_plugin_page"):
            try:
                self._settings_window.unregister_plugin_page(plugin_id)
            except Exception:
                pass

        inst = info.get("instance")
        if inst is not None:
            try:
                inst.on_unload()
            except Exception as e:
                self._record_plugin_error(plugin_id, f"on_unload: {e}")

        info["instance"] = None
        info["api"] = None
        info["widget"] = None

    def set_plugin_enabled(self, plugin_id: str, enabled: bool):
        info = self._registry.get(plugin_id)
        if not info:
            return
        info["enabled"] = bool(enabled)
        self._enabled_state[plugin_id] = bool(enabled)
        self._save_state()
        if enabled:
            self.load_plugin(plugin_id)
        else:
            self.unload_plugin(plugin_id)
        self.plugins_changed.emit()

    def install_calyxplugin(self, archive_path: str) -> Tuple[bool, str]:
        ok, manifest, msg = inspect_calyxplugin_archive(archive_path)
        if not ok:
            return False, msg
        pid = manifest["id"]
        dest_dir = os.path.join(self.plugins_dir, pid)
        if pid in self._registry and not self._registry[pid]["builtin"]:
            self.unload_plugin(pid)
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir, ignore_errors=True)
        os.makedirs(dest_dir, exist_ok=True)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(dest_dir)

        self._enabled_state[pid] = True
        self._save_state()
        self._registry[pid] = {
            "manifest": manifest,
            "builtin": False,
            "factory": None,
            "path": dest_dir,
            "enabled": True,
            "instance": None,
            "api": None,
            "widget": None,
        }
        loaded = self.load_plugin(pid)
        self.plugins_changed.emit()
        if not loaded:
            return False, f"Installed, but failed to load: {self._errors.get(pid, 'Unknown error')}"
        return True, f"Installed '{manifest.get('name', pid)}' v{manifest.get('version', '1.0.0')}"

    def uninstall_plugin(self, plugin_id: str) -> Tuple[bool, str]:
        info = self._registry.get(plugin_id)
        if not info:
            return False, "Plugin not found."
        if info["builtin"]:
            return False, "Built-in core plugins can be toggled off, not uninstalled."
        self.unload_plugin(plugin_id)
        p_dir = info.get("path", "")
        if p_dir and os.path.isdir(p_dir):
            shutil.rmtree(p_dir, ignore_errors=True)
        self._registry.pop(plugin_id, None)
        self._enabled_state.pop(plugin_id, None)
        self._save_state()
        self.plugins_changed.emit()
        return True, f"Uninstalled '{plugin_id}'."

    def list_plugins(self) -> List[Dict[str, Any]]:
        core_ids = {c["id"] for c in self._remote_catalog}
        out = []
        for pid, info in self._registry.items():
            m = info["manifest"]
            out.append({
                "id": pid,
                "name": m.get("name", pid),
                "version": m.get("version", "1.0.0"),
                "author": m.get("author", "Unknown"),
                "description": m.get("description", ""),
                "category": m.get("category", "PLUGINS"),
                "icon": m.get("icon", "🧩"),
                "permissions": m.get("permissions", []),
                "builtin": info["builtin"],
                "is_core": bool(info["builtin"] or pid in core_ids),
                "enabled": info["enabled"],
                "loaded": info["instance"] is not None,
                "error": self._errors.get(pid, ""),
            })
        return out

    def refresh_core_catalog_async(self):
        """Fetches the latest plugins/catalog.json from GitHub in a background thread."""
        import threading
        import urllib.request

        def _fetch():
            urls = [
                "https://raw.githubusercontent.com/thawizanator/streamer-calyx/develop/plugins/catalog.json",
                "https://raw.githubusercontent.com/thawizanator/streamer-calyx/main/plugins/catalog.json",
            ]
            for url in urls:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "StreamerCalyx-Catalog/1.0"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and data:
                        self._remote_catalog = data
                        self.catalog_updated.emit()
                        return
                except Exception:
                    continue

        threading.Thread(target=_fetch, daemon=True).start()

    def list_core_catalog(self) -> List[Dict[str, Any]]:
        """Returns the official downloadable core plugins with current install status."""
        out = []
        for entry in self._remote_catalog:
            pid = entry["id"]
            installed_info = self._registry.get(pid)
            out.append({
                **entry,
                "installed": installed_info is not None,
                "enabled": bool(installed_info["enabled"]) if installed_info else False,
                "loaded": bool(installed_info and installed_info["instance"] is not None),
            })
        return out

    def download_core_plugin_archive(self, plugin_id: str, dest_path: str) -> Tuple[bool, str]:
        """Downloads a core .calyxplugin package from GitHub and verifies its SHA-256 manifest."""
        import urllib.error
        import urllib.request

        entry = next((e for e in self._remote_catalog if e["id"] == plugin_id), None)
        if not entry:
            return False, f"Unknown core plugin '{plugin_id}'."
        url = entry["download_url"]
        urls_to_try = [url]
        if "/main/plugins/" in url:
            urls_to_try.append(url.replace("/main/plugins/", "/develop/plugins/"))
        last_err = ""
        data = b""
        for candidate_url in urls_to_try:
            try:
                req = urllib.request.Request(candidate_url, headers={"User-Agent": "StreamerCalyx-PluginDownloader/1.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
                if data:
                    break
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code} fetching {candidate_url}"
            except Exception as e:
                last_err = f"Download failed: {e}"
        if not data:
            return False, last_err or "Downloaded archive is empty."
        try:
            os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(data)
            ok, _manifest, msg = inspect_calyxplugin_archive(dest_path)
            if not ok:
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
                return False, f"Downloaded archive failed verification: {msg}"
            return True, dest_path
        except Exception as e:
            return False, f"Download failed: {e}"

    def download_and_install_core_plugin(self, plugin_id: str) -> Tuple[bool, str]:
        """Synchronously downloads, verifies, and installs a core plugin."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_pkg = os.path.join(tmp, f"{plugin_id}.calyxplugin")
            ok, msg = self.download_core_plugin_archive(plugin_id, tmp_pkg)
            if not ok:
                return False, msg
            return self.install_calyxplugin(tmp_pkg)

    # ------------------------------------------------------------------
    # Crash-Isolated Event & Hotkey Dispatch
    # ------------------------------------------------------------------
    def subscribe_event(self, plugin_id: str, event_name: str, callback: Callable[[Any], None]):
        subs = self._event_listeners.setdefault(event_name, [])
        subs.append((plugin_id, callback))

    def subscribe_command(self, plugin_id: str, command: str, callback: Callable[[Dict[str, Any]], None]):
        subs = self._command_listeners.setdefault(command.lower().strip(), [])
        subs.append((plugin_id, callback))

    def dispatch_chat_message(self, payload: Dict[str, Any]):
        self.dispatch_event("chat_message", payload)
        cmd = str(payload.get("command", "") or "").lower().strip()
        if cmd:
            for pid, cb in list(self._command_listeners.get(cmd, [])):
                try:
                    cb(payload)
                except Exception as e:
                    self._record_plugin_error(pid, f"command '{cmd}': {e}")

    def dispatch_event(self, event_name: str, payload: Any = None):
        for pid, cb in list(self._event_listeners.get(event_name, [])):
            try:
                cb(payload)
            except Exception as e:
                self._record_plugin_error(pid, f"event '{event_name}': {e}")

    def register_plugin_hotkey(self, plugin_id: str, hotkey_str: str, callback: Callable[[], None]) -> bool:
        if not hotkey_str:
            return False
        try:
            import keyboard

            def _guarded():
                try:
                    callback()
                except Exception as e:
                    self._record_plugin_error(plugin_id, f"hotkey '{hotkey_str}': {e}")

            handle = keyboard.add_hotkey(hotkey_str, _guarded)
            self._hotkey_hooks.setdefault(plugin_id, []).append(handle)
            return True
        except Exception as e:
            self._record_plugin_error(plugin_id, f"register_hotkey '{hotkey_str}': {e}")
            return False

    # ------------------------------------------------------------------
    # Cross-Plugin & Host Service Bus
    # ------------------------------------------------------------------
    def register_service(
        self,
        provider_id: str,
        service_name: str,
        actions: Dict[str, Callable[..., Any]],
        scope_map: Optional[Dict[str, str]] = None,
        policy: Optional[Dict[str, Any]] = None,
    ) -> bool:
        sname = str(service_name or "").strip().lower()
        if not sname or not isinstance(actions, dict):
            return False
        self._services[sname] = {
            "provider_id": provider_id,
            "actions": dict(actions),
            "scope_map": dict(scope_map or {}),
            "policy": dict(policy or {}),
        }
        self.services_changed.emit()
        return True

    def unregister_service(self, provider_id: str, service_name: Optional[str] = None) -> None:
        removed = False
        for sname in list(self._services.keys()):
            if self._services[sname].get("provider_id") == provider_id:
                if service_name is None or sname == str(service_name).strip().lower():
                    self._services.pop(sname, None)
                    removed = True
        if removed:
            self.services_changed.emit()

    def set_service_policy(self, provider_id: str, service_name: str, policy: Dict[str, Any]) -> bool:
        sname = str(service_name or "").strip().lower()
        svc = self._services.get(sname)
        if not svc or svc.get("provider_id") != provider_id:
            return False
        svc["policy"] = dict(policy or {})
        return True

    def get_service_policy(self, service_name: str) -> Dict[str, Any]:
        svc = self._services.get(str(service_name or "").strip().lower())
        return dict(svc.get("policy", {})) if svc else {}

    def list_services(self) -> List[Dict[str, Any]]:
        return [
            {
                "service": sname,
                "provider_id": svc["provider_id"],
                "actions": sorted(svc["actions"].keys()),
                "scopes": dict(svc["scope_map"]),
            }
            for sname, svc in self._services.items()
        ]

    def _resolve_service_name(self, service_name: str) -> Optional[str]:
        sname = str(service_name or "").strip().lower()
        if sname in self._services:
            return sname
        if sname == "loyalty":
            for candidate in ("streamelements", "streamlabs"):
                if candidate in self._services:
                    return candidate
        return None

    def call_service(self, caller_id: str, service_name: str, action: str, **kwargs: Any) -> Dict[str, Any]:
        resolved = self._resolve_service_name(service_name)
        if not resolved:
            return {"ok": False, "error": f"Service '{service_name}' is not available or not loaded."}
        svc = self._services[resolved]
        handler = svc["actions"].get(action)
        if not handler:
            return {"ok": False, "error": f"Unknown action '{action}' on service '{resolved}'."}

        provider_id = svc["provider_id"]
        required_scope = svc["scope_map"].get(action)
        is_host = caller_id == "__host__"
        is_self = caller_id == provider_id

        if not is_host and not is_self:
            caller_info = self._registry.get(caller_id)
            caller_perms = set(caller_info["manifest"].get("permissions", [])) if caller_info else set()
            if required_scope and required_scope not in caller_perms:
                self._notify_service_audit(svc, caller_id, action, required_scope, False, "Missing manifest permission", kwargs)
                return {"ok": False, "error": f"Plugin '{caller_id}' lacks manifest permission '{required_scope}'."}

            policy = svc.get("policy", {})
            allowed_scopes = policy.get("allowed_scopes", {})
            if required_scope and allowed_scopes and not allowed_scopes.get(required_scope, False):
                self._notify_service_audit(svc, caller_id, action, required_scope, False, "Blocked by provider scope policy", kwargs)
                return {"ok": False, "error": f"'{required_scope}' access is disabled in {resolved} permissions."}

            overrides = policy.get("plugin_overrides", {})
            if caller_id in overrides:
                ov_cfg = overrides[caller_id]
                if not ov_cfg.get("enabled", True):
                    self._notify_service_audit(svc, caller_id, action, required_scope or "", False, "Plugin blocked by user", kwargs)
                    return {"ok": False, "error": f"Plugin '{caller_id}' is blocked by {resolved} access control."}
                ov_scopes = ov_cfg.get("scopes", {})
                if required_scope and required_scope in ov_scopes and not ov_scopes[required_scope]:
                    self._notify_service_audit(svc, caller_id, action, required_scope, False, "Scope denied for plugin", kwargs)
                    return {"ok": False, "error": f"Scope '{required_scope}' denied for '{caller_id}'."}

        try:
            res = handler(caller_id=caller_id, **kwargs)
            self._notify_service_audit(svc, caller_id, action, required_scope or "open", True, "OK", kwargs)
            if isinstance(res, dict) and "ok" in res:
                return res
            return {"ok": True, "data": res}
        except Exception as e:
            self._record_plugin_error(provider_id, f"service '{resolved}.{action}': {e}")
            return {"ok": False, "error": str(e)}

    def _notify_service_audit(
        self,
        svc: Dict[str, Any],
        caller_id: str,
        action: str,
        scope: str,
        allowed: bool,
        reason: str,
        kwargs: Dict[str, Any],
    ) -> None:
        audit_cb = svc.get("policy", {}).get("_audit_cb")
        if callable(audit_cb):
            try:
                audit_cb({
                    "caller_id": caller_id,
                    "action": action,
                    "scope": scope,
                    "allowed": allowed,
                    "reason": reason,
                    "params": dict(kwargs),
                })
            except Exception:
                pass

    def call_service_as_host(self, service_name: str, action: str, **kwargs: Any) -> Dict[str, Any]:
        return self.call_service("__host__", service_name, action, **kwargs)

    def stop(self):
        for pid in list(self._registry.keys()):
            self.unload_plugin(pid)
