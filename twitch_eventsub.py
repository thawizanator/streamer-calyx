"""
Twitch EventSub WebSocket Client & Universal Chat/Points/Bits Normalizer.
Provides real-time incoming Twitch chat (!commands), Channel Points redemptions,
and Bits/Cheers with automatic Affiliate/Partner capability gating.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtWebSockets import QWebSocket

from debug_logger import log_debug

EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"
EVENTSUB_SUB_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"


def is_monetized_broadcaster(broadcaster_type: str) -> bool:
    """Returns True if Twitch channel is Affiliate or Partner (supports Channel Points & Bits)."""
    return str(broadcaster_type or "").strip().lower() in ("affiliate", "partner")


def parse_chat_command(text: str) -> tuple[str, List[str], str]:
    """Parses '!cmd arg1 arg2' -> ('!cmd', ['arg1', 'arg2'], 'arg1 arg2')."""
    s = (text or "").strip()
    if not s.startswith("!") or len(s) < 2:
        return "", [], ""
    parts = s.split(None, 1)
    cmd = parts[0].lower()
    raw_args = parts[1].strip() if len(parts) > 1 else ""
    args = raw_args.split() if raw_args else []
    return cmd, args, raw_args


class TwitchEventSubClient(QObject):
    """
    Persistent Twitch EventSub WebSocket listener.
    Automatically skips Channel Points & Bits subscriptions when the linked
    account is not Affiliate/Partner so non-monetized accounts never hit 403 errors.
    """
    chat_message_received = pyqtSignal(dict)
    channel_points_redeemed = pyqtSignal(dict)
    bits_cheered = pyqtSignal(dict)
    status_changed = pyqtSignal(str, str)  # (state: 'connected'|'connecting'|'disconnected'|'error', message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_ws_connected)
        self._ws.disconnected.connect(self._on_ws_disconnected)
        self._ws.textMessageReceived.connect(self._on_text_message)
        self._ws.errorOccurred.connect(self._on_ws_error)

        self._token: str = ""
        self._client_id: str = ""
        self._broadcaster_id: str = ""
        self._user_id: str = ""
        self._channel: str = ""
        self._broadcaster_type: str = ""
        self._session_id: str = ""
        self._should_run: bool = False

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._connect_ws)

    def configure(
        self,
        token: str,
        client_id: str,
        broadcaster_id: str,
        user_id: str = "",
        channel: str = "",
        broadcaster_type: str = "",
    ):
        self._token = (token or "").strip()
        self._client_id = (client_id or "").strip()
        self._broadcaster_id = str(broadcaster_id or "").strip()
        self._user_id = str(user_id or broadcaster_id or "").strip()
        self._channel = (channel or "").strip().lower()
        self._broadcaster_type = str(broadcaster_type or "").strip().lower()

    def start(self):
        if not self._token or not self._client_id or not self._broadcaster_id:
            self.status_changed.emit("disconnected", "Twitch credentials incomplete.")
            return
        self._should_run = True
        self._connect_ws()

    def stop(self):
        self._should_run = False
        self._reconnect_timer.stop()
        self._session_id = ""
        try:
            self._ws.close()
        except Exception:
            pass
        self.status_changed.emit("disconnected", "EventSub stopped.")

    def _connect_ws(self, url: str = EVENTSUB_WS_URL):
        if not self._should_run:
            return
        self.status_changed.emit("connecting", "Connecting to Twitch EventSub...")
        self._ws.open(QUrl(url))

    def _on_ws_connected(self):
        log_debug("EVENTSUB", "WebSocket connected; awaiting session_welcome...")

    def _on_ws_disconnected(self):
        self._session_id = ""
        if self._should_run:
            self.status_changed.emit("connecting", "EventSub disconnected; reconnecting in 5s...")
            self._reconnect_timer.start(5000)
        else:
            self.status_changed.emit("disconnected", "EventSub disconnected.")

    def _on_ws_error(self, _err):
        log_debug("EVENTSUB", f"WebSocket error: {self._ws.errorString()}")

    def _on_text_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        meta = msg.get("metadata", {})
        mtype = meta.get("message_type", "")
        payload = msg.get("payload", {})

        if mtype == "session_welcome":
            session = payload.get("session", {})
            self._session_id = str(session.get("id", ""))
            log_debug("EVENTSUB", f"Session welcome id={self._session_id}; registering subscriptions...")
            threading.Thread(target=self._register_subscriptions, args=(self._session_id,), daemon=True).start()

        elif mtype == "session_reconnect":
            new_url = str(payload.get("session", {}).get("reconnect_url", "")).strip()
            if new_url:
                log_debug("EVENTSUB", f"Session reconnect requested -> {new_url}")
                self._ws.open(QUrl(new_url))

        elif mtype == "notification":
            sub_type = meta.get("subscription_type", "")
            event = payload.get("event", {})
            self._handle_notification(sub_type, event)

    def _register_subscriptions(self, session_id: str):
        if not session_id or not self._token or not self._client_id or not self._broadcaster_id:
            return

        subs: List[tuple[str, str, Dict[str, str]]] = [
            (
                "channel.chat.message",
                "1",
                {
                    "broadcaster_user_id": self._broadcaster_id,
                    "user_id": self._user_id or self._broadcaster_id,
                },
            )
        ]

        # Capability Guard: only subscribe to Channel Points & Bits if Affiliate or Partner
        if is_monetized_broadcaster(self._broadcaster_type):
            subs.append(
                (
                    "channel.channel_points_custom_reward_redemption.add",
                    "1",
                    {"broadcaster_user_id": self._broadcaster_id},
                )
            )
            subs.append(
                (
                    "channel.cheer",
                    "1",
                    {"broadcaster_user_id": self._broadcaster_id},
                )
            )
        else:
            log_debug(
                "EVENTSUB",
                f"Broadcaster type='{self._broadcaster_type or 'standard'}' — skipping Channel Points & Bits subscriptions.",
            )

        headers = {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        ok_subs = []
        for sub_type, ver, cond in subs:
            body = {
                "type": sub_type,
                "version": ver,
                "condition": cond,
                "transport": {"method": "websocket", "session_id": session_id},
            }
            req = urllib.request.Request(
                EVENTSUB_SUB_URL,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 202):
                        ok_subs.append(sub_type)
            except urllib.error.HTTPError as he:
                err_body = ""
                try:
                    err_body = he.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                log_debug("EVENTSUB", f"Subscription {sub_type} failed (HTTP {he.code}): {err_body}")
            except Exception as e:
                log_debug("EVENTSUB", f"Subscription {sub_type} error: {e}")

        if ok_subs:
            self.status_changed.emit("connected", f"EventSub active ({', '.join(ok_subs)})")
        else:
            self.status_changed.emit("error", "No EventSub subscriptions succeeded (re-link Twitch to grant scopes).")

    def _handle_notification(self, sub_type: str, event: Dict[str, Any]):
        ts = datetime.now(timezone.utc).isoformat()
        if sub_type == "channel.chat.message":
            msg_text = str(event.get("message", {}).get("text", ""))
            cmd, args, raw_args = parse_chat_command(msg_text)
            badges = {str(b.get("set_id", "")).lower() for b in event.get("badges", []) if isinstance(b, dict)}
            norm = {
                "platform": "twitch",
                "channel": self._channel or str(event.get("broadcaster_user_login", "")),
                "username": str(event.get("chatter_user_login", "")),
                "display_name": str(event.get("chatter_user_name", "")),
                "user_id": str(event.get("chatter_user_id", "")),
                "message": msg_text,
                "command": cmd,
                "args": args,
                "raw_args": raw_args,
                "is_broadcaster": "broadcaster" in badges,
                "is_mod": "moderator" in badges or "broadcaster" in badges,
                "is_sub": "subscriber" in badges or "founder" in badges,
                "message_id": str(event.get("message_id", "")),
                "timestamp": ts,
            }
            self.chat_message_received.emit(norm)

        elif sub_type == "channel.channel_points_custom_reward_redemption.add":
            reward = event.get("reward", {})
            norm = {
                "platform": "twitch",
                "channel": self._channel or str(event.get("broadcaster_user_login", "")),
                "username": str(event.get("user_login", "")),
                "display_name": str(event.get("user_name", "")),
                "user_id": str(event.get("user_id", "")),
                "reward_id": str(reward.get("id", "")),
                "reward_title": str(reward.get("title", "")),
                "reward_cost": int(reward.get("cost", 0) or 0),
                "user_input": str(event.get("user_input", "")),
                "redemption_id": str(event.get("id", "")),
                "status": str(event.get("status", "unfulfilled")),
                "timestamp": ts,
            }
            self.channel_points_redeemed.emit(norm)

        elif sub_type == "channel.cheer":
            norm = {
                "platform": "twitch",
                "channel": self._channel or str(event.get("broadcaster_user_login", "")),
                "username": str(event.get("user_login", "") or "anonymous"),
                "display_name": str(event.get("user_name", "") or "Anonymous"),
                "user_id": str(event.get("user_id", "")),
                "bits": int(event.get("bits", 0) or 0),
                "message": str(event.get("message", "")),
                "is_anonymous": bool(event.get("is_anonymous", False)),
                "timestamp": ts,
            }
            self.bits_cheered.emit(norm)

    def simulate_chat_command(self, username: str, message: str, is_sub: bool = False, is_mod: bool = False):
        cmd, args, raw_args = parse_chat_command(message)
        self.chat_message_received.emit({
            "platform": "twitch",
            "channel": self._channel or "local_test",
            "username": username.lower(),
            "display_name": username,
            "user_id": "sim-user",
            "message": message,
            "command": cmd,
            "args": args,
            "raw_args": raw_args,
            "is_broadcaster": False,
            "is_mod": is_mod,
            "is_sub": is_sub,
            "message_id": "sim-msg",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "simulated": True,
        })

    def simulate_channel_points(self, username: str, reward_title: str, cost: int = 500, user_input: str = ""):
        self.channel_points_redeemed.emit({
            "platform": "twitch",
            "channel": self._channel or "local_test",
            "username": username.lower(),
            "display_name": username,
            "user_id": "sim-user",
            "reward_id": "sim-reward",
            "reward_title": reward_title,
            "reward_cost": int(cost),
            "user_input": user_input,
            "redemption_id": "sim-redemption",
            "status": "unfulfilled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "simulated": True,
        })

    def simulate_bits(self, username: str, bits: int = 100, message: str = "Cheer100"):
        self.bits_cheered.emit({
            "platform": "twitch",
            "channel": self._channel or "local_test",
            "username": username.lower(),
            "display_name": username,
            "user_id": "sim-user",
            "bits": int(bits),
            "message": message,
            "is_anonymous": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "simulated": True,
        })
