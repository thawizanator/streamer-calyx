"""
Phase 14.5: Launch & First-Party Core Plugins
Remaining built-in plugins inherit from CalyxPluginBase and run inside the crash-isolated CalyxAPI.
Downloadable core plugins (Ending Credits, Backstage Teleprompter, Encrypted Peer Chat,
StreamElements, Streamlabs) are fetched on-demand from GitHub via PluginManager.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
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
# 1. Devo's Slots Mini-Game (calyx.devos_slots)
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
# 2. VoiceMeeter / Discord Audio Ducking Hotkey (calyx.audio_ducking)
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
