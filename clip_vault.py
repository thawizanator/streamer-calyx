import os
import csv
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal, QFileSystemWatcher, QTimer, Qt, QUrl
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel
)

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    HAS_MULTIMEDIA_VIDEO = True
except Exception:
    HAS_MULTIMEDIA_VIDEO = False

try:
    from debug_logger import log_debug
except ImportError:
    def log_debug(tag, msg):
        print(f"[{tag}] {msg}")


VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".flv")


def _seconds_to_timecode(total_seconds: int, fps: int = 60) -> str:
    """Formats integer seconds into SMPTE HH:MM:SS:FF timecode."""
    total_seconds = max(0, int(total_seconds))
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}:00"


def _seconds_to_yt(total_seconds: int) -> str:
    """Formats integer seconds into YouTube chapter timestamp (MM:SS or HH:MM:SS)."""
    total_seconds = max(0, int(total_seconds))
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hrs > 0:
        return f"{hrs:d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


class ClipVaultManager(QObject):
    """
    Watches an OBS/SLOBS replay directory, matches saved video replays to
    AutoClipEngine reaction timestamps, and exports markers for video editors.
    """

    clips_updated = pyqtSignal(list)  # List of clip dicts

    def __init__(self, engine=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.replay_dir = ""
        self.auto_rename = False
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.setInterval(1200)
        self._scan_timer.timeout.connect(self.scan_clips)
        self._clips = []

    def set_replay_dir(self, path: str, auto_rename: bool = False):
        self.auto_rename = bool(auto_rename)
        norm = os.path.normpath(path.strip()) if path and path.strip() else ""
        if self.replay_dir and self.replay_dir in self._watcher.directories():
            self._watcher.removePath(self.replay_dir)
        self.replay_dir = norm
        if self.replay_dir and os.path.isdir(self.replay_dir):
            self._watcher.addPath(self.replay_dir)
        self.scan_clips()

    def _on_dir_changed(self, _path: str):
        # Wait briefly so OBS/SLOBS finishes flushing the replay file before matching/renaming
        self._scan_timer.start()

    def scan_clips(self) -> list:
        clips = []
        history = self.engine.get_reaction_history() if self.engine else []
        if not self.replay_dir or not os.path.isdir(self.replay_dir):
            self._clips = []
            self.clips_updated.emit([])
            return []

        try:
            entries = sorted(
                os.listdir(self.replay_dir),
                key=lambda name: os.path.getmtime(os.path.join(self.replay_dir, name)),
                reverse=True,
            )
        except Exception as e:
            log_debug("CLIPVAULT", f"Error listing replay dir '{self.replay_dir}': {e}")
            entries = []

        for fname in entries:
            if not fname.lower().endswith(VIDEO_EXTENSIONS):
                continue
            fpath = os.path.join(self.replay_dir, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                mtime = os.path.getmtime(fpath)
                size_mb = os.path.getsize(fpath) / (1024.0 * 1024.0)
            except OSError:
                continue

            matched = self._match_reaction(mtime, history)
            if self.auto_rename and matched and matched["reaction_slug"] not in fname:
                new_path = self._try_auto_rename(fpath, mtime, matched)
                if new_path:
                    fpath = new_path
                    fname = os.path.basename(new_path)

            clips.append({
                "filename": fname,
                "path": fpath,
                "mtime": mtime,
                "date_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_mb": round(size_mb, 1),
                "reaction_icon": matched.get("reaction_icon", "🎬") if matched else "🎬",
                "reaction_label": matched.get("reaction_label", "Unmatched Replay") if matched else "Unmatched Replay",
                "position_seconds": matched.get("position_seconds", 0) if matched else 0,
            })

        self._clips = clips
        self.clips_updated.emit(clips)
        return clips

    def _match_reaction(self, file_mtime: float, history: list) -> dict:
        best = None
        best_diff = 90.0  # Match replays written within 90s of reaction peak
        for h in history:
            try:
                dt = datetime.fromisoformat(h.get("created_at", ""))
                diff = abs(file_mtime - dt.timestamp())
                if diff <= best_diff:
                    best_diff = diff
                    best = h
            except Exception:
                continue
        return best

    def _try_auto_rename(self, fpath: str, mtime: float, matched: dict) -> str:
        try:
            ext = os.path.splitext(fpath)[1]
            stamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d_%H-%M-%S")
            icon = matched.get("reaction_icon", "")
            slug = matched.get("reaction_slug", "Highlight")
            new_name = f"{stamp}_{icon}_{slug}{ext}" if icon else f"{stamp}_{slug}{ext}"
            new_path = os.path.join(os.path.dirname(fpath), new_name)
            if new_path != fpath and not os.path.exists(new_path):
                os.rename(fpath, new_path)
                log_debug("CLIPVAULT", f"Auto-tagged replay: {os.path.basename(fpath)} -> {new_name}")
                return new_path
        except Exception as e:
            log_debug("CLIPVAULT", f"Could not auto-rename replay '{fpath}': {e}")
        return ""

    # ------------------ Video Editor Export Assistant ------------------

    @staticmethod
    def export_youtube_chapters(entries: list, output_path: str) -> int:
        lines = ["00:00 Intro / Stream Start"]
        ordered = sorted(entries, key=lambda e: int(e.get("position_seconds", 0)))
        for e in ordered:
            ts = _seconds_to_yt(int(e.get("position_seconds", 0)))
            icon = e.get("reaction_icon", "💬")
            label = e.get("reaction_label", "Highlight")
            lines.append(f"{ts} {icon} {label}")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return len(ordered)

    @staticmethod
    def export_edl_markers(entries: list, output_path: str, fps: int = 60) -> int:
        ordered = sorted(entries, key=lambda e: int(e.get("position_seconds", 0)))
        lines = [
            "TITLE: Streamer Calyx Auto-Clip Markers",
            "FCM: NON-DROP FRAME",
            "",
        ]
        for idx, e in enumerate(ordered, start=1):
            pos = int(e.get("position_seconds", 0))
            tc_in = _seconds_to_timecode(pos, fps=fps)
            tc_out = _seconds_to_timecode(pos + 1, fps=fps)
            icon = e.get("reaction_icon", "")
            label = e.get("reaction_label", "Highlight")
            lines.append(f"{idx:03d}  001      V     C        {tc_in} {tc_out} {tc_in} {tc_out}")
            lines.append(f"* FROM CLIP NAME: {icon} {label} |ResolveColor:Purple|")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return len(ordered)

    @staticmethod
    def export_csv_markers(entries: list, output_path: str, fps: int = 60) -> int:
        ordered = sorted(entries, key=lambda e: int(e.get("position_seconds", 0)))
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "Timecode", "Seconds", "Reaction", "Icon", "Level", "F0_Hz", "Kind"])
            for idx, e in enumerate(ordered, start=1):
                pos = int(e.get("position_seconds", 0))
                writer.writerow([
                    idx,
                    _seconds_to_timecode(pos, fps=fps),
                    pos,
                    e.get("reaction_label", "Highlight"),
                    e.get("reaction_icon", ""),
                    e.get("level", 0.0),
                    e.get("f0_hz", 0.0),
                    e.get("kind", "primary"),
                ])
        return len(ordered)


