"""
FLOWDEV FRAME - Live Institutional Metrics Cards Panel
Matches the visual architecture and styling of the Causal Backtest Station Metrics Panel.
Displays:
1. Live Equity
2. Net Profit ($ and %)
3. Win Rate (%)
4. Profit Factor
5. Max Drawdown (%)
6. Active Position
7. Total Trades (Wins / Losses)
"""

from typing import Dict, Any, Optional

try:
    from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
    from PySide6.QtCore import Qt
except ImportError:
    from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
    from PyQt6.QtCore import Qt


class LiveMetricCard(QFrame):
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

        self.val_color = val_color
        self.lbl_value = QLabel(initial_val)
        self.lbl_value.setStyleSheet(f"font-size: 17px; font-weight: 700; font-family: 'Consolas', 'Courier New', monospace; color: {val_color};")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

    def set_value(self, val_text: str, custom_color: str = None):
        self.lbl_value.setText(val_text)
        color = custom_color if custom_color else self.val_color
        self.lbl_value.setStyleSheet(f"font-size: 17px; font-weight: 700; font-family: 'Consolas', 'Courier New', monospace; color: {color};")


class LiveMetricsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.card_equity = LiveMetricCard("Live Equity", "$250.00", "#00e676")
        self.card_net_pnl = LiveMetricCard("Net Profit", "$0.00 (+0.0%)", "#8b949e")
        self.card_wr = LiveMetricCard("Win Rate", "0.0%", "#ffd700")
        self.card_pf = LiveMetricCard("Profit Factor", "0.00", "#2979ff")
        self.card_dd = LiveMetricCard("Max Drawdown", "0.00%", "#ff5252")
        self.card_pos = LiveMetricCard("Active Position", "STANDBY (FLAT)", "#8b949e")
        self.card_trades = LiveMetricCard("Total Trades", "0 (W:0 / L:0)", "#c9d1d9")

        layout.addWidget(self.card_equity)
        layout.addWidget(self.card_net_pnl)
        layout.addWidget(self.card_wr)
        layout.addWidget(self.card_pf)
        layout.addWidget(self.card_dd)
        layout.addWidget(self.card_pos)
        layout.addWidget(self.card_trades)

    def update_metrics(self, stats: Dict[str, Any], current_session: Optional[str] = None):
        cash = float(stats.get("cash", 250.0))
        equity = float(stats.get("equity", cash))
        net_profit = float(stats.get("net_profit", 0.0))
        ret_pct = float(stats.get("return_pct", 0.0))
        wr = float(stats.get("win_rate", 0.0))
        pf = float(stats.get("profit_factor", 0.0))
        dd = float(stats.get("max_drawdown", 0.0))
        trades = int(stats.get("total_trades", 0))
        wins = int(stats.get("winning_trades", 0))
        losses = int(stats.get("losing_trades", 0))

        # 1. Equity
        eq_color = "#00e676" if equity >= cash else "#ff5252"
        self.card_equity.set_value(f"${equity:,.2f}", eq_color)

        # 2. Net Profit
        pnl_color = "#00e676" if net_profit > 0 else ("#ff5252" if net_profit < 0 else "#8b949e")
        self.card_net_pnl.set_value(f"${net_profit:+,.2f} ({ret_pct:+,.1f}%)", pnl_color)

        # 3. Win Rate
        self.card_wr.set_value(f"{wr:.1f}%", "#ffd700")

        # 4. Profit Factor
        self.card_pf.set_value(f"{pf:.2f}", "#2979ff")

        # 5. Drawdown
        self.card_dd.set_value(f"{dd:.2f}%", "#ff5252")

        # 6. Active Position
        pos = stats.get("open_position")
        if pos and pos.get("direction"):
            d = str(pos["direction"]).upper()
            lot = float(pos.get("lot", 0.01))
            fl_r = float(pos.get("floating_r", 0.0))
            pos_color = "#00e676" if d == "BUY" else "#f43f5e"
            self.card_pos.set_value(f"{d} {lot:.2f}L ({fl_r:+.2f}R)", pos_color)
        else:
            self.card_pos.set_value("STANDBY (FLAT)", "#8b949e")

        # 7. Total Trades
        self.card_trades.set_value(f"{trades} (W:{wins}/L:{losses})", "#c9d1d9")
