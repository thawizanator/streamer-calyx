"""
Streamer Calyx - Phase 12 LAN Low-Latency Video Feed Bridge
Streams lightweight JPEG frames over QWebSocket (port 59652) at configurable
FPS throttle (1, 5, 10, or 15 FPS) from SLOBS/OBS Virtual Camera, SLOBS Window,
or Target Monitor to Director panels.
"""

import sys
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QBuffer, QIODevice, QByteArray, QUrl, Qt
from PyQt6.QtGui import QGuiApplication, QPixmap, QImage
from PyQt6.QtNetwork import QHostAddress
from PyQt6.QtWebSockets import QWebSocketServer, QWebSocket

try:
    from PyQt6.QtMultimedia import QMediaDevices, QCamera, QMediaCaptureSession, QVideoSink
    HAS_QCAMERA = True
except Exception:
    HAS_QCAMERA = False

try:
    from debug_logger import log_debug
except ImportError:
    def log_debug(tag, msg):
        print(f"[{tag}] {msg}")


LAN_VIDEO_PORT = 59652


def _find_slobs_obs_hwnd() -> int:
    """Finds the Streamlabs Desktop or OBS Studio main window handle on Windows."""
    if sys.platform != "win32":
        return 0
    try:
        import win32gui
        found = []

        def _enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return True
            title = (win32gui.GetWindowText(hwnd) or "").strip()
            low = title.lower()
            if not title:
                return True
            if ("streamlabs" in low and "calyx" not in low) or low.startswith("obs ") or "obs studio" in low:
                rect = win32gui.GetWindowRect(hwnd)
                if (rect[2] - rect[0]) >= 300 and (rect[3] - rect[1]) >= 200:
                    found.append((hwnd, title))
            return True

        win32gui.EnumWindows(_enum_cb, None)
        return found[0][0] if found else 0
    except Exception:
        return 0


