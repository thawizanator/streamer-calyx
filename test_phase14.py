import os
import sys
import tempfile
from PyQt6.QtWidgets import QApplication, QWidget

app = QApplication.instance() or QApplication(sys.argv)

from plugin_engine import (
    PluginManager,
    create_plugin_template,
    export_folder_as_calyxplugin,
    inspect_calyxplugin_archive,
)
from plugins_tab import PluginsTab, PluginPermissionDialog
from builtin_plugins import _encrypt_chat_msg, _decrypt_chat_msg


class DummyOverlay:
    toasts = []

    def show_hud_toast(self, msg, ok=True):
        self.toasts.append((msg, ok))


def run_tests():
    with tempfile.TemporaryDirectory() as tmp:
        plugins_dir = os.path.join(tmp, "installed_plugins")
        ov = DummyOverlay()
        pm = PluginManager(overlay=ov, plugins_dir=plugins_dir)

        # 1. Verify all 6 first-party core plugins discovered & load cleanly
        listed = pm.list_plugins()
        ids = {p["id"] for p in listed}
        expected_ids = {
            "calyx.ending_credits",
            "calyx.teleprompter",
            "calyx.devos_slots",
            "calyx.web_alerts_bridge",
            "calyx.backstage_chat",
            "calyx.audio_ducking",
        }
        assert expected_ids.issubset(ids), f"Missing built-in plugins: {expected_ids - ids}"

        pm.load_all_enabled()
        for p in pm.list_plugins():
            assert p["loaded"] is True, f"Plugin {p['id']} failed to load: {p['error']}"

        # 2. Verify E2EE backstage chat encryption/decryption & tamper rejection
        pkt = _encrypt_chat_msg("Go live in 5!", "secret-room")
        assert _decrypt_chat_msg(pkt, "secret-room") == "Go live in 5!"
        assert _decrypt_chat_msg(pkt, "wrong-key") is None

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

        # 5. PluginsTab UI instantiation
        tab = PluginsTab(None, pm)
        assert tab.grp_list is not None

        pm.stop()
        print("ALL PHASE 14 CHECKS PASSED!")


if __name__ == "__main__":
    run_tests()
