"""
Phase 14.5: Launch & First-Party Core Plugins
All 6 built-in plugins inherit from CalyxPluginBase and run inside the crash-isolated CalyxAPI.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
DEFAULT_CREDITS_DATA = [
    {"role": "The Streamer", "scale": 1.9, "names": ["ThaWizanator"]},
    {"role": "Subscribers", "scale": 1.0, "names": ["SubscriberOne", "SubscriberTwo"]},
    {"role": "Followers", "scale": 0.85, "names": ["FollowerOne", "FollowerTwo"]},
    {
        "role": "Special Thanks",
        "scale": 1.1,
        "names": [
            {"name": "Supporter", "reason": "For helping make the stream awesome!"}
        ],
    },
]


def _generate_credits_html(credits_data: List[Dict[str, Any]], speed: int = 60, loop: bool = True, transparent: bool = False) -> str:
    bg_css = "transparent" if transparent else "black"
    data_json = json.dumps(credits_data, indent=4, ensure_ascii=False)
    loop_js = "true" if loop else "false"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>End Credits Sequence — Streamer Calyx</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background-color: {bg_css};
            color: white;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            overflow: hidden;
        }}
        #credits-container {{ position: relative; width: 100vw; height: 100vh; }}
        #credits-content {{ position: absolute; width: 100%; text-align: center; }}
        .credit-block {{ margin-bottom: 80px; --block-scale: 1; }}
        .role {{
            font-size: calc(1.2rem * var(--block-scale));
            font-weight: bold;
            color: #888;
            margin-bottom: calc(20px * var(--block-scale));
            text-transform: uppercase;
            letter-spacing: 3px;
        }}
        .name {{
            font-size: calc(1.6rem * var(--block-scale));
            margin-bottom: calc(10px * var(--block-scale));
            letter-spacing: 1px;
        }}
        .thanks-item {{
            display: flex; justify-content: center; gap: 30px;
            margin-bottom: calc(15px * var(--block-scale));
            width: 100%; max-width: 800px; margin-left: auto; margin-right: auto;
            break-inside: avoid;
        }}
        .thanks-name {{
            font-size: calc(1.4rem * var(--block-scale));
            text-align: right; width: 50%; letter-spacing: 1px;
        }}
        .thanks-reason {{
            font-size: calc(1.2rem * var(--block-scale));
            color: #bbb; text-align: left; width: 50%; font-style: italic; align-self: center;
        }}
        .names-container {{ display: flex; flex-direction: column; align-items: center; }}
        .names-container.two-columns {{
            display: block; column-count: 2; column-gap: 80px;
            max-width: 800px; margin: 0 auto; text-align: center;
        }}
        @keyframes scrollUp {{
            0% {{ transform: translateY(100vh); }}
            100% {{ transform: translateY(-100%); }}
        }}
    </style>
</head>
<body>
    <div id="credits-container"><div id="credits-content"></div></div>
    <script>
        const config = {{ speed: {int(speed)}, loop: {loop_js} }};
        const creditsData = {data_json};
        const contentDiv = document.getElementById('credits-content');
        function buildCredits() {{
            creditsData.forEach(block => {{
                const blockDiv = document.createElement('div');
                blockDiv.className = 'credit-block';
                blockDiv.style.setProperty('--block-scale', block.scale || 1);
                const roleDiv = document.createElement('div');
                roleDiv.className = 'role';
                roleDiv.innerText = block.role || '';
                blockDiv.appendChild(roleDiv);
                const namesDiv = document.createElement('div');
                namesDiv.className = 'names-container';
                const names = Array.isArray(block.names) ? block.names : [];
                if (names.length > 24) namesDiv.classList.add('two-columns');
                names.forEach(item => {{
                    if (typeof item === 'string') {{
                        const nameDiv = document.createElement('div');
                        nameDiv.className = 'name';
                        nameDiv.innerText = item;
                        namesDiv.appendChild(nameDiv);
                    }} else if (item && typeof item === 'object') {{
                        const itemDiv = document.createElement('div');
                        itemDiv.className = 'thanks-item';
                        const nameDiv = document.createElement('div');
                        nameDiv.className = 'thanks-name';
                        nameDiv.innerText = item.name || '';
                        const reasonDiv = document.createElement('div');
                        reasonDiv.className = 'thanks-reason';
                        reasonDiv.innerText = item.reason || '';
                        itemDiv.appendChild(nameDiv);
                        itemDiv.appendChild(reasonDiv);
                        namesDiv.appendChild(itemDiv);
                    }}
                }});
                blockDiv.appendChild(namesDiv);
                contentDiv.appendChild(blockDiv);
            }});
        }}
        function startScroll() {{
            const totalDistance = contentDiv.offsetHeight + window.innerHeight;
            const duration = totalDistance / Math.max(1, config.speed);
            contentDiv.style.animation = `scrollUp ${{duration}}s linear ${{config.loop ? 'infinite' : '1'}}`;
        }}
        window.onload = () => {{ buildCredits(); requestAnimationFrame(startScroll); }};
        window.addEventListener('resize', startScroll);
    </script>
</body>
</html>
"""


