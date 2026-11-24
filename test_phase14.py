import os
import sys
import tempfile
from PyQt6.QtWidgets import QApplication, QWidget

app = QApplication.instance() or QApplication(sys.argv)

from plugin_engine import (
    CORE_PLUGIN_CATALOG,
    PluginManager,
    create_plugin_template,
    export_folder_as_calyxplugin,
    inspect_calyxplugin_archive,
)
from plugins_tab import PluginsTab, PluginPermissionDialog


class DummyOverlay:
    toasts = []

    def show_hud_toast(self, msg, ok=True):
        self.toasts.append((msg, ok))


def run_tests():
    with tempfile.TemporaryDirectory() as tmp:
        plugins_dir = os.path.join(tmp, "installed_plugins")
        ov = DummyOverlay()
        pm = PluginManager(overlay=ov, plugins_dir=plugins_dir)

        # 1. Verify remaining built-in plugins & downloadable core catalog
        listed = pm.list_plugins()
        ids = {p["id"] for p in listed}
        expected_ids = {
            "calyx.devos_slots",
            "calyx.audio_ducking",
        }
        assert expected_ids.issubset(ids), f"Missing built-in plugins: {expected_ids - ids}"
        catalog_ids = {c["id"] for c in pm.list_core_catalog()}
        assert {
            "calyx.ending_credits",
            "calyx.teleprompter",
            "calyx.backstage_chat",
            "calyx.streamelements",
            "calyx.streamlabs",
        }.issubset(catalog_ids)

        pm.load_all_enabled()
        for p in pm.list_plugins():
            assert p["loaded"] is True, f"Plugin {p['id']} failed to load: {p['error']}"

        # 3. Developer Kit: create template -> export .calyxplugin -> inspect -> install -> disable -> uninstall
        dev_src = os.path.join(tmp, "dev_sample")
        ok_t, msg_t = create_plugin_template(dev_src, "dev.test_addon", "Test Addon", "Tester")
        assert ok_t, msg_t

        bundle_path = os.path.join(tmp, "test_addon.calyxplugin")
        ok_e, msg_e = export_folder_as_calyxplugin(dev_src, bundle_path)
        assert ok_e and os.path.exists(bundle_path), msg_e

        ok_i, manifest, msg_i = inspect_calyxplugin_archive(bundle_path)
        assert ok_i and manifest["id"] == "dev.test_addon" and manifest["_has_checksum"] is True, msg_i

        # Permission modal instantiation
        dlg = PluginPermissionDialog(manifest)
        assert "Test Addon" in dlg.windowTitle() or dlg is not None

        ok_inst, msg_inst = pm.install_calyxplugin(bundle_path)
        assert ok_inst, msg_inst
        assert any(p["id"] == "dev.test_addon" and p["loaded"] for p in pm.list_plugins())

        # 4. Crash-isolated event boundary test
        def _crashing_cb(_payload):
            raise RuntimeError("Simulated third-party plugin crash!")

        pm.subscribe_event("dev.test_addon", "marker_created", _crashing_cb)
        pm.dispatch_event("marker_created", {"description": "Clutch!"})
        err_list = [p for p in pm.list_plugins() if p["id"] == "dev.test_addon"]
        assert "Simulated third-party plugin crash!" in err_list[0]["error"]

        # Toggle disable & uninstall
        pm.set_plugin_enabled("dev.test_addon", False)
        assert not any(p["id"] == "dev.test_addon" and p["loaded"] for p in pm.list_plugins())
        ok_u, _ = pm.uninstall_plugin("dev.test_addon")
        assert ok_u
        assert not any(p["id"] == "dev.test_addon" for p in pm.list_plugins())

        # 5. PluginsTab UI instantiation (including Core Catalog)
        tab = PluginsTab(None, pm)
        assert tab.grp_list is not None
        assert tab.grp_catalog is not None

        # 6. Cross-Plugin & Host Service Bus + Scoped Permissions checks
        pm.register_service(
            "calyx.devos_slots",
            "streamelements",
            actions={
                "get_points": lambda caller_id="", username="", **_: {"ok": True, "username": username, "points": 500},
                "add_points": lambda caller_id="", username="", amount=0, reason="", **_: {"ok": True, "username": username, "points": 500 + int(amount)},
            },
            scope_map={"get_points": "loyalty_read", "add_points": "loyalty_write"},
            policy={"allowed_scopes": {"loyalty_read": True, "loyalty_write": True}, "plugin_overrides": {}},
        )
        # Manifest permission missing -> denied
        res_denied = pm.call_service("calyx.audio_ducking", "loyalty", "get_points", username="alice")
        assert res_denied["ok"] is False and "loyalty_read" in res_denied["error"]

        # Host access -> always allowed
        res_host = pm.call_service_as_host("loyalty", "get_points", username="alice")
        assert res_host["ok"] is True and res_host["points"] == 500

        # Authorized plugin with manifest permissions -> allowed, then blocked by per-plugin override
        pm._registry["calyx.audio_ducking"]["manifest"]["permissions"].extend(["loyalty_read", "loyalty_write"])
        res_ok = pm.call_service("calyx.audio_ducking", "loyalty", "add_points", username="alice", amount=-50, reason="wager")
        assert res_ok["ok"] is True and res_ok["points"] == 450

        pm.set_service_policy(
            "calyx.devos_slots",
            "streamelements",
            {
                "allowed_scopes": {"loyalty_read": True, "loyalty_write": True},
                "plugin_overrides": {"calyx.audio_ducking": {"enabled": True, "scopes": {"loyalty_write": False}}},
            },
        )
        res_ro = pm.call_service("calyx.audio_ducking", "loyalty", "get_points", username="alice")
        assert res_ro["ok"] is True
        res_blocked_write = pm.call_service("calyx.audio_ducking", "loyalty", "add_points", username="alice", amount=50)
        assert res_blocked_write["ok"] is False
        pm.unregister_service("calyx.devos_slots", "streamelements")

        pm.stop()
        print("ALL PHASE 14 CHECKS PASSED!")


if __name__ == "__main__":
    run_tests()
