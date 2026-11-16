import os
import json
import time
import datetime
import ctypes
from PyQt6.QtCore import QObject, pyqtSignal
from debug_logger import log_debug


def get_active_window_title() -> str:
    """Returns the foreground window title on Windows, or 'Desktop' if unavailable."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "Desktop"
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return "Desktop"
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        return title if title else "Desktop"
    except Exception:
        return "Desktop"


class MomentsLogger(QObject):
    """
    Offline Production Moments Logger (Phase 9.2).
    Writes timestamped bookmarks to both:
      - %APPDATA%\\StreamerCalyx\\recording_moments.txt (human-readable editor log)
      - %APPDATA%\\StreamerCalyx\\recording_moments.json (structured timeline data)
    """
    moment_logged = pyqtSignal(dict)

    def __init__(self, app_dir: str, parent=None):
        super().__init__(parent)
        self.app_dir = app_dir
        os.makedirs(self.app_dir, exist_ok=True)
        self.txt_path = os.path.join(self.app_dir, "recording_moments.txt")
        self.json_path = os.path.join(self.app_dir, "recording_moments.json")
        self.session_start_ts: float = time.time()

    def reset_session(self):
        """Resets the elapsed session clock (e.g., when a new recording starts)."""
        self.session_start_ts = time.time()
        log_debug("MOMENTS", "Recording session clock reset.")

    def _format_elapsed(self, seconds: float) -> str:
        secs = max(0, int(seconds))
        hrs, rem = divmod(secs, 3600)
        mins, s = divmod(rem, 60)
        return f"{hrs:02d}:{mins:02d}:{s:02d}"

    def log_moment(self, description: str = "Manual Moment Bookmark", source: str = "Hotkey") -> dict:
        """Appends a timestamped moment entry to recording_moments.txt and recording_moments.json."""
        now = datetime.datetime.now()
        elapsed_sec = time.time() - self.session_start_ts
        elapsed_str = self._format_elapsed(elapsed_sec)
        window_title = get_active_window_title()

        entry = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed": elapsed_str,
            "elapsed_seconds": round(elapsed_sec, 2),
            "source": source,
            "window": window_title,
            "description": description.strip() or "Moment Bookmark",
        }

        # 1. Append to recording_moments.txt
        line = f"[{entry['timestamp']}] [T+{elapsed_str}] [{source}] [{window_title}] {entry['description']}\n"
        try:
            with open(self.txt_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            log_debug("ERROR", f"Failed writing recording_moments.txt: {e}")

        # 2. Append to recording_moments.json
        try:
            items = []
            if os.path.exists(self.json_path):
                with open(self.json_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        items = loaded
            items.append(entry)
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2)
        except Exception as e:
            log_debug("ERROR", f"Failed writing recording_moments.json: {e}")

        log_debug("MOMENTS", f"Logged moment: T+{elapsed_str} | {window_title} | {entry['description']}")
        self.moment_logged.emit(entry)
        return entry
