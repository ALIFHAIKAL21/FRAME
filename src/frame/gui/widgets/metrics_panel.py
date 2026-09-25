"""
Clean Institutional Metrics Cards Panel
Displays key audit metrics in sharp, minimal format without unnecessary icons.
"""

from typing import Dict, Any

try:
    from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
    from PySide6.QtCore import Qt
except ImportError:
    from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
    from PyQt6.QtCore import Qt

class MetricCard(QFrame):
    def __init__(self, label: str, initial_val: str = "—", val_color: str = "#f0f6fc"):
        super().__init__()
        self.setProperty("class", "panel-card")
        self.setStyleSheet("""
            QFrame {
                background-color: #121722;
                border: 1px solid #1e2638;
                border-radius: 3px;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        self.lbl_title = QLabel(label.upper())
        self.lbl_title.setStyleSheet("font-size: 10px; color: #8b949e; font-weight: 600; letter-spacing: 0.8px;")

        self.lbl_value = QLabel(initial_val)
        self.val_color = val_color
        self.lbl_value.setStyleSheet(f"font-size: 17px; font-weight: 700; font-family: 'Consolas', 'Courier New', monospace; color: {val_color};")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

    def set_value(self, val_text: str, custom_color: str = None):
        self.lbl_value.setText(val_text)
        color = custom_color if custom_color else self.val_color
        self.lbl_value.setStyleSheet(f"font-size: 17px; font-weight: 700; font-family: 'Consolas', 'Courier New', monospace; color: {color};")


class MetricsPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.card_net_pnl = MetricCard("Net Profit", "—", "#00e676")
        self.card_wr = MetricCard("Win Rate", "—", "#ffd700")
        self.card_pf = MetricCard("Profit Factor", "—", "#2979ff")
        self.card_max_dd = MetricCard("Max Drawdown", "—", "#ff5252")
        self.card_dip = MetricCard("Lowest Dip", "—", "#c9d1d9")
        self.card_sizing = MetricCard("Sizing / Peak Lot", "—", "#00e5ff")
        self.card_trades = MetricCard("Total Trades", "—", "#c9d1d9")

        layout.addWidget(self.card_net_pnl)
        layout.addWidget(self.card_wr)
        layout.addWidget(self.card_pf)
        layout.addWidget(self.card_max_dd)
        layout.addWidget(self.card_dip)
        layout.addWidget(self.card_sizing)
        layout.addWidget(self.card_trades)

    def update_metrics(self, data: Dict[str, Any]):
        net = data.get('net_pnl', 0.0)
        ret_pct = data.get('return_pct', 0.0)
        pnl_color = "#00e676" if net >= 0 else "#ff5252"
        self.card_net_pnl.set_value(f"${net:+,.2f} ({ret_pct:+,.1f}%)", pnl_color)

        wr = data.get('win_rate', 0.0)
        self.card_wr.set_value(f"{wr:.2f}%", "#ffd700")

        pf = data.get('profit_factor', 0.0)
        self.card_pf.set_value(f"{pf:.2f}", "#2979ff")

        dd = data.get('max_drawdown', 0.0)
        self.card_max_dd.set_value(f"{dd:.2f}%", "#ff5252")

        min_eq = data.get('min_equity', 0.0)
        self.card_dip.set_value(f"${min_eq:,.2f}", "#c9d1d9")

        sizing_mode = data.get('sizing_mode', 'flat').lower()
        peak_lot = data.get('peak_lot', 0.01)
        if sizing_mode == 'dual':
            self.card_sizing.set_value(f"Dual ({peak_lot:.2f}L)", "#00e5ff")
        elif sizing_mode == 'dynamic':
            self.card_sizing.set_value(f"Dyn ({peak_lot:.2f}L)", "#00e676")
        else:
            self.card_sizing.set_value("Flat (0.01L)", "#c9d1d9")

        trades = data.get('total_trades', 0)
        wins = data.get('wins', 0)
        losses = data.get('losses', 0)
        self.card_trades.set_value(f"{trades} (W:{wins}/L:{losses})", "#c9d1d9")

