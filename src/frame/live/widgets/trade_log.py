"""
FLOWDEV FRAME - Live Real-Time Trade Journal & AI Telemetry Widget
Displays real-time open trade status, closed trade ledger, neural network inference output, and OMS event log.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, 
        QTableWidgetItem, QHeaderView, QPlainTextEdit, QLabel, QFrame
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
except ImportError:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, 
        QTableWidgetItem, QHeaderView, QPlainTextEdit, QLabel, QFrame
    )
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor


class LiveTradeJournalWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Tab 1: Active Position & Closed Trade Ledger
        self.tab_ledger = QWidget()
        l_layout = QVBoxLayout(self.tab_ledger)
        l_layout.setContentsMargins(5, 4, 5, 4)
        l_layout.setSpacing(4)

        # ── 1. ACTIVE / FLOATING POSITION BANNER (Detached / Handled by Position HUD) ──
        self.active_card = QFrame()
        self.lbl_active_badge = QLabel("⚡ STANDBY")
        self.lbl_active_info = QLabel("")
        self.lbl_active_pnl = QLabel("")
        self.lbl_active_stage = QLabel("")

        # ── 2. CLOSED TRADES TABLE ──
        self.tbl_trades = QTableWidget()
        self.tbl_trades.setColumnCount(10)
        self.tbl_trades.setHorizontalHeaderLabels([
            "Time (UTC)", "Direction", "Lot Size", "Entry Price", "Exit Price",
            "SL Dist ($)", "Net PnL ($)", "Balance ($)", "Bars Held", "Exit Reason"
        ])
        self.tbl_trades.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_trades.horizontalHeader().setFixedHeight(25)
        self.tbl_trades.verticalHeader().setVisible(False)
        self.tbl_trades.verticalHeader().setDefaultSectionSize(22)
        self.tbl_trades.setStyleSheet("""
            QTableWidget {
                background-color: #0b0f17;
                border: 1px solid #161e2e;
                gridline-color: #1a2333;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                color: #cbd5e1;
            }
            QHeaderView::section {
                background-color: #0f172a;
                color: #8b949e;
                font-weight: 700;
                font-size: 10px;
                border: 1px solid #1e293b;
                padding: 3px;
            }
        """)
        l_layout.addWidget(self.tbl_trades, stretch=1)
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

    def update_active_position(self, pos: Optional[dict], live_price: Optional[float] = None):
        """Displays active running trade prominently above the closed trades table."""
        if not pos or not pos.get("direction"):
            self.clear_active_position()
            return

        d = str(pos.get("direction", "BUY")).upper()
        lot = float(pos.get("lot", 0.01))
        ep = float(pos.get("entry_price", 0.0))
        sl = float(pos.get("current_sl", pos.get("sl_price", 0.0)))
        tp = float(pos.get("current_tp", pos.get("tp_price", 0.0)))
        pnl = float(pos.get("floating_pnl", 0.0))
        r_gain = float(pos.get("floating_r", 0.0))
        bars = int(pos.get("bars_held", 1))

        # Direction styling
        if d == "BUY":
            self.lbl_active_badge.setText(f"ACTIVE BUY {lot:.2f}L")
            self.lbl_active_badge.setStyleSheet("""
                background-color: #1e3a8a; color: #93c5fd; font-weight: 800;
                padding: 4px 10px; border-radius: 3px; font-size: 11px; font-family: monospace;
            """)
            self.active_card.setStyleSheet("background-color: #091224; border: 1px solid #1d4ed8; border-radius: 4px; padding: 6px 10px;")
        else:
            self.lbl_active_badge.setText(f"ACTIVE SELL {lot:.2f}L")
            self.lbl_active_badge.setStyleSheet("""
                background-color: #7c2d12; color: #fdba74; font-weight: 800;
                padding: 4px 10px; border-radius: 3px; font-size: 11px; font-family: monospace;
            """)
            self.active_card.setStyleSheet("background-color: #1f1107; border: 1px solid #ea580c; border-radius: 4px; padding: 6px 10px;")

        cur_str = f" | MKT: ${live_price:,.2f}" if live_price else ""
        self.lbl_active_info.setText(
            f"ENTRY: ${ep:,.2f}{cur_str}  |  SL: ${sl:,.2f}  |  TP (+2.7R): ${tp:,.2f}  |  Bar {bars}/12 (M30)"
        )
        self.lbl_active_info.setStyleSheet("color: #f1f5f9; font-size: 11px; font-family: monospace; font-weight: 600;")

        pnl_col = "#00e676" if pnl >= 0 else "#ff5252"
        self.lbl_active_pnl.setText(f"{'+' if pnl>=0 else ''}${pnl:,.2f} ({r_gain:+.2f}R)")
        self.lbl_active_pnl.setStyleSheet(f"font-size: 14px; font-weight: 800; font-family: monospace; color: {pnl_col};")

        # Stage detail
        stage_str = "STAGE 0: INITIAL SL"
        if pos.get("trail_activated"):
            stage_str = "STAGE 3: TRAILING STOP"
        elif pos.get("ratchet_activated"):
            stage_str = "STAGE 2: RATCHET (+0.5R LOCKED)"
        elif pos.get("be_activated"):
            stage_str = "STAGE 1: MICRO-BE (+0.75R)"
        elif pos.get("stale_decay_activated"):
            stage_str = "STAGE 4: STALE DECAY (-0.45R)"
        self.lbl_active_stage.setText(f"[{stage_str}]")

    def clear_active_position(self):
        """Resets active position card to standby state."""
        self.lbl_active_badge.setText("⚡ STANDBY")
        self.lbl_active_badge.setStyleSheet("""
            background-color: #1e293b; color: #94a3b8; font-weight: 800;
            padding: 3px 8px; border-radius: 3px; font-size: 11px; font-family: monospace;
        """)
        self.active_card.setStyleSheet("""
            QFrame {
                background-color: #0b0f19;
                border: 1px solid #1e293b;
                border-radius: 4px;
                padding: 6px 10px;
            }
        """)
        self.lbl_active_info.setText("No active order. Agent scanning M30 market setups...")
        self.lbl_active_info.setStyleSheet("color: #64748b; font-size: 11px; font-family: monospace;")
        self.lbl_active_pnl.setText("")
        self.lbl_active_stage.setText("")

    def set_trades(self, trades: List[dict]):
        """Populates the trade table from trade records (alias for session switching)."""
        self.tbl_trades.setRowCount(0)
        for t in trades:
            self._insert_trade_row(t)
        self.tbl_trades.scrollToBottom()

    def load_history_trades(self, trades: List[dict]):
        """Populates the trade table from historical trade records without spamming events."""
        self.set_trades(trades)
        if trades:
            self._log_event(f"[SYSTEM] Loaded {len(trades)} historical closed trade(s) from audit ledger.")

    def _insert_trade_row(self, t: dict):
        row = self.tbl_trades.rowCount()
        self.tbl_trades.insertRow(row)

        pnl_val = float(t.get('net_pnl') or 0.0)
        pnl_color = QColor("#00e676") if pnl_val >= 0 else QColor("#ff5252")

        raw_time = str(t.get('close_time') or t.get('open_time') or '')
        ts_str = raw_time.replace("T", " ")[:19]
        item_ts = QTableWidgetItem(ts_str)

        direction = str(t.get('direction', '')).upper()
        item_dir = QTableWidgetItem(direction)
        item_dir.setForeground(QColor("#2979ff") if direction == "BUY" else QColor("#ff9100"))

        lot_val = float(t.get('lot') or t.get('lot_size') or 0.01)
        item_lot = QTableWidgetItem(f"{lot_val:.2f}L")

        ep_val = float(t.get('entry_price') or 0.0)
        item_ep = QTableWidgetItem(f"${ep_val:,.2f}")

        exit_val = float(t.get('exit_price') or 0.0)
        item_exit = QTableWidgetItem(f"${exit_val:,.2f}")

        sl_val = float(t.get('sl_dist') or 0.0)
        item_sl = QTableWidgetItem(f"${sl_val:.2f}")

        item_pnl = QTableWidgetItem(f"${pnl_val:+,.2f}")
        item_pnl.setForeground(pnl_color)

        bal_val = float(t.get('balance') or t.get('balance_after') or 0.0)
        item_eq = QTableWidgetItem(f"${bal_val:,.2f}")

        bars_val = int(t.get('bars_held') or 1)
        item_bars = QTableWidgetItem(str(bars_val))

        reason_val = str(t.get('exit_reason') or '')
        item_reason = QTableWidgetItem(reason_val)

        for c, itm in enumerate([item_ts, item_dir, item_lot, item_ep, item_exit, item_sl, item_pnl, item_eq, item_bars, item_reason]):
            itm.setTextAlignment(Qt.AlignCenter)
            self.tbl_trades.setItem(row, c, itm)

    def add_closed_trade(self, t: dict):
        self._insert_trade_row(t)
        self.tbl_trades.scrollToBottom()
        lot_val = float(t.get('lot') or t.get('lot_size') or 0.01)
        pnl_val = float(t.get('net_pnl') or 0.0)
        self._log_event(f"[TRADE CLOSED] {t.get('direction')} {lot_val:.2f}L | Net PnL: ${pnl_val:+,.2f} | Reason: {t.get('exit_reason')}")

    def update_telemetry(self, tele: dict):
        probs_str = " | ".join([f"C{i}: {p:.1f}%" for i, p in enumerate(tele.get("probs", []))])
        line = (
            f"[{tele.get('time', '')}] TF: M30 | Session: {tele.get('session', '')} | "
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
