"""
Streamer Calyx - Phase 12 LAN Low-Latency Video Feed Bridge
Streams lightweight JPEG frames over QWebSocket (port 59652) at configurable
FPS throttle (1, 5, 10, or 15 FPS) from the Streamer rig to Director panels.
"""

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QBuffer, QIODevice, QByteArray, QUrl, Qt
from PyQt6.QtGui import QGuiApplication, QPixmap
from PyQt6.QtNetwork import QHostAddress
from PyQt6.QtWebSockets import QWebSocketServer, QWebSocket

try:
    from debug_logger import log_debug
except ImportError:
    def log_debug(tag, msg):
        print(f"[{tag}] {msg}")


LAN_VIDEO_PORT = 59652


class LANVideoServer(QObject):
    """Host-side LAN WebSocket video preview streamer with FPS throttle."""

    client_count_changed = pyqtSignal(int)

    def __init__(self, port: int = LAN_VIDEO_PORT, fps: int = 5, monitor_index: int = 0, parent=None):
        super().__init__(parent)
        self.port = int(port)
        self.fps = self._clamp_fps(fps)
        self.monitor_index = int(monitor_index)
        self.enabled = False
        self._server = QWebSocketServer("CalyxLANVideo", QWebSocketServer.SslMode.NonSecureMode, self)
        self._clients = []
        self._capture_timer = QTimer(self)
        self._capture_timer.timeout.connect(self._capture_and_broadcast)
        self._server.newConnection.connect(self._on_new_connection)

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

    def start(self) -> bool:
        if self.enabled:
            return True
        if self._server.listen(QHostAddress.SpecialAddress.Any, self.port):
            self.enabled = True
            self.set_fps(self.fps)
            self._capture_timer.start()
            log_debug("LAN_VIDEO", f"LAN Video Server listening on port {self.port} ({self.fps} FPS)")
            return True
        log_debug("LAN_VIDEO_ERR", f"Failed to listen on port {self.port}: {self._server.errorString()}")
        return False

    def stop(self):
        self.enabled = False
        self._capture_timer.stop()
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

    def _capture_and_broadcast(self):
        if not self.enabled or not self._clients:
            return
        screens = QGuiApplication.screens()
        if not screens:
            return
        scr = screens[self.monitor_index] if 0 <= self.monitor_index < len(screens) else screens[0]
        pix = scr.grabWindow(0)
        if pix.isNull():
            return
        scaled = pix.scaled(480, 270, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buf, "JPG", 62)
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
