import os
import sys
import json
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QSignalSpy

app = QApplication.instance() or QApplication(sys.argv)

from platform_gateway import (
    MultiPlatformGateway,
    YOUTUBE_MARKERS_FILE,
    fetch_kick_public_channel,
    _obfuscate_secret,
    _deobfuscate_secret,
)
from gateway_tab import MultiPlatformGatewayTab


class DummyOverlay:
    twitch_token = "tok_test"
    twitch_channel = "testchannel"
    twitch_display_name = "TestChannel"
    twitch_client_id = "cid_test"
    twitch_user_id = "12345"

    def save_settings(self):
        pass


class DummyMainWin:
    def __init__(self, overlay):
        self.overlay = overlay

    def set_view_index(self, idx):
        pass


def run_tests():
    # 1. Secret obfuscation round-trip
    raw = "super_secret_oauth_token_123"
    obf = _obfuscate_secret(raw)
    assert obf != raw
    assert _deobfuscate_secret(obf) == raw

    # 2. Gateway initialization & settings round-trip
    ov = DummyOverlay()
    gw = MultiPlatformGateway(overlay=ov)
    gw.twitch_enabled = True
    gw.youtube_enabled = True
    gw.kick_enabled = True
    gw.dry_run_mode = True
    gw.yt_client_id = "yt-cid-123"
    gw.yt_client_secret = "yt-sec-456"
    gw.kick_channel_slug = "testkick"
    gw.kick_webhook_url = "https://example.invalid/webhook"

    exported = gw.export_settings()
    assert exported["yt_client_secret_obf"] != "yt-sec-456"

    gw2 = MultiPlatformGateway(overlay=ov)
    gw2.import_settings(exported)
    assert gw2.get_active_destinations() == ["twitch", "youtube", "kick"]
    assert gw2.yt_client_id == "yt-cid-123"
    assert gw2.yt_client_secret == "yt-sec-456"
    assert gw2.kick_channel_slug == "testkick"
    assert gw2.dry_run_mode is True

    # 3. YouTube Dry-Run Health Watchdog check
    health = gw2.check_youtube_health_sync()
    assert health["is_live"] is True
    assert health["healthStatus"] == "good"

    # 4. Concurrent Dry-Run Unified Dispatchers (Marker, Metadata, Announcement)
    spy = QSignalSpy(gw2.dispatch_logged)

    gw2.dispatch_marker("Boss Defeated!")
    assert spy.wait(5000), "Marker dispatch timed out"
    entry_m = spy[-1][0]
    assert entry_m["event_type"] == "marker"
    assert set(entry_m["results"].keys()) == {"twitch", "youtube", "kick"}
    assert all(r["ok"] for r in entry_m["results"].values())

    # Verify YouTube VOD chapter marker was persisted
    assert os.path.exists(YOUTUBE_MARKERS_FILE)
    with open(YOUTUBE_MARKERS_FILE, "r", encoding="utf-8") as f:
        markers = json.load(f)
    assert any(m.get("description") == "Boss Defeated!" for m in markers)

    gw2.dispatch_metadata_update("Phase 13 Stream!", "Just Chatting")
    assert spy.wait(5000), "Metadata dispatch timed out"
    entry_meta = spy[-1][0]
    assert entry_meta["event_type"] == "metadata_update"
    assert all(r["ok"] for r in entry_meta["results"].values())

    gw2.dispatch_announcement("Multi-stream test!")
    assert spy.wait(5000), "Announcement dispatch timed out"
    entry_ann = spy[-1][0]
    assert entry_ann["event_type"] == "announcement"
    assert all(r["ok"] for r in entry_ann["results"].values())

    # 5. Kick empty slug guard
    ok_k, info_k = fetch_kick_public_channel("")
    assert ok_k is False and "error" in info_k

    # 6. Gateway UI Tab instantiation
    mw = DummyMainWin(ov)
    tab = MultiPlatformGatewayTab(mw, gw2)
    assert "Twitch" in tab.lbl_active_dests.text()
    assert "Youtube" in tab.lbl_active_dests.text()
    assert "Kick" in tab.lbl_active_dests.text()
    tab._on_dispatch_logged(entry_m)
    assert "Boss Defeated!" in tab.txt_dispatch_log.toPlainText()

    gw2.stop()
    print("ALL PHASE 13 CHECKS PASSED!")


if __name__ == "__main__":
    run_tests()