class ClipPreviewWidget(QWidget):
    """Lightweight embedded video preview player with timeline scrubber."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path = ""
        self._is_seeking = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if HAS_MULTIMEDIA_VIDEO:
            self.video_widget = QVideoWidget()
            self.video_widget.setMinimumHeight(180)
            self.video_widget.setStyleSheet("background-color: #0b0b0e; border: 1px solid #333; border-radius: 6px;")
            layout.addWidget(self.video_widget)

            self.audio_output = QAudioOutput(self)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio_output)
            self.player.setVideoOutput(self.video_widget)
            self.player.positionChanged.connect(self._on_pos_changed)
            self.player.durationChanged.connect(self._on_dur_changed)
            self.player.playbackStateChanged.connect(self._on_state_changed)
        else:
            self.player = None
            lbl_fb = QLabel("Embedded video preview unavailable; use 'Open External' to play clips.")
            lbl_fb.setStyleSheet("color: #aaa; padding: 16px; background-color: #141418; border-radius: 6px;")
            lbl_fb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl_fb)

        ctrl = QHBoxLayout()
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.btn_play)

        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderPressed.connect(lambda: setattr(self, "_is_seeking", True))
        self.scrubber.sliderReleased.connect(self._on_seek_released)
        ctrl.addWidget(self.scrubber, 1)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("color: #aaa; font-family: monospace; font-size: 11px;")
        ctrl.addWidget(self.lbl_time)

        self.btn_open_ext = QPushButton("📂 Open")
        self.btn_open_ext.setEnabled(False)
        self.btn_open_ext.clicked.connect(self._open_external)
        ctrl.addWidget(self.btn_open_ext)

        layout.addLayout(ctrl)

    def load_clip(self, path: str):
        self._current_path = path or ""
        valid = bool(path and os.path.isfile(path))
        self.btn_open_ext.setEnabled(valid)
        self.btn_play.setEnabled(valid and self.player is not None)
        if self.player and valid:
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.pause()
            self.btn_play.setText("▶ Play")
        elif self.player:
            self.player.stop()
            self.lbl_time.setText("00:00 / 00:00")

    def _toggle_play(self):
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸ Pause")
        else:
            self.btn_play.setText("▶ Play")

    def _on_pos_changed(self, pos_ms: int):
        if not self._is_seeking:
            self.scrubber.setValue(pos_ms)
        dur_ms = self.player.duration() if self.player else 0
        self.lbl_time.setText(f"{_seconds_to_yt(pos_ms // 1000)} / {_seconds_to_yt(dur_ms // 1000)}")

    def _on_dur_changed(self, dur_ms: int):
        self.scrubber.setRange(0, max(0, dur_ms))

    def _on_seek_released(self):
        self._is_seeking = False
        if self.player:
            self.player.setPosition(self.scrubber.value())

    def _open_external(self):
        if self._current_path and os.path.exists(self._current_path):
            try:
                os.startfile(self._current_path)
            except Exception as e:
                log_debug("CLIPVAULT", f"Error opening clip externally: {e}")
