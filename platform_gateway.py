"""
Phase 13: Multi-Platform Broadcast Gateway (YouTube Live & Kick)
Provides:
  - 13.1 YouTube Gaming / YouTube Live Integration (Google OAuth2 PKCE, Health Watchdog, VOD/Chat Markers, Title/Category)
  - 13.2 Kick Streaming Target Compatibility (Public metadata sync, Kick OAuth2 PKCE / API v1, Webhook Bridge)
  - 13.3 Multi-Stream Unified Event Dispatcher (Concurrent routing across Twitch, YouTube Live, and Kick)
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from debug_logger import log_debug
from twitch_worker import TwitchCommandWorker

YOUTUBE_OAUTH_PORT = 17564
KICK_OAUTH_PORT = 17565

YOUTUBE_MARKERS_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "StreamerCalyx",
    "youtube_markers.json",
)


def _obfuscate_secret(text: str) -> str:
    """Symmetric XOR+Base64 obfuscation matching main.py."""
    if not text:
        return ""
    key = b"StreamerCalyx2026!"
    data = text.encode("utf-8")
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(xored).decode("ascii")


def _deobfuscate_secret(text: str) -> str:
    if not text:
        return ""
    try:
        key = b"StreamerCalyx2026!"
        raw = base64.b64decode(text.encode("ascii"))
        xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
        return xored.decode("utf-8")
    except Exception:
        return ""


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _http_json(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    form_data: Optional[Dict[str, str]] = None,
    timeout: int = 12,
) -> tuple[int, Dict[str, Any]]:
    req_headers = {"User-Agent": "StreamerCalyx/4.0"}
    if headers:
        req_headers.update(headers)
    data_bytes = None
    if body is not None:
        data_bytes = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    elif form_data is not None:
        data_bytes = urllib.parse.urlencode(form_data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip() else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"data": parsed}
    except urllib.error.HTTPError as he:
        err_raw = ""
        try:
            err_raw = he.read().decode("utf-8", errors="replace")
            err_json = json.loads(err_raw) if err_raw.strip() else {}
        except Exception:
            err_json = {"raw": err_raw}
        return he.code, err_json if isinstance(err_json, dict) else {"error": str(err_json)}


def fetch_youtube_channel_info(access_token: str) -> Optional[Dict[str, str]]:
    if not access_token:
        return None
    status, data = _http_json(
        "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if status == 200 and data.get("items"):
        item = data["items"][0]
        return {
            "id": str(item.get("id", "")),
            "title": str(item.get("snippet", {}).get("title", "")),
        }
    return None


def fetch_kick_public_channel(slug: str) -> tuple[bool, Dict[str, Any]]:
    """Fetch public Kick channel metadata without requiring authentication."""
    clean_slug = slug.strip().lstrip("@").lower()
    if not clean_slug:
        return False, {"error": "Empty Kick channel slug."}
    url = f"https://kick.com/api/v2/channels/{urllib.parse.quote(clean_slug)}"
    status, data = _http_json(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StreamerCalyx/4.0",
        },
        timeout=10,
    )
    if status != 200:
        err_msg = data.get("message") or data.get("error") or f"HTTP {status}"
        return False, {"error": f"Kick lookup failed ({err_msg})"}

    livestream = data.get("livestream") or {}
    is_live = bool(livestream and livestream.get("is_live", True))
    cats = livestream.get("categories") or data.get("recent_categories") or []
    category_name = ""
    if cats and isinstance(cats, list) and isinstance(cats[0], dict):
        category_name = str(cats[0].get("name", ""))
    title = str(livestream.get("session_title") or data.get("previous_livestreams", [{}])[0].get("session_title", "") if isinstance(data.get("previous_livestreams"), list) and data.get("previous_livestreams") else livestream.get("session_title", ""))
    return True, {
        "slug": clean_slug,
        "channel_id": str(data.get("id", "")),
        "user_id": str(data.get("user_id", "")),
        "is_live": is_live,
        "title": title,
        "category": category_name,
        "viewers": int(livestream.get("viewer_count", 0) or 0) if is_live else 0,
        "followers": int(data.get("followers_count", 0) or 0),
    }


class _LoopbackOAuthServer(http.server.HTTPServer):
    allow_reuse_address = True


class YouTubeOAuthWorker(QThread):
    """Runs local loopback Google OAuth2 PKCE flow for YouTube Live."""
    auth_success = pyqtSignal(dict)
    auth_error = pyqtSignal(str)

    def __init__(self, client_id: str, client_secret: str = "", port: int = YOUTUBE_OAUTH_PORT):
        super().__init__()
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.port = port
        self._server: Optional[_LoopbackOAuthServer] = None
        self._aborted = False

    def stop(self):
        self._aborted = True
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass

    def run(self):
        if not self.client_id:
            self.auth_error.emit("Google OAuth Client ID is required before signing in.")
            return

        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(16)
        redirect_uri = f"http://127.0.0.1:{self.port}/callback"
        result_box: Dict[str, Optional[str]] = {"code": None, "state": None, "error": None}
        done_event = threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self_h):
                parsed = urllib.parse.urlparse(self_h.path)
                if parsed.path != "/callback":
                    self_h.send_response(404)
                    self_h.end_headers()
                    return
                qs = urllib.parse.parse_qs(parsed.query)
                result_box["code"] = (qs.get("code") or [None])[0]
                result_box["state"] = (qs.get("state") or [None])[0]
                result_box["error"] = (qs.get("error") or [None])[0]

                self_h.send_response(200)
                self_h.send_header("Content-Type", "text/html; charset=utf-8")
                self_h.end_headers()
                if result_box["code"] and not result_box["error"]:
                    html = (
                        "<html><body style='background:#0e0e10;color:#efeff1;font-family:sans-serif;"
                        "display:flex;align-items:center;justify-content:center;height:100vh;'>"
                        "<div style='text-align:center;border:1px solid #ef4444;padding:28px;border-radius:10px;'>"
                        "<h2>YouTube Live Linked!</h2>"
                        "<p>You can close this tab and return to Streamer Calyx.</p>"
                        "</div></body></html>"
                    )
                else:
                    html = (
                        "<html><body style='background:#0e0e10;color:#efeff1;font-family:sans-serif;"
                        "display:flex;align-items:center;justify-content:center;height:100vh;'>"
                        f"<div style='text-align:center;'><h2>Authorization Error</h2><p>{result_box['error']}</p></div>"
                        "</body></html>"
                    )
                self_h.wfile.write(html.encode("utf-8"))
                done_event.set()

            def log_message(self_h, format, *args):
                pass

        try:
            self._server = _LoopbackOAuthServer(("127.0.0.1", self.port), Handler)
            self._server.timeout = 1.0
        except Exception as e:
            self.auth_error.emit(f"Could not bind OAuth port {self.port}: {e}")
            return

        auth_params = urllib.parse.urlencode({
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.force-ssl",
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        })
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{auth_params}"

        import webbrowser
        webbrowser.open(auth_url)

        deadline = time.time() + 180
        while not done_event.is_set() and not self._aborted and time.time() < deadline:
            self._server.handle_request()

        try:
            self._server.server_close()
        except Exception:
            pass

        if self._aborted:
            return
        if result_box["error"]:
            self.auth_error.emit(f"Google OAuth denied: {result_box['error']}")
            return
        if not result_box["code"]:
            self.auth_error.emit("Google OAuth timed out waiting for browser authorization.")
            return
        if result_box["state"] != state:
            self.auth_error.emit("Google OAuth state mismatch (CSRF check failed).")
            return

        token_form = {
            "client_id": self.client_id,
            "code": result_box["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        if self.client_secret:
            token_form["client_secret"] = self.client_secret

        status, tok = _http_json("https://oauth2.googleapis.com/token", method="POST", form_data=token_form)
        if status != 200 or "access_token" not in tok:
            err = tok.get("error_description") or tok.get("error") or f"HTTP {status}"
            self.auth_error.emit(f"Token exchange failed: {err}")
            return

        access_token = tok["access_token"]
        refresh_token = tok.get("refresh_token", "")
        expires_in = int(tok.get("expires_in", 3600) or 3600)
        ch = fetch_youtube_channel_info(access_token) or {}
        self.auth_success.emit({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + expires_in - 60,
            "channel_id": ch.get("id", ""),
            "channel_title": ch.get("title", ""),
        })


class KickOAuthWorker(QThread):
    """Runs local loopback Kick OAuth2 PKCE flow."""
    auth_success = pyqtSignal(dict)
    auth_error = pyqtSignal(str)

    def __init__(self, client_id: str, client_secret: str = "", port: int = KICK_OAUTH_PORT):
        super().__init__()
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.port = port
        self._server: Optional[_LoopbackOAuthServer] = None
        self._aborted = False

    def stop(self):
        self._aborted = True
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass

    def run(self):
        if not self.client_id:
            self.auth_error.emit("Kick OAuth Client ID is required before signing in.")
            return

        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(16)
        redirect_uri = f"http://127.0.0.1:{self.port}/callback"
        result_box: Dict[str, Optional[str]] = {"code": None, "state": None, "error": None}
        done_event = threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self_h):
                parsed = urllib.parse.urlparse(self_h.path)
                if parsed.path != "/callback":
                    self_h.send_response(404)
                    self_h.end_headers()
                    return
                qs = urllib.parse.parse_qs(parsed.query)
                result_box["code"] = (qs.get("code") or [None])[0]
                result_box["state"] = (qs.get("state") or [None])[0]
                result_box["error"] = (qs.get("error") or [None])[0]

                self_h.send_response(200)
                self_h.send_header("Content-Type", "text/html; charset=utf-8")
                self_h.end_headers()
                html = (
                    "<html><body style='background:#0e0e10;color:#efeff1;font-family:sans-serif;"
                    "display:flex;align-items:center;justify-content:center;height:100vh;'>"
                    "<div style='text-align:center;border:1px solid #53fc18;padding:28px;border-radius:10px;'>"
                    "<h2>Kick Account Linked!</h2>"
                    "<p>You can close this tab and return to Streamer Calyx.</p>"
                    "</div></body></html>"
                )
                self_h.wfile.write(html.encode("utf-8"))
                done_event.set()

            def log_message(self_h, format, *args):
                pass

        try:
            self._server = _LoopbackOAuthServer(("127.0.0.1", self.port), Handler)
            self._server.timeout = 1.0
        except Exception as e:
            self.auth_error.emit(f"Could not bind Kick OAuth port {self.port}: {e}")
            return

        auth_params = urllib.parse.urlencode({
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "user:read channel:read channel:write chat:write",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        })
        auth_url = f"https://id.kick.com/oauth/authorize?{auth_params}"

        import webbrowser
        webbrowser.open(auth_url)

        deadline = time.time() + 180
        while not done_event.is_set() and not self._aborted and time.time() < deadline:
            self._server.handle_request()

        try:
            self._server.server_close()
        except Exception:
            pass

        if self._aborted:
            return
        if result_box["error"] or not result_box["code"]:
            self.auth_error.emit(f"Kick OAuth failed: {result_box['error'] or 'Timed out'}")
            return
        if result_box["state"] != state:
            self.auth_error.emit("Kick OAuth state mismatch.")
            return

        form_data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "code": result_box["code"],
        }
        if self.client_secret:
            form_data["client_secret"] = self.client_secret

        status, tok = _http_json("https://id.kick.com/oauth/token", method="POST", form_data=form_data)
        if status != 200 or "access_token" not in tok:
            err = tok.get("error_description") or tok.get("error") or f"HTTP {status}"
            self.auth_error.emit(f"Kick token exchange failed: {err}")
            return

        self.auth_success.emit({
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token", ""),
            "expires_at": time.time() + int(tok.get("expires_in", 3600) or 3600) - 60,
        })


class _AsyncDispatchTask(QThread):
    """Runs a single callable in a background QThread and emits its result."""
    finished_result = pyqtSignal(dict)

    def __init__(self, fn: Callable[[], Dict[str, Any]]):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            res = self._fn()
        except Exception as e:
            res = {"event_type": "error", "summary": str(e), "results": {}}
        self.finished_result.emit(res)


class MultiPlatformGateway(QObject):
    """
    Unified Broadcast Gateway & Event Dispatcher for Twitch, YouTube Live, and Kick.
    """
    dispatch_logged = pyqtSignal(dict)       # {timestamp, event_type, summary, results}
    youtube_health_updated = pyqtSignal(dict)
    kick_status_updated = pyqtSignal(dict)
    gateway_status_changed = pyqtSignal()

    def __init__(self, overlay=None, parent=None):
        super().__init__(parent)
        self.overlay = overlay

        # Destination enable flags
        self.twitch_enabled: bool = True
        self.youtube_enabled: bool = False
        self.kick_enabled: bool = False
        self.dry_run_mode: bool = False

        # YouTube Live credentials & state
        self.yt_client_id: str = ""
        self.yt_client_secret: str = ""
        self.yt_access_token: str = ""
        self.yt_refresh_token: str = ""
        self.yt_token_expires_at: float = 0.0
        self.yt_channel_id: str = ""
        self.yt_channel_title: str = ""
        self.yt_watchdog_enabled: bool = True
        self.yt_post_marker_to_chat: bool = True
        self.yt_active_broadcast: Dict[str, Any] = {}

        # Kick credentials & state
        self.kick_channel_slug: str = ""
        self.kick_client_id: str = ""
        self.kick_client_secret: str = ""
        self.kick_access_token: str = ""
        self.kick_refresh_token: str = ""
        self.kick_webhook_url: str = ""
        self.kick_last_status: Dict[str, Any] = {}

        self._active_tasks: List[QThread] = []
        self._twitch_workers: List[TwitchCommandWorker] = []

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(20000)
        self._watchdog_timer.timeout.connect(self.poll_youtube_health_async)

    def start_watchdog_if_ready(self):
        if self.youtube_enabled and self.yt_watchdog_enabled and self.yt_access_token:
            if not self._watchdog_timer.isActive():
                self._watchdog_timer.start()
        else:
            self._watchdog_timer.stop()

    def stop(self):
        self._watchdog_timer.stop()
        for t in list(self._active_tasks):
            try:
                if t.isRunning():
                    t.wait(1000)
            except Exception:
                pass
        self._active_tasks.clear()

    def get_active_destinations(self) -> List[str]:
        dests = []
        if self.twitch_enabled:
            dests.append("twitch")
        if self.youtube_enabled:
            dests.append("youtube")
        if self.kick_enabled:
            dests.append("kick")
        return dests

    # ------------------------------------------------------------------
    # YouTube Token Refresh & Live Broadcast Health Watchdog (13.1)
    # ------------------------------------------------------------------
    def _ensure_yt_token(self) -> str:
        if not self.yt_access_token:
            return ""
        if self.yt_refresh_token and self.yt_client_id and time.time() >= self.yt_token_expires_at:
            form = {
                "client_id": self.yt_client_id,
                "refresh_token": self.yt_refresh_token,
                "grant_type": "refresh_token",
            }
            if self.yt_client_secret:
                form["client_secret"] = self.yt_client_secret
            status, tok = _http_json("https://oauth2.googleapis.com/token", method="POST", form_data=form)
            if status == 200 and "access_token" in tok:
                self.yt_access_token = tok["access_token"]
                self.yt_token_expires_at = time.time() + int(tok.get("expires_in", 3600) or 3600) - 60
        return self.yt_access_token

    def check_youtube_health_sync(self) -> Dict[str, Any]:
        if self.dry_run_mode and not self.yt_access_token:
            info = {
                "connected": True,
                "is_live": True,
                "broadcast_id": "dryrun-yt-broadcast",
                "title": "Dry-Run YouTube Broadcast",
                "lifeCycleStatus": "live",
                "healthStatus": "good",
                "actualStartTime": datetime.now(timezone.utc).isoformat(),
                "liveChatId": "dryrun-chat",
                "dry_run": True,
            }
            self.yt_active_broadcast = info
            return info

        token = self._ensure_yt_token()
        if not token:
            return {"connected": False, "is_live": False, "healthStatus": "offline", "error": "YouTube not linked."}

        status, data = _http_json(
            "https://www.googleapis.com/youtube/v3/liveBroadcasts"
            "?part=snippet,status,contentDetails&broadcastStatus=active&broadcastType=all",
            headers={"Authorization": f"Bearer {token}"},
        )
        if status != 200:
            err = data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else str(data)
            return {"connected": True, "is_live": False, "healthStatus": "error", "error": err}

        items = data.get("items") or []
        if not items:
            info = {
                "connected": True,
                "is_live": False,
                "broadcast_id": "",
                "title": "",
                "lifeCycleStatus": "offline",
                "healthStatus": "no_active_stream",
            }
            self.yt_active_broadcast = info
            return info

        b = items[0]
        snippet = b.get("snippet", {})
        b_status = b.get("status", {})
        details = b.get("contentDetails", {})
        bound_stream_id = details.get("boundStreamId", "")
        health_str = "good"

        if bound_stream_id:
            s_code, s_data = _http_json(
                f"https://www.googleapis.com/youtube/v3/liveStreams?part=status&id={urllib.parse.quote(bound_stream_id)}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if s_code == 200 and s_data.get("items"):
                hs = s_data["items"][0].get("status", {}).get("healthStatus", {})
                health_str = str(hs.get("status", "good"))

        info = {
            "connected": True,
            "is_live": True,
            "broadcast_id": str(b.get("id", "")),
            "title": str(snippet.get("title", "")),
            "lifeCycleStatus": str(b_status.get("lifeCycleStatus", "live")),
            "healthStatus": health_str,
            "actualStartTime": str(snippet.get("actualStartTime", "")),
            "liveChatId": str(snippet.get("liveChatId", "")),
        }
        self.yt_active_broadcast = info
        return info

    def poll_youtube_health_async(self):
        if not self.youtube_enabled or not self.yt_access_token:
            return

        def _job():
            return {"event_type": "yt_health", "health": self.check_youtube_health_sync()}

        task = _AsyncDispatchTask(_job)
        task.finished_result.connect(lambda res: self.youtube_health_updated.emit(res.get("health", {})))
        self._track_task(task)
        task.start()

    # ------------------------------------------------------------------
    # Per-Platform Action Implementations (Sync, run inside worker thread)
    # ------------------------------------------------------------------
    def _compute_yt_offset_str(self) -> str:
        start_iso = self.yt_active_broadcast.get("actualStartTime", "")
        if not start_iso:
            return "00:00:00"
        try:
            dt_start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            elapsed = max(0, int((datetime.now(timezone.utc) - dt_start).total_seconds()))
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"
        except Exception:
            return "00:00:00"

    def _record_yt_vod_marker(self, description: str, offset_str: str):
        try:
            os.makedirs(os.path.dirname(YOUTUBE_MARKERS_FILE), exist_ok=True)
            items = []
            if os.path.exists(YOUTUBE_MARKERS_FILE):
                with open(YOUTUBE_MARKERS_FILE, "r", encoding="utf-8") as f:
                    items = json.load(f)
            if not isinstance(items, list):
                items = []
            items.append({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "vod_offset": offset_str,
                "broadcast_id": self.yt_active_broadcast.get("broadcast_id", ""),
                "description": description,
            })
            with open(YOUTUBE_MARKERS_FILE, "w", encoding="utf-8") as f:
                json.dump(items[-250:], f, indent=2)
        except Exception as e:
            log_debug("GATEWAY", f"Could not write YouTube VOD marker file: {e}")

    def _youtube_marker(self, description: str) -> Dict[str, Any]:
        if self.dry_run_mode:
            offset = self._compute_yt_offset_str()
            self._record_yt_vod_marker(description, offset)
            return {"ok": True, "dry_run": True, "message": f"[Dry-Run] YouTube VOD chapter @ {offset}: {description}"}

        token = self._ensure_yt_token()
        if not token:
            return {"ok": False, "message": "YouTube account not linked."}

        if not self.yt_active_broadcast.get("is_live"):
            self.check_youtube_health_sync()

        offset = self._compute_yt_offset_str()
        self._record_yt_vod_marker(description, offset)

        chat_id = self.yt_active_broadcast.get("liveChatId", "")
        if self.yt_post_marker_to_chat and chat_id:
            status, data = _http_json(
                "https://www.googleapis.com/youtube/v3/liveChat/messages?part=snippet",
                method="POST",
                headers={"Authorization": f"Bearer {token}"},
                body={
                    "snippet": {
                        "liveChatId": chat_id,
                        "type": "textMessageEvent",
                        "textMessageDetails": {"messageText": f"📍 [{offset}] {description}"[:200]},
                    }
                },
            )
            if status in (200, 201):
                return {"ok": True, "message": f"YouTube VOD + Live Chat marker @ {offset}"}
            err = data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else f"HTTP {status}"
            return {"ok": True, "message": f"YouTube VOD marker saved @ {offset} (chat post skipped: {err})"}

        return {"ok": True, "message": f"YouTube VOD chapter marker saved @ {offset}"}

    def _youtube_metadata(self, title: str, category: str) -> Dict[str, Any]:
        if self.dry_run_mode:
            return {"ok": True, "dry_run": True, "message": f"[Dry-Run] YouTube title='{title}'"}

        token = self._ensure_yt_token()
        if not token:
            return {"ok": False, "message": "YouTube account not linked."}

        if not self.yt_active_broadcast.get("broadcast_id"):
            self.check_youtube_health_sync()
        vid = self.yt_active_broadcast.get("broadcast_id", "")
        if not vid:
            return {"ok": False, "message": "No active YouTube broadcast found to update."}

        g_code, g_data = _http_json(
            f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={urllib.parse.quote(vid)}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if g_code != 200 or not g_data.get("items"):
            return {"ok": False, "message": f"Could not fetch YouTube video snippet (HTTP {g_code})."}

        snippet = g_data["items"][0].get("snippet", {})
        if title:
            snippet["title"] = title[:100]
        snippet["categoryId"] = snippet.get("categoryId") or "20"  # 20 = Gaming

        p_code, p_data = _http_json(
            "https://www.googleapis.com/youtube/v3/videos?part=snippet",
            method="PUT",
            headers={"Authorization": f"Bearer {token}"},
            body={"id": vid, "snippet": snippet},
        )
        if p_code == 200:
            return {"ok": True, "message": f"YouTube title updated to '{snippet['title']}'"}
        err = p_data.get("error", {}).get("message") if isinstance(p_data.get("error"), dict) else f"HTTP {p_code}"
        return {"ok": False, "message": f"YouTube metadata update failed: {err}"}

    def _kick_dispatch(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        slug = self.kick_channel_slug.strip().lstrip("@").lower()
        if self.dry_run_mode:
            return {
                "ok": True,
                "dry_run": True,
                "message": f"[Dry-Run] Kick ({slug or 'unconfigured'}) {event_type}: {payload.get('description') or payload.get('title') or payload.get('message', '')}",
            }

        results = []
        any_ok = False

        # 1. Official Kick Public API v1 if token is present
        if self.kick_access_token:
            headers = {"Authorization": f"Bearer {self.kick_access_token}"}
            if event_type in ("marker", "announcement"):
                msg = payload.get("description") or payload.get("message") or ""
                if event_type == "marker":
                    msg = f"📍 [MARKER] {msg}"
                code, resp = _http_json(
                    "https://api.kick.com/public/v1/chat",
                    method="POST",
                    headers=headers,
                    body={"content": msg[:500], "type": "bot"},
                )
                if code in (200, 201, 204):
                    any_ok = True
                    results.append("Kick API chat posted")
                else:
                    results.append(f"Kick API chat HTTP {code}")
            elif event_type == "metadata_update":
                patch_body: Dict[str, Any] = {}
                if payload.get("title"):
                    patch_body["stream_title"] = payload["title"]
                code, resp = _http_json(
                    "https://api.kick.com/public/v1/channels",
                    method="PATCH",
                    headers=headers,
                    body=patch_body,
                )
                if code in (200, 204):
                    any_ok = True
                    results.append("Kick API title updated")
                else:
                    results.append(f"Kick API PATCH HTTP {code}")

        # 2. Webhook Bridge (Botrix / Kicklet / n8n / Custom Relay)
        if self.kick_webhook_url.strip():
            wh_body = {
                "source": "StreamerCalyx",
                "platform": "kick",
                "event": event_type,
                "channel": slug,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
            code, _ = _http_json(self.kick_webhook_url.strip(), method="POST", body=wh_body)
            if 200 <= code < 300:
                any_ok = True
                results.append("Kick webhook delivered")
            else:
                results.append(f"Kick webhook HTTP {code}")

        if not self.kick_access_token and not self.kick_webhook_url.strip():
            return {
                "ok": False,
                "message": "Kick has no OAuth token or Webhook URL configured (enable Dry-Run to test without a Kick account).",
            }

        return {"ok": any_ok, "message": " | ".join(results)}

    def _twitch_metadata_sync(self, title: str, category: str) -> Dict[str, Any]:
        if self.dry_run_mode:
            return {"ok": True, "dry_run": True, "message": f"[Dry-Run] Twitch title='{title}', category='{category}'"}
        ov = self.overlay
        token = getattr(ov, "twitch_token", "") if ov else ""
        client_id = getattr(ov, "twitch_client_id", "") if ov else ""
        broadcaster_id = getattr(ov, "twitch_user_id", "") if ov else ""
        if not token or not client_id or not broadcaster_id:
            return {"ok": False, "message": "Twitch credentials incomplete."}

        headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
        body: Dict[str, Any] = {}
        if title:
            body["title"] = title[:140]
        if category:
            g_code, g_data = _http_json(
                f"https://api.twitch.tv/helix/games?name={urllib.parse.quote(category.strip())}",
                headers=headers,
            )
            if g_code == 200 and g_data.get("data"):
                body["game_id"] = str(g_data["data"][0]["id"])

        if not body:
            return {"ok": False, "message": "Nothing to update on Twitch."}

        p_code, p_data = _http_json(
            f"https://api.twitch.tv/helix/channels?broadcaster_id={urllib.parse.quote(str(broadcaster_id))}",
            method="PATCH",
            headers=headers,
            body=body,
        )
        if p_code in (200, 204):
            return {"ok": True, "message": f"Twitch updated ({', '.join(body.keys())})"}
        return {"ok": False, "message": f"Twitch PATCH failed (HTTP {p_code})"}

    # ------------------------------------------------------------------
    # 13.3 Unified Concurrent Event Dispatcher
    # ------------------------------------------------------------------
    def _track_task(self, task: QThread):
        self._active_tasks.append(task)
        task.finished.connect(lambda: self._active_tasks.remove(task) if task in self._active_tasks else None)

    def _dispatch_twitch_worker(self, command: str, argument: str):
        ov = self.overlay
        if not ov:
            return
        if self.dry_run_mode:
            return
        token = getattr(ov, "twitch_token", "")
        channel = getattr(ov, "twitch_channel", "")
        client_id = getattr(ov, "twitch_client_id", "")
        user_id = getattr(ov, "twitch_user_id", "")
        if not token or not channel:
            return
        worker = TwitchCommandWorker(command, argument, token, client_id, channel, user_id=user_id)
        if hasattr(ov, "on_twitch_worker_result"):
            worker.result_signal.connect(ov.on_twitch_worker_result)
        self._twitch_workers.append(worker)
        worker.finished.connect(lambda: self._twitch_workers.remove(worker) if worker in self._twitch_workers else None)
        worker.start()

    def dispatch_marker(self, description: str):
        desc = (description or "Highlight").strip()
        dests = self.get_active_destinations()
        if not dests:
            return

        # Twitch via existing TwitchCommandWorker (or Dry-Run log)
        if "twitch" in dests and not self.dry_run_mode:
            self._dispatch_twitch_worker("/marker", desc)

        def _job():
            results: Dict[str, Any] = {}
            threads: List[threading.Thread] = []
            lock = threading.Lock()

            def _run(name: str, fn: Callable[[], Dict[str, Any]]):
                r = fn()
                with lock:
                    results[name] = r

            if "twitch" in dests:
                if self.dry_run_mode:
                    results["twitch"] = {"ok": True, "dry_run": True, "message": f"[Dry-Run] Twitch /marker '{desc}'"}
                else:
                    ov = self.overlay
                    has_tw = bool(ov and getattr(ov, "twitch_token", "") and getattr(ov, "twitch_channel", ""))
                    results["twitch"] = {
                        "ok": has_tw,
                        "message": f"Dispatched /marker '{desc}'" if has_tw else "Twitch not linked",
                    }

            if "youtube" in dests:
                t = threading.Thread(target=_run, args=("youtube", lambda: self._youtube_marker(desc)), daemon=True)
                threads.append(t)
                t.start()

            if "kick" in dests:
                t = threading.Thread(
                    target=_run,
                    args=("kick", lambda: self._kick_dispatch("marker", {"description": desc})),
                    daemon=True,
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=12)

            return {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "event_type": "marker",
                "summary": f"Marker: {desc}",
                "results": results,
            }

        task = _AsyncDispatchTask(_job)
        task.finished_result.connect(self.dispatch_logged.emit)
        self._track_task(task)
        task.start()

    def dispatch_metadata_update(self, title: str, category: str):
        dests = self.get_active_destinations()
        if not dests:
            return

        def _job():
            results: Dict[str, Any] = {}
            threads: List[threading.Thread] = []
            lock = threading.Lock()

            def _run(name: str, fn: Callable[[], Dict[str, Any]]):
                r = fn()
                with lock:
                    results[name] = r

            if "twitch" in dests:
                t = threading.Thread(target=_run, args=("twitch", lambda: self._twitch_metadata_sync(title, category)), daemon=True)
                threads.append(t)
                t.start()
            if "youtube" in dests:
                t = threading.Thread(target=_run, args=("youtube", lambda: self._youtube_metadata(title, category)), daemon=True)
                threads.append(t)
                t.start()
            if "kick" in dests:
                t = threading.Thread(
                    target=_run,
                    args=("kick", lambda: self._kick_dispatch("metadata_update", {"title": title, "category": category})),
                    daemon=True,
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=15)

            return {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "event_type": "metadata_update",
                "summary": f"Metadata Sync: '{title}' [{category}]",
                "results": results,
            }

        task = _AsyncDispatchTask(_job)
        task.finished_result.connect(self.dispatch_logged.emit)
        self._track_task(task)
        task.start()

    def dispatch_announcement(self, message: str):
        msg = (message or "").strip()
        if not msg:
            return
        dests = self.get_active_destinations()
        if "twitch" in dests and not self.dry_run_mode:
            self._dispatch_twitch_worker("/announce", msg)

        def _job():
            results: Dict[str, Any] = {}
            threads: List[threading.Thread] = []
            lock = threading.Lock()

            def _run(name: str, fn: Callable[[], Dict[str, Any]]):
                r = fn()
                with lock:
                    results[name] = r

            if "twitch" in dests:
                results["twitch"] = (
                    {"ok": True, "dry_run": True, "message": f"[Dry-Run] Twitch /announce '{msg}'"}
                    if self.dry_run_mode
                    else {"ok": True, "message": "Dispatched /announce"}
                )

            if "youtube" in dests:
                def _yt_chat():
                    if self.dry_run_mode:
                        return {"ok": True, "dry_run": True, "message": f"[Dry-Run] YouTube chat: '{msg}'"}
                    token = self._ensure_yt_token()
                    chat_id = self.yt_active_broadcast.get("liveChatId", "")
                    if not token or not chat_id:
                        return {"ok": False, "message": "No active YouTube liveChatId"}
                    code, _ = _http_json(
                        "https://www.googleapis.com/youtube/v3/liveChat/messages?part=snippet",
                        method="POST",
                        headers={"Authorization": f"Bearer {token}"},
                        body={"snippet": {"liveChatId": chat_id, "type": "textMessageEvent", "textMessageDetails": {"messageText": msg[:200]}}},
                    )
                    return {"ok": code in (200, 201), "message": "YouTube chat posted" if code in (200, 201) else f"YouTube HTTP {code}"}

                t = threading.Thread(target=_run, args=("youtube", _yt_chat), daemon=True)
                threads.append(t)
                t.start()

            if "kick" in dests:
                t = threading.Thread(
                    target=_run,
                    args=("kick", lambda: self._kick_dispatch("announcement", {"message": msg})),
                    daemon=True,
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=12)

            return {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "event_type": "announcement",
                "summary": f"Announce: {msg}",
                "results": results,
            }

        task = _AsyncDispatchTask(_job)
        task.finished_result.connect(self.dispatch_logged.emit)
        self._track_task(task)
        task.start()

    def sync_kick_public_async(self, slug: str):
        def _job():
            ok, info = fetch_kick_public_channel(slug)
            return {"event_type": "kick_sync", "ok": ok, "info": info}

        task = _AsyncDispatchTask(_job)
        task.finished_result.connect(lambda res: self._on_kick_sync_done(res))
        self._track_task(task)
        task.start()

    def _on_kick_sync_done(self, res: Dict[str, Any]):
        info = res.get("info", {})
        if res.get("ok"):
            self.kick_last_status = info
        self.kick_status_updated.emit({"ok": res.get("ok", False), **info})

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def export_settings(self) -> Dict[str, Any]:
        return {
            "twitch_enabled": self.twitch_enabled,
            "youtube_enabled": self.youtube_enabled,
            "kick_enabled": self.kick_enabled,
            "dry_run_mode": self.dry_run_mode,
            "yt_client_id": self.yt_client_id,
            "yt_client_secret_obf": _obfuscate_secret(self.yt_client_secret),
            "yt_access_token_obf": _obfuscate_secret(self.yt_access_token),
            "yt_refresh_token_obf": _obfuscate_secret(self.yt_refresh_token),
            "yt_token_expires_at": self.yt_token_expires_at,
            "yt_channel_id": self.yt_channel_id,
            "yt_channel_title": self.yt_channel_title,
            "yt_watchdog_enabled": self.yt_watchdog_enabled,
            "yt_post_marker_to_chat": self.yt_post_marker_to_chat,
            "kick_channel_slug": self.kick_channel_slug,
            "kick_client_id": self.kick_client_id,
            "kick_client_secret_obf": _obfuscate_secret(self.kick_client_secret),
            "kick_access_token_obf": _obfuscate_secret(self.kick_access_token),
            "kick_refresh_token_obf": _obfuscate_secret(self.kick_refresh_token),
            "kick_webhook_url": self.kick_webhook_url,
        }

    def import_settings(self, d: Dict[str, Any]):
        if not isinstance(d, dict):
            return
        self.twitch_enabled = bool(d.get("twitch_enabled", True))
        self.youtube_enabled = bool(d.get("youtube_enabled", False))
        self.kick_enabled = bool(d.get("kick_enabled", False))
        self.dry_run_mode = bool(d.get("dry_run_mode", False))

        self.yt_client_id = str(d.get("yt_client_id", ""))
        self.yt_client_secret = _deobfuscate_secret(d.get("yt_client_secret_obf", ""))
        self.yt_access_token = _deobfuscate_secret(d.get("yt_access_token_obf", ""))
        self.yt_refresh_token = _deobfuscate_secret(d.get("yt_refresh_token_obf", ""))
        self.yt_token_expires_at = float(d.get("yt_token_expires_at", 0.0) or 0.0)
        self.yt_channel_id = str(d.get("yt_channel_id", ""))
        self.yt_channel_title = str(d.get("yt_channel_title", ""))
        self.yt_watchdog_enabled = bool(d.get("yt_watchdog_enabled", True))
        self.yt_post_marker_to_chat = bool(d.get("yt_post_marker_to_chat", True))

        self.kick_channel_slug = str(d.get("kick_channel_slug", ""))
        self.kick_client_id = str(d.get("kick_client_id", ""))
        self.kick_client_secret = _deobfuscate_secret(d.get("kick_client_secret_obf", ""))
        self.kick_access_token = _deobfuscate_secret(d.get("kick_access_token_obf", ""))
        self.kick_refresh_token = _deobfuscate_secret(d.get("kick_refresh_token_obf", ""))
        self.kick_webhook_url = str(d.get("kick_webhook_url", ""))

        self.start_watchdog_if_ready()