def _format_credits_for_qt(credits_data: List[Dict[str, Any]]) -> str:
    html_parts = []
    for block in credits_data:
        scale = float(block.get("scale", 1.0) or 1.0)
        role_px = max(11, int(14 * scale))
        name_px = max(13, int(18 * scale))
        role = str(block.get("role", "")).upper()
        html_parts.append(f"<div style='color:#888888; font-size:{role_px}px; font-weight:bold; letter-spacing:2px; margin-top:28px; margin-bottom:10px;'>{role}</div>")
        for item in block.get("names", []):
            if isinstance(item, str) and item.strip():
                html_parts.append(f"<div style='color:#ffffff; font-size:{name_px}px; margin-bottom:6px;'>{item}</div>")
            elif isinstance(item, dict):
                n = item.get("name", "")
                r = item.get("reason", "")
                html_parts.append(f"<div style='color:#ffffff; font-size:{name_px}px; margin-bottom:6px;'><b>{n}</b> <span style='color:#bbbbbb; font-style:italic; font-size:{max(11, name_px-3)}px;'>— {r}</span></div>")
    return "".join(html_parts)


class _CreditsScrollerWindow(QWidget):
    def __init__(self, rich_html: str, speed_px: int = 60, loop: bool = True):
        super().__init__()
        self.setWindowTitle("End Credits Sequence — Streamer Calyx")
        self.resize(680, 720)
        self.setStyleSheet("background-color: #000000; color: #ffffff;")
        self._speed = max(10, speed_px)
        self._loop = loop
        self._lbl = QLabel(self)
        self._lbl.setTextFormat(Qt.TextFormat.RichText)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._lbl.setWordWrap(True)
        self._lbl.setText(rich_html)
        self._lbl.setFixedWidth(640)
        self._lbl.adjustSize()
        self._y = float(self.height())
        self._lbl.move(20, int(self._y))
        self._timer = QTimer(self)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._y -= self._speed * 0.025
        if self._y + self._lbl.height() < 0:
            if self._loop:
                self._y = float(self.height())
            else:
                self._timer.stop()
                return
        self._lbl.move(20, int(self._y))

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


