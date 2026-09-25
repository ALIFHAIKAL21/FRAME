"""
FLOWDEV FRAME - Live Real-Time Trade Journal & AI Telemetry Widget
Displays real-time closed trade ledger, neural network inference output, and OMS event log.
"""

from typing import List, Dict, Any

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, 
        QTableWidgetItem, QHeaderView, QPlainTextEdit, QLabel
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
except ImportError:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, 
        QTableWidgetItem, QHeaderView, QPlainTextEdit, QLabel
    )
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor

class LiveTradeJournalWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Tab 1: Closed Trade Ledger
        self.tab_ledger = QWidget()
        l_layout = QVBoxLayout(self.tab_ledger)
        l_layout.setContentsMargins(4, 4, 4, 4)

        self.tbl_trades = QTableWidget()
        self.tbl_trades.setColumnCount(10)
        self.tbl_trades.setHorizontalHeaderLabels([
            "Time (UTC)", "Direction", "Lot Size", "Entry Price", "Exit Price",
            "SL Dist ($)", "Net PnL ($)", "Balance ($)", "Bars Held", "Exit Reason"
        ])
        self.tbl_trades.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l_layout.addWidget(self.tbl_trades)
        self.addTab(self.tab_ledger, "LIVE TRADE JOURNAL")

        # Tab 2: Neural Network Telemetry
        self.tab_telemetry = QWidget()
        t_layout = QVBoxLayout(self.tab_telemetry)
        t_layout.setContentsMargins(8, 8, 8, 8)
        self.txt_telemetry = QPlainTextEdit()
        self.txt_telemetry.setReadOnly(True)
        self.txt_telemetry.setStyleSheet("background-color: #080c14; border: 1px solid #161e2e; font-family: monospace; color: #8b949e; font-size: 11px;")
        t_layout.addWidget(self.txt_telemetry)
        self.addTab(self.tab_telemetry, "AI INFERENCE MONITOR")

        # Tab 3: OMS & System Event Stream
        self.tab_events = QWidget()
        e_layout = QVBoxLayout(self.tab_events)
        e_layout.setContentsMargins(8, 8, 8, 8)
        self.txt_events = QPlainTextEdit()
        self.txt_events.setReadOnly(True)
        self.txt_events.setStyleSheet("background-color: #080c14; border: 1px solid #161e2e; font-family: monospace; color: #8b949e; font-size: 11px;")
        e_layout.addWidget(self.txt_events)
        self.addTab(self.tab_events, "KINETIC OMS LOG")

        self._log_event("[SYSTEM] Live Trade Journal & Telemetry initialized.")

    def add_closed_trade(self, t: dict):
        row = self.tbl_trades.rowCount()
        self.tbl_trades.insertRow(row)

        pnl_val = t.get('net_pnl', 0.0)
        pnl_color = QColor("#00e676") if pnl_val >= 0 else QColor("#ff5252")

        item_ts = QTableWidgetItem(str(t.get('close_time', ''))[:19])
        item_dir = QTableWidgetItem(str(t.get('direction', '')))
        item_dir.setForeground(QColor("#2979ff") if t.get('direction') == "BUY" else QColor("#ff9100"))

        item_lot = QTableWidgetItem(f"{t.get('lot', 0.01):.2f}L")
        item_ep = QTableWidgetItem(f"${t.get('entry_price', 0.0):,.2f}")
        item_exit = QTableWidgetItem(f"${t.get('exit_price', 0.0):,.2f}")
        item_sl = QTableWidgetItem(f"${t.get('sl_dist', 0.0):.2f}")
        item_pnl = QTableWidgetItem(f"${pnl_val:+,.2f}")
        item_pnl.setForeground(pnl_color)
        item_eq = QTableWidgetItem(f"${t.get('balance', 0.0):,.2f}")
        item_bars = QTableWidgetItem(str(t.get('bars_held', 1)))
        item_reason = QTableWidgetItem(str(t.get('exit_reason', '')))

        for c, itm in enumerate([item_ts, item_dir, item_lot, item_ep, item_exit, item_sl, item_pnl, item_eq, item_bars, item_reason]):
            itm.setTextAlignment(Qt.AlignCenter)
            self.tbl_trades.setItem(row, c, itm)

        self.tbl_trades.scrollToBottom()
        self._log_event(f"[TRADE CLOSED] {t.get('direction')} {t.get('lot'):.2f}L | Net PnL: ${pnl_val:+,.2f} | Reason: {t.get('exit_reason')}")

    def update_telemetry(self, tele: dict):
        probs_str = " | ".join([f"C{i}: {p:.1f}%" for i, p in enumerate(tele.get("probs", []))])
        line = (
            f"[{tele.get('time', '')}] Session: {tele.get('session', '')} | "
            f"Verdict: {tele.get('action', '')} (Conf: {tele.get('conf', 0):.1f}%) | "
            f"ATR(14): ${tele.get('atr', 0):.2f} | SL Dist: ${tele.get('sl_dist', 0):.2f}\n"
            f"  Class Probs -> {probs_str}\n"
            "--------------------------------------------------------------------------"
        )
        self.txt_telemetry.appendPlainText(line)
        self.txt_telemetry.verticalScrollBar().setValue(self.txt_telemetry.verticalScrollBar().maximum())

    def log_oms_event(self, stage: str, details: str, price: float):
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        msg = f"[{now_str}] [{stage.upper()}] {details} (Ref Price: ${price:,.2f})"
        self.txt_events.appendPlainText(msg)
        self.txt_events.verticalScrollBar().setValue(self.txt_events.verticalScrollBar().maximum())

    def _log_event(self, msg: str):
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        self.txt_events.appendPlainText(f"[{now_str}] {msg}")
        self.txt_events.verticalScrollBar().setValue(self.txt_events.verticalScrollBar().maximum())

from datetime import datetime, timezone
