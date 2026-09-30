"""
FLOWDEV FRAME - Real-Time Open Position HUD Card
Displays live floating PnL ($ / R), Kinetic OMS stage, SL/TP targets, and instant panic close button.
"""

from typing import Optional, Dict, Any

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QColor
except ImportError:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
    )
    from PyQt6.QtCore import Qt, pyqtSignal as Signal
    from PyQt6.QtGui import QColor

class LivePositionHUD(QFrame):
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pos_hud")
        self.setStyleSheet("""
            #pos_hud {
                background-color: #0d111a;
                border: 1px solid #1c2333;
                border-radius: 3px;
                padding: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        self.setMaximumHeight(46)

        # 1. Standby / Empty Bar
        self.frame_standby = QFrame()
        st_layout = QHBoxLayout(self.frame_standby)
        st_layout.setContentsMargins(4, 2, 4, 2)
        self.lbl_standby = QLabel("● STANDBY // AGENT ACTIVELY SCANNING XAU/USD (M30) FOR INSTITUTIONAL SETUP...")
        self.lbl_standby.setStyleSheet("color: #64748b; font-size: 11px; font-family: monospace; font-weight: 600;")
        st_layout.addWidget(self.lbl_standby)
        st_layout.addStretch()
        layout.addWidget(self.frame_standby)

        # 2. Active Position Bar
        self.frame_active = QFrame()
        act_layout = QHBoxLayout(self.frame_active)
        act_layout.setContentsMargins(2, 0, 2, 0)
        act_layout.setSpacing(10)

        # Col A: Direction & Lot
        self.lbl_dir = QLabel("BUY 0.01L")
        self.lbl_dir.setStyleSheet("""
            background-color: #064e3b; color: #a7f3d0; font-weight: 800;
            padding: 3px 8px; border-radius: 3px; font-size: 11px; font-family: monospace;
            border: 1px solid #059669;
        """)
        act_layout.addWidget(self.lbl_dir)

        # Col B: Entry & Live Price
        col_b = QHBoxLayout()
        col_b.setSpacing(8)
        self.lbl_prices = QLabel("ENTRY: $4,310.50 | MKT: $4,312.10")
        self.lbl_prices.setStyleSheet("color: #f1f5f9; font-size: 11px; font-family: monospace; font-weight: 700;")
        self.lbl_targets = QLabel("SL: $4,305.20 | TP: $4,324.80")
        self.lbl_targets.setStyleSheet("color: #94a3b8; font-size: 11px; font-family: monospace;")
        col_b.addWidget(self.lbl_prices)
        col_b.addWidget(self.lbl_targets)
        act_layout.addLayout(col_b)

        act_layout.addStretch()

        # Col C: Kinetic OMS Stage Badge
        self.lbl_oms_stage = QLabel("STAGE 0: INITIAL SL")
        self.lbl_oms_stage.setStyleSheet("""
            background-color: #0f172a; color: #38bdf8; font-size: 10px;
            font-weight: 700; padding: 3px 6px; border: 1px solid #1e293b; border-radius: 3px;
            font-family: monospace;
        """)
        act_layout.addWidget(self.lbl_oms_stage)

        # Col D: Floating PnL ($ and R)
        self.lbl_pnl = QLabel("+$0.00 (+0.00R)")
        self.lbl_pnl.setStyleSheet("""
            font-size: 15px; font-weight: 800; font-family: 'Consolas', monospace; color: #00e676;
        """)
        act_layout.addWidget(self.lbl_pnl)

        # Col E: Time held / Bars
        self.lbl_bars = QLabel("Bar 1/12")
        self.lbl_bars.setStyleSheet("color: #64748b; font-size: 10px; font-family: monospace;")
        act_layout.addWidget(self.lbl_bars)

        # Col F: Panic Close Button
        self.btn_close = QPushButton("CLOSE POSITION")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #450a0a;
                border: 1px solid #dc2626;
                color: #fca5a5;
                font-weight: 700;
                font-size: 10px;
                padding: 4px 10px;
                border-radius: 3px;
                font-family: monospace;
            }
            QPushButton:hover {
                background-color: #7f1d1d;
                color: #ffffff;
            }
        """)
        self.btn_close.clicked.connect(self.close_requested.emit)
        act_layout.addWidget(self.btn_close)

        layout.addWidget(self.frame_active)

        self.set_standby(True)

    def set_standby(self, is_standby: bool, symbol: str = 'XAU/USD'):
        self.frame_standby.setVisible(is_standby)
        self.frame_active.setVisible(not is_standby)
        if is_standby:
            self.lbl_standby.setText(f'STANDBY // AGENT ACTIVELY SCANNING {symbol} FOR INSTITUTIONAL SETUP...')

    def update_position(self, pos: dict, live_price: float = 0.0):
        self.set_standby(False)
        d = pos.get("direction", "BUY")
        lot = pos.get("lot", 0.01)
        ep = pos.get("entry_price", 0.0)
        sl = pos.get("current_sl", 0.0)
        tp = pos.get("current_tp", 0.0)
        pnl = pos.get("floating_pnl", 0.0)
        r = pos.get("floating_r", 0.0)
        bars = pos.get("bars_held", 1)

        # Direction badge
        if d == "BUY":
            self.lbl_dir.setText(f"BUY {lot:.2f}L")
            self.lbl_dir.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-weight: 800; padding: 4px 10px; border-radius: 3px; font-size: 12px; font-family: monospace;")
        else:
            self.lbl_dir.setText(f"SELL {lot:.2f}L")
            self.lbl_dir.setStyleSheet("background-color: #7c2d12; color: #fdba74; font-weight: 800; padding: 4px 10px; border-radius: 3px; font-size: 12px; font-family: monospace;")

        # Prices
        self.lbl_prices.setText(f"ENTRY: ${ep:,.2f}  |  MARKET: ${live_price:,.2f}")
        self.lbl_targets.setText(f"SL: ${sl:,.2f}  |  TP (+2.7R): ${tp:,.2f}")

        # PnL & R
        pnl_color = "#00e676" if pnl >= 0 else "#ff5252"
        self.lbl_pnl.setText(f"${pnl:+,.2f} ({r:+,.2f}R)")
        self.lbl_pnl.setStyleSheet(f"font-size: 18px; font-weight: 800; font-family: 'Consolas', monospace; color: {pnl_color};")

        # Bars held
        self.lbl_bars.setText(f"Bar {bars}/12")

        # Stage Badge
        if pos.get("trail_activated"):
            self.lbl_oms_stage.setText("STAGE 3: TRAILING STOP ACTIVE")
            self.lbl_oms_stage.setStyleSheet("background-color: #064e3b; color: #34d399; font-size: 10px; font-weight: 700; padding: 4px 8px; border: 1px solid #059669; border-radius: 3px;")
        elif pos.get("ratchet_activated"):
            self.lbl_oms_stage.setText("STAGE 2: SMART RATCHET (+0.5R LOCKED)")
            self.lbl_oms_stage.setStyleSheet("background-color: #14532d; color: #86efac; font-size: 10px; font-weight: 700; padding: 4px 8px; border: 1px solid #16a34a; border-radius: 3px;")
        elif pos.get("be_activated"):
            self.lbl_oms_stage.setText("STAGE 1: MICRO-BE ACTIVE (+0.75R)")
            self.lbl_oms_stage.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-size: 10px; font-weight: 700; padding: 4px 8px; border: 1px solid #2563eb; border-radius: 3px;")
        elif pos.get("stale_decay_activated"):
            self.lbl_oms_stage.setText("STAGE 4: STALE DECAY (-0.45R)")
            self.lbl_oms_stage.setStyleSheet("background-color: #78350f; color: #fde047; font-size: 10px; font-weight: 700; padding: 4px 8px; border: 1px solid #d97706; border-radius: 3px;")
        else:
            self.lbl_oms_stage.setText("STAGE 0: INITIAL RISK (-1.0R)")
            self.lbl_oms_stage.setStyleSheet("background-color: #182234; color: #94a3b8; font-size: 10px; font-weight: 700; padding: 4px 8px; border: 1px solid #334155; border-radius: 3px;")
