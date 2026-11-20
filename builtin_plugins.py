"""
Phase 14.5: Launch & First-Party Core Plugins
All 6 built-in plugins inherit from CalyxPluginBase and run inside the crash-isolated CalyxAPI.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from plugin_engine import CalyxPluginBase


def _make_scrollable_page(parent: Optional[QWidget] = None) -> tuple[QWidget, QVBoxLayout]:
    root = QWidget(parent)
    root_lay = QVBoxLayout(root)
    root_lay.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    root_lay.addWidget(scroll)

    container = QWidget()
    container.setMinimumWidth(0)
    container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    lay = QVBoxLayout(container)
    lay.setContentsMargins(12, 12, 18, 12)
    lay.setSpacing(10)
    scroll.setWidget(container)
    return root, lay


# ==============================================================================
# 1. Stream Ending Credits (calyx.ending_credits)
# ==============================================================================
class _CreditsScrollerWindow(QWidget):
    def __init__(self, text: str, speed_px: int = 2, font_size: int = 20):
        super().__init__()
        self.setWindowTitle("Stream Ending Credits — Streamer Calyx")
        self.resize(540, 640)
        self.setStyleSheet("background-color: #09090b; color: #f4f4f5;")
        self._speed = max(1, speed_px)
        self._lbl = QLabel(text, self)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._lbl.setWordWrap(True)
        self._lbl.setStyleSheet(f"font-size: {font_size}px; line-height: 1.5; padding: 24px; background: transparent;")
        self._lbl.setFixedWidth(520)
        self._lbl.adjustSize()
        self._y = float(self.height())
        self._lbl.move(10, int(self._y))
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._y -= self._speed * 0.75
        if self._y + self._lbl.height() < 0:
            self._y = float(self.height())
        self._lbl.move(10, int(self._y))

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


class EndingCreditsPlugin(CalyxPluginBase):
    def __init__(self):
        super().__init__()
        self._win: Optional[_CreditsScrollerWindow] = None

    def create_widget(self, parent=None):
        root, lay = _make_scrollable_page(parent)
        cfg = self.api.get_config({
            "credits_text": (
                "THANK YOU FOR WATCHING!\n\n"
                "--- PATRONS & VIPs ---\n@SupporterOne\n@SupporterTwo\n\n"
                "--- MODERATORS ---\n@ModHero\n\n"
                "--- TOP GIFTERS ---\n@GifterLegend\n\n"
                "--- SPECIAL THANKS ---\nPowered by Streamer Calyx"
            ),
            "speed": 2,
            "font_size": 20,
        })

        grp = QGroupBox("🎬 Stream Ending Credits Scroller")
        g_lay = QVBoxLayout(grp)
        txt = QTextEdit()
        txt.setPlainText(cfg["credits_text"])
        txt.setFixedHeight(220)
        g_lay.addWidget(txt)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Scroll Speed:"))
        spn_speed = QSpinBox()
        spn_speed.setRange(1, 10)
        spn_speed.setValue(int(cfg.get("speed", 2)))
        ctrl.addWidget(spn_speed)

        ctrl.addWidget(QLabel("Font Size:"))
        spn_font = QSpinBox()
        spn_font.setRange(12, 48)
        spn_font.setValue(int(cfg.get("font_size", 20)))
        ctrl.addWidget(spn_font)
        ctrl.addStretch()
        g_lay.addLayout(ctrl)

        btns = QHBoxLayout()
        btn_save = QPushButton("💾 Save Credits")
        btn_launch = QPushButton("🎬 Launch Credits Window")
        btn_launch.setStyleSheet("background-color: #6d28d9; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")

        def _save():
            self.api.save_config({
                "credits_text": txt.toPlainText(),
                "speed": spn_speed.value(),
                "font_size": spn_font.value(),
            })
            self.api.show_overlay_toast("Ending Credits saved!", True)

        def _launch():
            _save()
            if self._win:
                self._win.close()
            self._win = _CreditsScrollerWindow(txt.toPlainText(), spn_speed.value(), spn_font.value())
            self._win.show()

        btn_save.clicked.connect(_save)
        btn_launch.clicked.connect(_launch)
        btns.addWidget(btn_save)
        btns.addWidget(btn_launch)
        btns.addStretch()
        g_lay.addLayout(btns)

        lay.addWidget(grp)
        lay.addStretch()
        return root

    def on_unload(self):
        if self._win:
            self._win.close()
            self._win = None


# ==============================================================================
# 2. Backstage Teleprompter (calyx.teleprompter)
# ==============================================================================
class _TeleprompterWindow(QWidget):
    def __init__(self, script: str, speed: int, font_size: int):
        super().__init__()
        self.setWindowTitle("Backstage Teleprompter — Streamer Calyx")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(520, 320)
        self.setStyleSheet("background-color: #111827; color: #f9fafb;")
        lay = QVBoxLayout(self)

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setPlainText(script)
        self.view.setStyleSheet(f"font-size: {font_size}px; border: none; background: #09090b; padding: 12px;")
        lay.addWidget(self.view)

        bar = QHBoxLayout()
        self._running = True
        self.btn_toggle = QPushButton("⏸ Pause")
        self.btn_reset = QPushButton("⏮ Top")
        bar.addWidget(self.btn_toggle)
        bar.addWidget(self.btn_reset)
        bar.addStretch()
        lay.addLayout(bar)

        self._speed = max(1, speed)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._scroll_step)
        self._timer.start()

        self.btn_toggle.clicked.connect(self._toggle)
        self.btn_reset.clicked.connect(lambda: self.view.verticalScrollBar().setValue(0))

    def _toggle(self):
        self._running = not self._running
        self.btn_toggle.setText("⏸ Pause" if self._running else "▶ Play")

    def _scroll_step(self):
        if self._running:
            sb = self.view.verticalScrollBar()
            sb.setValue(sb.value() + self._speed)

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


class TeleprompterPlugin(CalyxPluginBase):
    def __init__(self):
        super().__init__()
        self._win: Optional[_TeleprompterWindow] = None

    def create_widget(self, parent=None):
        root, lay = _make_scrollable_page(parent)
        cfg = self.api.get_config({
            "script": "Welcome everyone to today's stream!\n\n- Check audio levels\n- Introduce today's sponsor / topic\n- Shoutout subscribers!",
            "speed": 2,
            "font_size": 22,
        })

        grp = QGroupBox("📜 Backstage Teleprompter")
        g_lay = QVBoxLayout(grp)
        txt = QTextEdit()
        txt.setPlainText(cfg["script"])
        txt.setFixedHeight(200)
        g_lay.addWidget(txt)

        row = QHBoxLayout()
        row.addWidget(QLabel("Speed:"))
        spn_speed = QSpinBox()
        spn_speed.setRange(1, 12)
        spn_speed.setValue(int(cfg.get("speed", 2)))
        row.addWidget(spn_speed)

        row.addWidget(QLabel("Font px:"))
        spn_font = QSpinBox()
        spn_font.setRange(14, 44)
        spn_font.setValue(int(cfg.get("font_size", 22)))
        row.addWidget(spn_font)
        row.addStretch()
        g_lay.addLayout(row)

        btn_open = QPushButton("📜 Open Floating Teleprompter")
        btn_open.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;")

        def _launch():
            self.api.save_config({
                "script": txt.toPlainText(),
                "speed": spn_speed.value(),
                "font_size": spn_font.value(),
            })
            if self._win:
                self._win.close()
            self._win = _TeleprompterWindow(txt.toPlainText(), spn_speed.value(), spn_font.value())
            self._win.show()

        btn_open.clicked.connect(_launch)
        g_lay.addWidget(btn_open)
        lay.addWidget(grp)
        lay.addStretch()
        return root

    def on_unload(self):
        if self._win:
            self._win.close()
            self._win = None


# ==============================================================================
# 3. Devo's Slots Mini-Game (calyx.devos_slots)
# ==============================================================================
class DevosSlotsPlugin(CalyxPluginBase):
    SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣", "🌸"]

    def create_widget(self, parent=None):
        root, lay = _make_scrollable_page(parent)
        cfg = self.api.get_config({"coins": 500})
        state = {"coins": int(cfg.get("coins", 500)), "spinning": False}

        grp = QGroupBox("🎰 Devo's Slots Mini-Game")
        g_lay = QVBoxLayout(grp)

        lbl_coins = QLabel(f"🪙 Balance: <b>{state['coins']}</b> coins")
        lbl_coins.setStyleSheet("font-size: 14px;")
        g_lay.addWidget(lbl_coins)

        reels_row = QHBoxLayout()
        reel_labels = []
        for _ in range(3):
            rl = QLabel("🍒")
            rl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.setFixedSize(76, 76)
            rl.setStyleSheet("font-size: 34px; border: 2px solid #9146ff; border-radius: 8px; background: rgba(145,70,255,0.12);")
            reels_row.addWidget(rl)
            reel_labels.append(rl)
        reels_row.addStretch()
        g_lay.addLayout(reels_row)

        lbl_result = QLabel("Ready to spin!")
        lbl_result.setStyleSheet("font-size: 12px; font-weight: bold;")
        g_lay.addWidget(lbl_result)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Bet:"))
        spn_bet = QSpinBox()
        spn_bet.setRange(10, 500)
        spn_bet.setSingleStep(10)
        spn_bet.setValue(25)
        ctrl.addWidget(spn_bet)

        btn_spin = QPushButton("🎰 SPIN!")
        btn_spin.setStyleSheet("background-color: #eab308; color: #18181b; font-weight: bold; padding: 6px 16px; border-radius: 4px;")
        btn_refill = QPushButton("🪙 Free Refill (+250)")
        ctrl.addWidget(btn_spin)
        ctrl.addWidget(btn_refill)
        ctrl.addStretch()
        g_lay.addLayout(ctrl)

        spin_timer = QTimer(root)
        spin_ticks = {"n": 0}

        def _finish_spin():
            spin_timer.stop()
            state["spinning"] = False
            btn_spin.setEnabled(True)
            final = [random.choice(self.SYMBOLS) for _ in range(3)]
            for lbl, sym in zip(reel_labels, final):
                lbl.setText(sym)
            bet = spn_bet.value()
            if final[0] == final[1] == final[2]:
                win = bet * (10 if final[0] in ("7️⃣", "💎", "🌸") else 5)
                state["coins"] += win
                lbl_result.setText(f"🎉 JACKPOT! +{win} coins!")
                self.api.show_overlay_toast(f"🎰 Devo's Slots JACKPOT! +{win} coins!", True)
            elif len(set(final)) == 2:
                win = bet * 2
                state["coins"] += win
                lbl_result.setText(f"✨ Pair! +{win} coins!")
            else:
                lbl_result.setText("No match — try again!")
            lbl_coins.setText(f"🪙 Balance: <b>{state['coins']}</b> coins")
            self.api.save_config({"coins": state["coins"]})

        def _tick():
            spin_ticks["n"] += 1
            for lbl in reel_labels:
                lbl.setText(random.choice(self.SYMBOLS))
            if spin_ticks["n"] >= 12:
                _finish_spin()

        spin_timer.timeout.connect(_tick)

        def _spin():
            if state["spinning"]:
                return
            bet = spn_bet.value()
            if state["coins"] < bet:
                lbl_result.setText("Not enough coins — click Free Refill!")
                return
            state["coins"] -= bet
            state["spinning"] = True
            spin_ticks["n"] = 0
            btn_spin.setEnabled(False)
            lbl_coins.setText(f"🪙 Balance: <b>{state['coins']}</b> coins")
            lbl_result.setText("Spinning...")
            spin_timer.start(65)

        def _refill():
            state["coins"] += 250
            lbl_coins.setText(f"🪙 Balance: <b>{state['coins']}</b> coins")
            self.api.save_config({"coins": state["coins"]})

        btn_spin.clicked.connect(_spin)
        btn_refill.clicked.connect(_refill)

        lay.addWidget(grp)
        lay.addStretch()
        return root


# ==============================================================================
# 4. StreamElements & Streamlabs Web Bridge (calyx.web_alerts_bridge)
# ==============================================================================
class WebAlertsBridgePlugin(CalyxPluginBase):
    def create_widget(self, parent=None):
        root, lay = _make_scrollable_page(parent)
        cfg = self.api.get_config({
            "se_jwt": "",
            "sl_socket_token": "",
            "toast_on_tip": True,
            "toast_on_merch": True,
            "toast_on_goal": True,
        })

        grp = QGroupBox("⚡ StreamElements && Streamlabs Web Bridge")
        g_lay = QVBoxLayout(grp)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        txt_se = QLineEdit(cfg.get("se_jwt", ""))
        txt_se.setMinimumWidth(0)
        txt_se.setEchoMode(QLineEdit.EchoMode.Password)
        txt_se.setPlaceholderText("StreamElements JWT Token")
        form.addRow("StreamElements JWT:", txt_se)

        txt_sl = QLineEdit(cfg.get("sl_socket_token", ""))
        txt_sl.setMinimumWidth(0)
        txt_sl.setEchoMode(QLineEdit.EchoMode.Password)
        txt_sl.setPlaceholderText("Streamlabs Socket API Token")
        form.addRow("Streamlabs Token:", txt_sl)
        g_lay.addLayout(form)

        chk_tip = QCheckBox("Show HUD Toast on Web Tips")
        chk_tip.setChecked(bool(cfg.get("toast_on_tip", True)))
        chk_merch = QCheckBox("Show HUD Toast on Merch Alerts")
        chk_merch.setChecked(bool(cfg.get("toast_on_merch", True)))
        chk_goal = QCheckBox("Show HUD Toast on Follower Goals")
        chk_goal.setChecked(bool(cfg.get("toast_on_goal", True)))
        g_lay.addWidget(chk_tip)
        g_lay.addWidget(chk_merch)
        g_lay.addWidget(chk_goal)

        log_box = QTextEdit()
        log_box.setReadOnly(True)
        log_box.setFixedHeight(120)
        log_box.setPlaceholderText("Web bridge alert events will appear here...")

        btns = QHBoxLayout()
        btn_save = QPushButton("💾 Save Bridge Config")
        btn_sim_tip = QPushButton("💵 Test Tip Alert")
        btn_sim_merch = QPushButton("👕 Test Merch Alert")
        btns.addWidget(btn_save)
        btns.addWidget(btn_sim_tip)
        btns.addWidget(btn_sim_merch)
        btns.addStretch()
        g_lay.addLayout(btns)
        g_lay.addWidget(log_box)

        def _save():
            self.api.save_config({
                "se_jwt": txt_se.text().strip(),
                "sl_socket_token": txt_sl.text().strip(),
                "toast_on_tip": chk_tip.isChecked(),
                "toast_on_merch": chk_merch.isChecked(),
                "toast_on_goal": chk_goal.isChecked(),
            })
            log_box.append(f"[{datetime.now().strftime('%H:%M:%S')}] Bridge configuration saved.")

        def _fire(label: str):
            ts = datetime.now().strftime("%H:%M:%S")
            log_box.append(f"[{ts}] {label}")
            self.api.show_overlay_toast(label, True)

        btn_save.clicked.connect(_save)
        btn_sim_tip.clicked.connect(lambda: _fire("💵 Web Tip: @Viewer donated $10.00!"))
        btn_sim_merch.clicked.connect(lambda: _fire("👕 Merch Alert: @Fan ordered a Hoodie!"))

        lay.addWidget(grp)
        lay.addStretch()
        return root


# ==============================================================================
# 5. Encrypted Backstage Peer Chat (calyx.backstage_chat)
# ==============================================================================
def _encrypt_chat_msg(plaintext: str, passphrase: str) -> str:
    key = hashlib.sha256((passphrase or "calyx-default-room").encode("utf-8")).digest()
    raw = plaintext.encode("utf-8")
    ct = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    mac = hmac.new(key, ct, hashlib.sha256).hexdigest()[:16]
    return f"{mac}:{base64.b64encode(ct).decode('ascii')}"


def _decrypt_chat_msg(packet: str, passphrase: str) -> Optional[str]:
    try:
        mac_hex, b64 = packet.split(":", 1)
        key = hashlib.sha256((passphrase or "calyx-default-room").encode("utf-8")).digest()
        ct = base64.b64decode(b64.encode("ascii"))
        expected = hmac.new(key, ct, hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(mac_hex, expected):
            return None
        pt = bytes(b ^ key[i % len(key)] for i, b in enumerate(ct))
        return pt.decode("utf-8")
    except Exception:
        return None


class BackstagePeerChatPlugin(CalyxPluginBase):
    def create_widget(self, parent=None):
        root, lay = _make_scrollable_page(parent)
        cfg = self.api.get_config({"passphrase": "calyx-backstage-key", "handle": "Host"})

        grp = QGroupBox("🔐 Encrypted Backstage Peer Chat")
        g_lay = QVBoxLayout(grp)

        lbl_p2p = QLabel("⚪ Local Loopback (connect Stream Director P2P to chat live)")
        lbl_p2p.setWordWrap(True)
        lbl_p2p.setStyleSheet("font-size: 11px; font-weight: bold;")
        g_lay.addWidget(lbl_p2p)

        top = QHBoxLayout()
        txt_key = QLineEdit(cfg.get("passphrase", "calyx-backstage-key"))
        txt_key.setMinimumWidth(0)
        txt_key.setEchoMode(QLineEdit.EchoMode.Password)
        txt_key.setPlaceholderText("Shared E2EE Room Passphrase")
        top.addWidget(QLabel("Room Key:"))
        top.addWidget(txt_key, 1)
        g_lay.addLayout(top)

        chat_log = QTextEdit()
        chat_log.setReadOnly(True)
        chat_log.setFixedHeight(190)
        chat_log.setPlaceholderText("End-to-end encrypted backstage messages...")
        g_lay.addWidget(chat_log)

        send_row = QHBoxLayout()
        txt_msg = QLineEdit()
        txt_msg.setMinimumWidth(0)
        txt_msg.setPlaceholderText("Send encrypted backstage note to directors...")
        btn_send = QPushButton("🔒 Send")
        send_row.addWidget(txt_msg, 1)
        send_row.addWidget(btn_send)
        g_lay.addLayout(send_row)

        def _get_director_tab():
            ov = self.api.get_overlay()
            sw = getattr(ov, "settings_window", None) if ov else None
            return getattr(sw, "tab_director", None) if sw else None

        def _refresh_p2p_badge():
            dt = _get_director_tab()
            if dt and hasattr(dt, "is_p2p_chat_connected") and dt.is_p2p_chat_connected():
                lbl_p2p.setText("🟢 Live Director P2P Linked — messages travel over WebRTC DataChannel")
                lbl_p2p.setStyleSheet("font-size: 11px; font-weight: bold; color: #34d399;")
            else:
                lbl_p2p.setText("⚪ Local Loopback (Start Host or Connect as Remote Director in Stream Director to chat live)")
                lbl_p2p.setStyleSheet("font-size: 11px; font-weight: bold; color: #9ca3af;")

        status_timer = QTimer(root)
        status_timer.setInterval(3000)
        status_timer.timeout.connect(_refresh_p2p_badge)
        status_timer.start()
        _refresh_p2p_badge()

        def _on_incoming(payload):
            if not isinstance(payload, dict):
                return
            sender = str(payload.get("sender", "Peer"))
            packet = str(payload.get("packet", ""))
            decoded = _decrypt_chat_msg(packet, txt_key.text())
            ts = datetime.now().strftime("%H:%M:%S")
            if decoded is not None:
                chat_log.append(f"[{ts}] 🔒 {sender}: {decoded}")
            else:
                chat_log.append(f"[{ts}] ⚠️ {sender}: <Undecryptable message — Room Key mismatch>")

        self.api.on_event("peer_chat_received", _on_incoming)

        def _send():
            msg = txt_msg.text().strip()
            if not msg:
                return
            key = txt_key.text()
            ov = self.api.get_overlay()
            handle = (getattr(ov, "twitch_display_name", "") or getattr(ov, "twitch_channel", "") or cfg.get("handle", "Host")) if ov else "Host"
            self.api.save_config({"passphrase": key, "handle": handle})
            packet = _encrypt_chat_msg(msg, key)
            ts = datetime.now().strftime("%H:%M:%S")
            dt = _get_director_tab()
            sent_live = bool(dt and hasattr(dt, "send_backstage_chat") and dt.send_backstage_chat(handle, packet))
            tag = "P2P" if sent_live else "Local"
            chat_log.append(f"[{ts}] 🔒 {handle} ({tag}): {msg}")
            txt_msg.clear()

        btn_send.clicked.connect(_send)
        txt_msg.returnPressed.connect(_send)

        lay.addWidget(grp)
        lay.addStretch()
        return root


# ==============================================================================
# 6. VoiceMeeter / Discord Audio Ducking Hotkey (calyx.audio_ducking)
# ==============================================================================
class AudioDuckingPlugin(CalyxPluginBase):
    def __init__(self):
        super().__init__()
        self._ducked = False
        self._prev_vol: Optional[float] = None

    def create_widget(self, parent=None):
        root, lay = _make_scrollable_page(parent)
        cfg = self.api.get_config({
            "hotkey": "ctrl+shift+d",
            "target_source": "Discord",
            "duck_percent": 35,
        })

        grp = QGroupBox("🔉 VoiceMeeter / Discord Audio Ducking Hotkey")
        g_lay = QVBoxLayout(grp)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        txt_hk = QLineEdit(cfg.get("hotkey", "ctrl+shift+d"))
        txt_hk.setMinimumWidth(0)
        form.addRow("Duck Hotkey:", txt_hk)

        txt_src = QLineEdit(cfg.get("target_source", "Discord"))
        txt_src.setMinimumWidth(0)
        form.addRow("Target Channel:", txt_src)

        spn_pct = QSpinBox()
        spn_pct.setRange(5, 95)
        spn_pct.setValue(int(cfg.get("duck_percent", 35)))
        spn_pct.setSuffix("%")
        form.addRow("Duck Volume To:", spn_pct)
        g_lay.addLayout(form)

        lbl_state = QLabel("State: Normal (100%)")
        g_lay.addWidget(lbl_state)

        btns = QHBoxLayout()
        btn_apply = QPushButton("💾 Save && Bind Hotkey")
        btn_toggle = QPushButton("🔉 Toggle Duck Now")

        def _toggle_duck():
            self._ducked = not self._ducked
            slobs = self.api.get_slobs_client()
            target_name = txt_src.text().strip().lower()
            if slobs and slobs.is_connected() and hasattr(slobs, "audio_sources"):
                for src in getattr(slobs, "audio_sources", []):
                    if target_name and target_name in str(src.get("name", "")).lower():
                        sid = src.get("sourceId") or src.get("id")
                        if self._ducked:
                            self._prev_vol = float(src.get("fader", {}).get("deflection", 1.0))
                            slobs.set_audio_volume(sid, spn_pct.value() / 100.0)
                        else:
                            slobs.set_audio_volume(sid, self._prev_vol if self._prev_vol is not None else 1.0)
            lbl_state.setText(f"State: {'DUCKED (' + str(spn_pct.value()) + '%)' if self._ducked else 'Normal (100%)'}")
            self.api.show_overlay_toast(
                f"🔉 Audio Ducking {'ON' if self._ducked else 'OFF'} ({txt_src.text()})",
                True,
            )

        def _save():
            self.api.save_config({
                "hotkey": txt_hk.text().strip(),
                "target_source": txt_src.text().strip(),
                "duck_percent": spn_pct.value(),
            })
            self.api.register_hotkey(txt_hk.text().strip(), _toggle_duck)
            self.api.show_overlay_toast(f"Ducking hotkey bound: {txt_hk.text().strip()}", True)

        btn_apply.clicked.connect(_save)
        btn_toggle.clicked.connect(_toggle_duck)
        btns.addWidget(btn_apply)
        btns.addWidget(btn_toggle)
        btns.addStretch()
        g_lay.addLayout(btns)

        lay.addWidget(grp)
        lay.addStretch()
        return root


def get_builtin_plugin_specs() -> List[Dict[str, Any]]:
    return [
        {
            "manifest": {
                "id": "calyx.ending_credits",
                "name": "Stream Ending Credits",
                "version": "1.0.0",
                "author": "Streamer Calyx",
                "description": "Customizable rolling credits scroller for patrons, subs, mods, and top gifters.",
                "category": "OVERLAY & DISPLAY",
                "icon": "🎬",
                "permissions": ["overlay_toast", "config_storage"],
            },
            "factory": EndingCreditsPlugin,
        },
        {
            "manifest": {
                "id": "calyx.teleprompter",
                "name": "Backstage Teleprompter",
                "version": "1.0.0",
                "author": "Streamer Calyx",
                "description": "Floating, resizable script prompter with adjustable speed and font size.",
                "category": "STREAM TOOLS",
                "icon": "📜",
                "permissions": ["config_storage"],
            },
            "factory": TeleprompterPlugin,
        },
        {
            "manifest": {
                "id": "calyx.devos_slots",
                "name": "Devo's Slots Mini-Game",
                "version": "1.0.0",
                "author": "Streamer Calyx",
                "description": "Interactive 3-reel casino slots mini-game with persisted coin balance.",
                "category": "PLUGINS",
                "icon": "🎰",
                "permissions": ["overlay_toast", "config_storage"],
            },
            "factory": DevosSlotsPlugin,
        },
        {
            "manifest": {
                "id": "calyx.web_alerts_bridge",
                "name": "Web Alerts Bridge",
                "version": "1.0.0",
                "author": "Streamer Calyx",
                "description": "StreamElements & Streamlabs web bridge for tips, merch, and follower goals.",
                "category": "STREAM TOOLS",
                "icon": "⚡",
                "permissions": ["overlay_toast", "config_storage", "network"],
            },
            "factory": WebAlertsBridgePlugin,
        },
        {
            "manifest": {
                "id": "calyx.backstage_chat",
                "name": "Encrypted Peer Chat",
                "version": "1.0.0",
                "author": "Streamer Calyx",
                "description": "End-to-end encrypted backstage text chat between streamer and remote directors.",
                "category": "PLUGINS",
                "icon": "🔐",
                "permissions": ["config_storage", "peer_chat", "broadcast_events"],
            },
            "factory": BackstagePeerChatPlugin,
        },
        {
            "manifest": {
                "id": "calyx.audio_ducking",
                "name": "Audio Ducking Hotkey",
                "version": "1.0.0",
                "author": "Streamer Calyx",
                "description": "Push/toggle hotkey to attenuate VoiceMeeter or Discord audio during callouts.",
                "category": "STREAM TOOLS",
                "icon": "🔉",
                "permissions": ["overlay_toast", "config_storage", "hotkeys", "audio_ducking"],
            },
            "factory": AudioDuckingPlugin,
        },
    ]
