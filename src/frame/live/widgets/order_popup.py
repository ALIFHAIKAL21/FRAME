"""
FLOWDEV FRAME - Live Order Notification Popup (Compact Institutional Toast)
Triggered automatically when the AI Model opens a new live position.
Displays:
1. Direction & Lot
2. Entry Price
3. Stop Loss (SL)
4. Take Profit (TP)
5. Risk-to-Reward (RR) ratio
"""

from typing import Optional, Dict, Any

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QProgressBar
    )
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QColor
except ImportError:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QProgressBar
    )
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont, QColor


class LiveOrderPopup(QDialog):
    """
    Compact, sleek, non-blocking modal popup displayed when the model opens a trade.
    Ultra-clean institutional aesthetic, zero clutter, no cheesy icons.
    """
    def __init__(self, order_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        # Frameless, non-modal tool window that stays on top without stealing focus
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(330, 185)

        d = str(order_data.get("direction", "BUY")).upper()
        lot = float(order_data.get("lot", 0.01))
        ep = float(order_data.get("entry_price", 0.0))
        sl = float(order_data.get("current_sl", order_data.get("sl_price", 0.0)))
        tp = float(order_data.get("current_tp", order_data.get("tp_price", 0.0)))

        is_buy = d == "BUY"
        accent_color = "#00e676" if is_buy else "#f43f5e"
        accent_border = "#059669" if is_buy else "#e11d48"
        badge_bg = "#064e3b" if is_buy else "#4c0519"

        # Calculate RR and Distances
        sl_dist = abs(ep - sl)
        tp_dist = abs(tp - ep)
        rr = (tp_dist / sl_dist) if sl_dist > 1e-4 else 0.0

        self.setStyleSheet(f"""
            QDialog {{
                background-color: #0b0f17;
                border: 1px solid {accent_border};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(6)

        # ── 1. HEADER ROW ──
        h_row = QHBoxLayout()
        h_row.setSpacing(8)

        lbl_badge = QLabel(f" {d} {lot:.2f}L ")
        lbl_badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: {accent_color};
            font-size: 11px;
            font-weight: 800;
            font-family: 'Consolas', monospace;
            padding: 3px 6px;
            border-radius: 3px;
            border: 1px solid {accent_border};
        """)
        h_row.addWidget(lbl_badge)

        lbl_title = QLabel("NEW POSITION OPENED")
        lbl_title.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        h_row.addWidget(lbl_title)
        h_row.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(18, 18)
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        btn_close.clicked.connect(self.close)
        h_row.addWidget(btn_close)
        layout.addLayout(h_row)

        # ── 2. SEPARATOR LINE ──
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #1e293b;")
        layout.addWidget(sep)

        # ── 3. DATA GRID (Entry, SL, TP, RR) ──
        grid = QVBoxLayout()
        grid.setSpacing(4)

        # Row 1: Entry
        r1 = QHBoxLayout()
        lbl_e_txt = QLabel("ENTRY PRICE")
        lbl_e_txt.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
        lbl_e_val = QLabel(f"${ep:,.2f}")
        lbl_e_val.setStyleSheet("color: #f1f5f9; font-size: 13px; font-weight: 800; font-family: 'Consolas', monospace;")
        r1.addWidget(lbl_e_txt)
        r1.addStretch()
        r1.addWidget(lbl_e_val)
        grid.addLayout(r1)

        # Row 2: Stop Loss
        r2 = QHBoxLayout()
        lbl_sl_txt = QLabel("STOP LOSS (SL)")
        lbl_sl_txt.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
        lbl_sl_val = QLabel(f"${sl:,.2f}  (-1.0R)")
        lbl_sl_val.setStyleSheet("color: #f87171; font-size: 12px; font-weight: 700; font-family: 'Consolas', monospace;")
        r2.addWidget(lbl_sl_txt)
        r2.addStretch()
        r2.addWidget(lbl_sl_val)
        grid.addLayout(r2)

        # Row 3: Take Profit
        r3 = QHBoxLayout()
        lbl_tp_txt = QLabel("TAKE PROFIT (TP)")
        lbl_tp_txt.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
        lbl_tp_val = QLabel(f"${tp:,.2f}  (+{rr:.1f}R)")
        lbl_tp_val.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 700; font-family: 'Consolas', monospace;")
        r3.addWidget(lbl_tp_txt)
        r3.addStretch()
        r3.addWidget(lbl_tp_val)
        grid.addLayout(r3)

        # Row 4: Risk-Reward
        r4 = QHBoxLayout()
        lbl_rr_txt = QLabel("RISK / REWARD")
        lbl_rr_txt.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 700;")
        lbl_rr_val = QLabel(f"1 : {rr:.2f}")
        lbl_rr_val.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 800; font-family: 'Consolas', monospace;")
        r4.addWidget(lbl_rr_txt)
        r4.addStretch()
        r4.addWidget(lbl_rr_val)
        grid.addLayout(r4)

        layout.addLayout(grid)

        # ── 4. FOOTER NOTE ──
        lbl_model = QLabel("MOMENT-1-large Foundation Setup • M30")
        lbl_model.setStyleSheet("color: #475569; font-size: 9.5px; font-family: monospace;")
        layout.addWidget(lbl_model)

        # Auto-dismiss after 8 seconds
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self.close)
        self._auto_timer.start(8000)

    def show_anchored(self, parent_widget=None):
        """Displays popup anchored neatly in top-right of parent window."""
        if parent_widget:
            geo = parent_widget.geometry()
            x = geo.right() - self.width() - 25
            y = geo.top() + 75
            self.move(x, y)
        self.show()