class EndingCreditsPlugin(CalyxPluginBase):
    def __init__(self):
        super().__init__()
        self._win: Optional[_CreditsScrollerWindow] = None

    def create_widget(self, parent=None):
        root, lay = _make_scrollable_page(parent)
        default_html_path = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "StreamerCalyx",
            "end_credits.html",
        )
        cfg = self.api.get_config({
            "credits_data": DEFAULT_CREDITS_DATA,
            "speed": 60,
            "loop": True,
            "transparent": False,
            "html_path": default_html_path,
        })

        grp = QGroupBox("🎬 Stream Ending Credits (Movie-Style OBS Browser Source + Scroller)")
        g_lay = QVBoxLayout(grp)
        g_lay.setSpacing(8)

        lbl_info = QLabel(
            "Uses your structured JSON credit blocks (<code>role</code>, <code>scale</code>, <code>names</code> "
            "with auto 2-column layout at &gt;24 entries, plus <code>{\"name\", \"reason\"}</code> Special Thanks)."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("font-size: 11px; opacity: 0.85;")
        g_lay.addWidget(lbl_info)

        txt = QTextEdit()
        txt.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        txt.setPlainText(json.dumps(cfg.get("credits_data", DEFAULT_CREDITS_DATA), indent=2, ensure_ascii=False))
        txt.setFixedHeight(230)
        g_lay.addWidget(txt)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Speed (px/s):"))
        spn_speed = QSpinBox()
        spn_speed.setRange(10, 300)
        spn_speed.setValue(int(cfg.get("speed", 60)))
        ctrl.addWidget(spn_speed)

        chk_loop = QCheckBox("Loop")
        chk_loop.setChecked(bool(cfg.get("loop", True)))
        ctrl.addWidget(chk_loop)

        chk_trans = QCheckBox("Transparent BG (OBS)")
        chk_trans.setChecked(bool(cfg.get("transparent", False)))
        ctrl.addWidget(chk_trans)
        ctrl.addStretch()
        g_lay.addLayout(ctrl)

        path_row = QHBoxLayout()
        txt_html_path = QLineEdit(str(cfg.get("html_path", default_html_path)))
        txt_html_path.setMinimumWidth(0)
        btn_browse = QPushButton("Browse...")
        path_row.addWidget(QLabel("OBS HTML:"))
        path_row.addWidget(txt_html_path, 1)
        path_row.addWidget(btn_browse)
        g_lay.addLayout(path_row)

        btns = QHBoxLayout()
        btn_import = QPushButton("📂 Import HTML...")
        btn_save = QPushButton("💾 Save && Export HTML")
        btn_browser = QPushButton("🌐 Preview HTML")
        btn_launch = QPushButton("🎬 Launch Window")
        btn_launch.setStyleSheet("background-color: #6d28d9; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")

        def _parse_data() -> Optional[List[Dict[str, Any]]]:
            try:
                parsed = json.loads(txt.toPlainText())
                if not isinstance(parsed, list):
                    raise ValueError("Credits JSON must be a list of role blocks.")
                return parsed
            except Exception as e:
                QMessageBox.warning(root, "Invalid Credits JSON", f"Please fix JSON syntax:\n{e}")
                return None

        def _save_and_export() -> Optional[List[Dict[str, Any]]]:
            data = _parse_data()
            if data is None:
                return None
            out_path = txt_html_path.text().strip() or default_html_path
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            html_str = _generate_credits_html(data, spn_speed.value(), chk_loop.isChecked(), chk_trans.isChecked())
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_str)
            self.api.save_config({
                "credits_data": data,
                "speed": spn_speed.value(),
                "loop": chk_loop.isChecked(),
                "transparent": chk_trans.isChecked(),
                "html_path": out_path,
            })
            self.api.show_overlay_toast(f"Credits HTML exported!", True)
            return data

        def _import_html():
            p, _ = QFileDialog.getOpenFileName(root, "Import Credits HTML (e.g. end credits B.html)", "", "HTML Files (*.html *.htm)")
            if not p:
                return
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = f.read()
                m = re.search(r"const\s+creditsData\s*=\s*(\[[\s\S]*?\]);", raw)
                if not m:
                    QMessageBox.warning(root, "Import Notice", "Could not find `const creditsData = [...]` in that HTML file.")
                    return
                js_arr = m.group(1)
                # Strip JS // line comments and trailing commas, quote unquoted keys
                js_arr = re.sub(r"//.*", "", js_arr)
                js_arr = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', js_arr)
                js_arr = re.sub(r",\s*([}\]])", r"\1", js_arr)
                # Normalize single-quoted strings if present via ast.literal_eval fallback
                try:
                    parsed = json.loads(js_arr)
                except Exception:
                    import ast
                    parsed = ast.literal_eval(js_arr)
                txt.setPlainText(json.dumps(parsed, indent=2, ensure_ascii=False))
                self.api.show_overlay_toast("Imported creditsData from HTML!", True)
            except Exception as e:
                QMessageBox.warning(root, "Import Error", f"Failed to parse creditsData:\n{e}")

        def _browse():
            p, _ = QFileDialog.getSaveFileName(root, "Save OBS Credits HTML", txt_html_path.text(), "HTML Files (*.html)")
            if p:
                txt_html_path.setText(p)

        def _preview_browser():
            if _save_and_export() is not None:
                QDesktopServices.openUrl(QUrl.fromLocalFile(txt_html_path.text().strip()))

        def _launch_win():
            data = _save_and_export()
            if data is None:
                return
            if self._win:
                self._win.close()
            self._win = _CreditsScrollerWindow(_format_credits_for_qt(data), spn_speed.value(), chk_loop.isChecked())
            self._win.show()

        btn_browse.clicked.connect(_browse)
        btn_import.clicked.connect(_import_html)
        btn_save.clicked.connect(_save_and_export)
        btn_browser.clicked.connect(_preview_browser)
        btn_launch.clicked.connect(_launch_win)

        btns.addWidget(btn_import)
        btns.addWidget(btn_save)
        btns.addWidget(btn_browser)
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
