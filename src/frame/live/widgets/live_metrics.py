"""
FLOWDEV FRAME - Live Institutional Metrics Cards Panel
Displays real-time cash balance, floating equity, realized PnL, win rate, and profit factor.
"""

from typing import Dict, Any

try:
    from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
except ImportError:
    from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame

class LiveMetricCard(QFrame):
    def __init__(self, title: str, initial_val: str = "—", val_color: str = "#f0f6fc"):
        super().__init__()
        self.setObjectName("live_card")
        self.setStyleSheet("""
            #live_card {
                background-color: #0f1522;
                border: 1px solid #1a2233;
                border-radius: 3px;
                padding: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet("font-size: 9.5px; color: #8b949e; font-weight: 700; letter-spacing: 0.8px;")

        self.val_color = val_color
        self.lbl_value = QLabel(initial_val)
        self.lbl_value.setStyleSheet(f"font-size: 16px; font-weight: 800; font-family: 'Consolas', monospace; color: {val_color};")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

    def set_value(self, text: str, custom_color: str = None):
        color = custom_color or self.val_color
        self.lbl_value.setText(text)
        self.lbl_value.setStyleSheet(f"font-size: 16px; font-weight: 800; font-family: 'Consolas', monospace; color: {color};")


class LiveMetricsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.card_equity = LiveMetricCard("Live Equity", "$500.00", "#00e676")
        self.card_balance = LiveMetricCard("Cash Balance", "$500.00", "#f0f6fc")
        self.card_pnl = LiveMetricCard("Realized PnL", "$0.00 (0.0%)", "#8b949e")
        self.card_wr = LiveMetricCard("Win Rate", "0.0%", "#ffd700")
        self.card_pf = LiveMetricCard("Profit Factor", "0.00", "#2979ff")
        self.card_dd = LiveMetricCard("Max Drawdown", "0.00%", "#ff5252")
        self.card_session = LiveMetricCard("Active Session", "NY Open", "#38bdf8")

        layout.addWidget(self.card_equity)
        layout.addWidget(self.card_balance)
        layout.addWidget(self.card_pnl)
        layout.addWidget(self.card_wr)
        layout.addWidget(self.card_pf)
        layout.addWidget(self.card_dd)
        layout.addWidget(self.card_session)

    def update_metrics(self, stats: Dict[str, Any], current_session: str = "Active"):
        cash = stats.get("cash", 500.0)
        equity = stats.get("equity", 500.0)
        net_profit = stats.get("net_profit", 0.0)
        ret_pct = stats.get("return_pct", 0.0)
        wr = stats.get("win_rate", 0.0)
        pf = stats.get("profit_factor", 0.0)
        dd = stats.get("max_drawdown", 0.0)

        # Equity
        eq_color = "#00e676" if equity >= cash else "#ff5252"
        self.card_equity.set_value(f"${equity:,.2f}", eq_color)

        # Cash
        self.card_balance.set_value(f"${cash:,.2f}", "#f0f6fc")

        # PnL
        pnl_color = "#00e676" if net_profit > 0 else ("#ff5252" if net_profit < 0 else "#8b949e")
        self.card_pnl.set_value(f"${net_profit:+,.2f} ({ret_pct:+,.1f}%)", pnl_color)

        # WR, PF, DD
        self.card_wr.set_value(f"{wr:.1f}%", "#ffd700")
        self.card_pf.set_value(f"{pf:.2f}", "#2979ff")
        self.card_dd.set_value(f"{dd:.2f}%", "#ff5252")

        # Session
        self.card_session.set_value(current_session or "Off-Session", "#38bdf8")