class LANVideoServer(QObject):
    """Host-side LAN WebSocket video preview streamer with FPS throttle & SLOBS scene capture."""

    client_count_changed = pyqtSignal(int)

    def __init__(self, port: int = LAN_VIDEO_PORT, fps: int = 5, monitor_index: int = 0,
                 capture_source: str = "auto", parent=None):
        super().__init__(parent)
        self.port = int(port)
        self.fps = self._clamp_fps(fps)
        self.monitor_index = int(monitor_index)
        self.capture_source = capture_source or "auto"
        self.enabled = False
        self._server = QWebSocketServer("CalyxLANVideo", QWebSocketServer.SslMode.NonSecureMode, self)
        self._clients = []
        self._capture_timer = QTimer(self)
        self._capture_timer.timeout.connect(self._capture_and_broadcast)
        self._server.newConnection.connect(self._on_new_connection)

        # Optional Virtual Camera state
        self._camera = None
        self._capture_session = None
        self._video_sink = None
        self._latest_cam_image = None

    @staticmethod
    def _clamp_fps(fps: int) -> int:
        allowed = (1, 5, 10, 15)
        fps = int(fps)
        return min(allowed, key=lambda x: abs(x - fps))

    def set_fps(self, fps: int):
        self.fps = self._clamp_fps(fps)
        self._capture_timer.setInterval(max(66, int(1000 / max(1, self.fps))))
        log_debug("LAN_VIDEO", f"LAN video preview FPS throttle set to {self.fps} FPS.")

    def set_monitor_index(self, idx: int):
        self.monitor_index = max(0, int(idx))

    def set_capture_source(self, source_mode: str):
        self.capture_source = source_mode or "auto"
        if self.enabled:
            self._teardown_virtual_cam()
            if self.capture_source in ("auto", "virtual_cam"):
                self._try_init_virtual_cam()

    def _try_init_virtual_cam(self) -> bool:
        if not HAS_QCAMERA:
            return False
        try:
            cams = QMediaDevices.videoInputs()
            vcam = None
            for c in cams:
                desc = (c.description() or "").lower()
                if any(k in desc for k in ("streamlabs", "obs virtual", "virtual camera", "virtual webcam")):
                    vcam = c
                    break
            if not vcam:
                return False
            self._camera = QCamera(vcam, self)
            self._video_sink = QVideoSink(self)
            self._video_sink.videoFrameChanged.connect(self._on_vcam_frame)
            self._capture_session = QMediaCaptureSession(self)
            self._capture_session.setCamera(self._camera)
            self._capture_session.setVideoSink(self._video_sink)
            self._camera.start()
            log_debug("LAN_VIDEO", f"Attached to Virtual Camera: '{vcam.description()}'")
            return True
        except Exception as e:
            log_debug("LAN_VIDEO", f"Virtual camera init skipped: {e}")
            self._teardown_virtual_cam()
            return False

    def _teardown_virtual_cam(self):
        if self._camera:
            try:
                self._camera.stop()
            except Exception:
                pass
        self._camera = None
        self._capture_session = None
        self._video_sink = None
        self._latest_cam_image = None

    def _on_vcam_frame(self, frame):
        try:
            img = frame.toImage()
            if not img.isNull():
                self._latest_cam_image = img
        except Exception:
            pass

    def start(self) -> bool:
        if self.enabled:
            return True
        if self._server.listen(QHostAddress.SpecialAddress.Any, self.port):
            self.enabled = True
            self.set_fps(self.fps)
            if self.capture_source in ("auto", "virtual_cam"):
                self._try_init_virtual_cam()
            self._capture_timer.start()
            log_debug("LAN_VIDEO", f"LAN Video Server listening on port {self.port} ({self.fps} FPS, source={self.capture_source})")
            return True
        log_debug("LAN_VIDEO_ERR", f"Failed to listen on port {self.port}: {self._server.errorString()}")
        return False

    def stop(self):
        self.enabled = False
        self._capture_timer.stop()
        self._teardown_virtual_cam()
        for c in list(self._clients):
            try:
                c.close()
            except Exception:
                pass
        self._clients.clear()
        if self._server.isListening():
            self._server.close()
        self.client_count_changed.emit(0)
        log_debug("LAN_VIDEO", "LAN Video Server stopped.")

    def _on_new_connection(self):
        sock = self._server.nextPendingConnection()
        if not sock:
            return
        sock.disconnected.connect(lambda s=sock: self._on_client_disconnected(s))
        self._clients.append(sock)
        self.client_count_changed.emit(len(self._clients))
        log_debug("LAN_VIDEO", f"LAN Video client connected ({len(self._clients)} total)")

    def _on_client_disconnected(self, sock):
        if sock in self._clients:
            self._clients.remove(sock)
        self.client_count_changed.emit(len(self._clients))

    def _grab_frame_pixmap(self) -> QPixmap:
        mode = self.capture_source or "auto"

        # 1. Virtual Camera (direct SLOBS/OBS active scene output)
        if mode in ("auto", "virtual_cam") and isinstance(self._latest_cam_image, QImage) and not self._latest_cam_image.isNull():
            return QPixmap.fromImage(self._latest_cam_image)

        # 2. Streamlabs Desktop / OBS Studio Window
        screens = QGuiApplication.screens()
        if not screens:
            return QPixmap()
        scr = screens[self.monitor_index] if 0 <= self.monitor_index < len(screens) else screens[0]

        if mode in ("auto", "slobs_window"):
            hwnd = _find_slobs_obs_hwnd()
            if hwnd:
                pix = scr.grabWindow(hwnd)
                if not pix.isNull() and not self._is_mostly_black(pix):
                    return pix
                # Electron/Direct3D windows often return black from grabWindow(hwnd);
                # capture the desktop region at the window's screen rect instead.
                rect_pix = self._grab_hwnd_screen_region(hwnd)
                if not rect_pix.isNull():
                    return rect_pix

        # 3. Monitor fallback
        if mode in ("auto", "monitor"):
            return scr.grabWindow(0)

        return QPixmap()

    @staticmethod
    def _is_mostly_black(pix: QPixmap) -> bool:
        img = pix.toImage()
        if img.isNull() or img.width() < 4 or img.height() < 4:
            return True
        w, h = img.width(), img.height()
        for fx in (0.2, 0.5, 0.8):
            for fy in (0.2, 0.5, 0.8):
                c = img.pixelColor(int(w * fx), int(h * fy))
                if (c.red() + c.green() + c.blue()) > 3:
                    return False
        return True

    @staticmethod
    def _grab_hwnd_screen_region(hwnd: int) -> QPixmap:
        if sys.platform != "win32":
            return QPixmap()
        try:
            import win32gui
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            w, h = r - l, b - t
            if w < 100 or h < 100:
                return QPixmap()
            cx, cy = l + w // 2, t + h // 2
            screens = QGuiApplication.screens()
            target_scr = screens[0] if screens else None
            for s in screens:
                if s.geometry().contains(cx, cy):
                    target_scr = s
                    break
            if not target_scr:
                return QPixmap()
            sg = target_scr.geometry()
            return target_scr.grabWindow(0, l - sg.x(), t - sg.y(), w, h)
        except Exception:
            return QPixmap()

    def _capture_and_broadcast(self):
        if not self.enabled or not self._clients:
            return
        pix = self._grab_frame_pixmap()
        if pix.isNull():
            return
        scaled = pix.scaled(640, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buf, "JPG", 68)
        raw = bytes(ba)
        for sock in list(self._clients):
            try:
                sock.sendBinaryMessage(raw)
            except Exception:
                pass


class LANVideoClient(QObject):
    """Director-side LAN WebSocket video preview receiver."""

    frame_received = pyqtSignal(QPixmap)
    connection_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws = QWebSocket()
        self._ws.connected.connect(lambda: self.connection_changed.emit(True))
        self._ws.disconnected.connect(lambda: self.connection_changed.emit(False))
        self._ws.binaryMessageReceived.connect(self._on_binary_frame)
        self._connected_url = ""

    def connect_to_host(self, host: str = "127.0.0.1", port: int = LAN_VIDEO_PORT):
        url = f"ws://{host.strip() or '127.0.0.1'}:{int(port)}"
        self._connected_url = url
        self._ws.open(QUrl(url))

    def disconnect_feed(self):
        self._ws.close()

    def is_connected(self) -> bool:
        return self._ws.state() == self._ws.state().ConnectedState

    def _on_binary_frame(self, data: bytes):
        pix = QPixmap()
        if pix.loadFromData(data, "JPG"):
            self.frame_received.emit(pix)
