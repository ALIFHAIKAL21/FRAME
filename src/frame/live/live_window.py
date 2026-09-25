"""
FLOWDEV FRAME - Dedicated Standalone Live Real-Time Paper Trading Workstation
Engineered specifically for live realtime market simulation without real account risk.
Features sub-millisecond low-latency chart, tick-by-tick execution, 4-Stage Kinetic OMS,
and full AI inference monitoring.
"""

import sys, pathlib, json, ctypes, time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLabel, QPushButton, QComboBox, QSplitter, QFrame, QDoubleSpinBox, 
        QMessageBox, QSystemTrayIcon, QMenu, QDialog
    )
    from PySide6.QtCore import Qt, QTimer, QLocale
    from PySide6.QtGui import QFont, QColor, QAction, QIcon, QPixmap, QPainter, QBrush, QPen
except ImportError:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLabel, QPushButton, QComboBox, QSplitter, QFrame, QDoubleSpinBox, 
        QMessageBox, QSystemTrayIcon, QMenu, QDialog
    )
    from PyQt6.QtCore import Qt, QTimer, QLocale
    from PyQt6.QtGui import QFont, QColor, QAction, QIcon, QPixmap, QPainter, QBrush, QPen

from src.frame.gui.styles import QSS_STYLE
from .paper_broker import LivePaperBroker
from .feed import LiveMarketFeed
from .agent import LiveAgent
from .widgets.live_chart import LiveRealtimeChartWidget
from .widgets.position_hud import LivePositionHUD
from .widgets.live_metrics import LiveMetricsPanel
from .widgets.trade_log import LiveTradeJournalWidget
from .db_audit import TradeAuditDB

class LiveTradingWindow(QMainWindow):
    def __init__(self, operator_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.operator_user = operator_user or {
            "username": "alifhaikal",
            "role": "MASTER_TRADER",
            "display_name": "Alif Haikal (Master Operator)"
        }
        self.setWindowTitle("FLOWDEV FRAME // LIVE REALTIME PAPER TRADER [ZERO ACCOUNT RISK]")
        self.resize(1360, 880)
        self.setStyleSheet(QSS_STYLE)

        # Core Engines & Database
        self.db = TradeAuditDB()
        self.broker = LivePaperBroker(initial_capital=500.0, lot_mode="dynamic", max_lot=2.0)
        self.feed = LiveMarketFeed(symbol="XAUUSD", poll_interval_ms=250)
        self.agent = LiveAgent(broker=self.broker)

        # State
        self.last_tick: dict = {}
        self.recent_candles: list = []

        # Windows Background Keep-Alive & System Tray
        self._enable_windows_keepalive()
        self._init_ui()
        self._init_system_tray()
        self._wire_signals()
        self._apply_role_permissions()

        # Start live market feed
        self.feed.start()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)

        # -------------------------------------------------------------
        # 1. Header Bar
        # -------------------------------------------------------------
        header = QFrame()
        header.setObjectName("header_frame")
        header.setStyleSheet("#header_frame { background-color: #090d14; border: 1px solid #161e2e; }")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 5, 10, 5)

        lbl_brand = QLabel("FLOWDEV FRAME // LIVE REALTIME PAPER TRADING WORKBENCH")
        lbl_brand.setStyleSheet("font-size: 11px; font-weight: 800; color: #d4af37; letter-spacing: 1.2px;")

        self.lbl_feed_status = QLabel("[FEED: INITIALIZING]")
        self.lbl_feed_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #38bdf8; font-weight: 700;")

        self.lbl_agent_status = QLabel("[AGENT: ARMED & HUNTING]")
        self.lbl_agent_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #00e676; font-weight: 700;")

        lbl_hw = QLabel("[RTX 4050 / CUDA 12.6]  [M30 SNIPER]")
        lbl_hw.setStyleSheet("font-size: 11px; font-family: monospace; color: #8b949e;")

        self.btn_open_web = QPushButton("🌐 OPEN CLOUD WEB APP")
        self.btn_open_web.setToolTip("Open 1:1 Identical Cloud Web Application (Streamlit)")
        self.btn_open_web.setStyleSheet("""
            QPushButton {
                background-color: #1e1b4b; border: 1px solid #4338ca;
                font-size: 10.5px; padding: 4px 10px; font-weight: 700; color: #a5b4fc;
            }
            QPushButton:hover { background-color: #312e81; border-color: #6366f1; color: #ffffff; }
        """)
        self.btn_open_web.clicked.connect(self._open_web_app)

        self.btn_switch_historical = QPushButton("📊 OPEN BACKTEST WORKSTATION")
        self.btn_switch_historical.setStyleSheet("""
            QPushButton {
                background-color: #161e2e; border: 1px solid #27334a;
                font-size: 10.5px; padding: 4px 10px; font-weight: 700; color: #cbd5e1;
            }
            QPushButton:hover { background-color: #1f2a3f; border-color: #00bfa5; color: #f0f6fc; }
        """)
        self.btn_switch_historical.clicked.connect(self._open_historical_workstation)

        self.lbl_operator = QLabel(f"👤 {self.operator_user.get('display_name', 'OPERATOR').upper()}")
        self.lbl_operator.setStyleSheet("font-size: 10.5px; font-weight: 800; color: #38bdf8; background-color: #0f172a; padding: 4px 10px; border: 1px solid #1e293b; border-radius: 3px;")

        self.btn_lock = QPushButton("🔒 LOCK")
        self.btn_lock.setToolTip("Lock Workstation Session Immediately")
        self.btn_lock.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; border: 1px solid #334155;
                font-size: 10px; padding: 4px 8px; font-weight: 700; color: #94a3b8; border-radius: 3px;
            }
            QPushButton:hover { background-color: #334155; color: #f8fafc; border-color: #ef4444; }
        """)
        self.btn_lock.clicked.connect(self._lock_session)

        h_layout.addWidget(lbl_brand)
        h_layout.addSpacing(16)
        h_layout.addWidget(self.lbl_feed_status)
        h_layout.addSpacing(12)
        h_layout.addWidget(self.lbl_agent_status)
        h_layout.addStretch()
        h_layout.addWidget(lbl_hw)
        h_layout.addSpacing(12)
        h_layout.addWidget(self.btn_open_web)
        h_layout.addSpacing(8)
        h_layout.addWidget(self.btn_switch_historical)
        h_layout.addSpacing(8)
        h_layout.addWidget(self.lbl_operator)
        h_layout.addSpacing(4)
        h_layout.addWidget(self.btn_lock)
        main_layout.addWidget(header)

        # -------------------------------------------------------------
        # 2. Main Content Splitter
        # -------------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)

        # Left Panel (Controls & Parameters)
        left_panel = QFrame()
        left_panel.setObjectName("left_panel")
        left_panel.setFixedWidth(275)
        left_panel.setStyleSheet("#left_panel { background-color: #0d111a; border: 1px solid #1c2333; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        lbl_ctrl = QLabel("LIVE TRADING ENGINE")
        lbl_ctrl.setStyleSheet("font-size: 10px; font-weight: 700; color: #8b949e; letter-spacing: 1px;")
        left_layout.addWidget(lbl_ctrl)

        # Arm/Disarm Master Switch
        self.btn_toggle_agent = QPushButton("⚡ ARMED (ACTIVELY TRADING)")
        self.btn_toggle_agent.setStyleSheet("""
            QPushButton {
                background-color: #004d40; border: 1px solid #00bfa5;
                color: #ffffff; font-size: 11.5px; font-weight: 800; padding: 8px; letter-spacing: 0.5px;
            }
            QPushButton:hover { background-color: #00695c; border-color: #1de9b6; }
        """)
        self.btn_toggle_agent.clicked.connect(self._toggle_agent_armed)
        left_layout.addWidget(self.btn_toggle_agent)

        # Virtual Account Capital
        left_layout.addWidget(QLabel("Simulated Capital ($ USD):"))
        self.spin_capital = QDoubleSpinBox()
        self.spin_capital.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.spin_capital.setRange(50.0, 1000000.0)
        self.spin_capital.setSingleStep(50.0)
        self.spin_capital.setValue(500.0)
        self.spin_capital.setPrefix("$ ")
        self.spin_capital.setDecimals(2)
        self.spin_capital.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; font-weight: 700; color: #00e676;")
        left_layout.addWidget(self.spin_capital)

        # Quick Preset Buttons
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        for val in [250, 500, 1000, 2500]:
            b = QPushButton(f"${val}")
            b.setStyleSheet("background-color: #121824; border: 1px solid #1f293d; padding: 2px; font-size: 10px; font-family: monospace; color: #8b949e;")
            b.clicked.connect(lambda _, v=val: self._reset_capital_to(float(v)))
            preset_row.addWidget(b)
        left_layout.addLayout(preset_row)

        # Sizing Mode
        left_layout.addWidget(QLabel("Position Sizing Mode:"))
        self.combo_sizing = QComboBox()
        self.combo_sizing.addItems([
            "Dynamic Compounding",
            "Flat 0.01 Lot (Baseline)"
        ])
        self.combo_sizing.currentIndexChanged.connect(self._on_sizing_changed)
        left_layout.addWidget(self.combo_sizing)

        # Max Lot Cap Frame
        self.frame_max_lot = QFrame()
        self.frame_max_lot.setObjectName("frame_max_lot")
        self.frame_max_lot.setStyleSheet("#frame_max_lot { background-color: #080c14; border: 1px solid #161e2e; border-radius: 3px; }")
        ml_layout = QVBoxLayout(self.frame_max_lot)
        ml_layout.setContentsMargins(6, 4, 6, 4)
        ml_layout.setSpacing(2)
        
        row_ml = QHBoxLayout()
        row_ml.addWidget(QLabel("Max Lot Cap:"))
        self.spin_max_lot = QDoubleSpinBox()
        self.spin_max_lot.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.spin_max_lot.setRange(0.05, 50.0)
        self.spin_max_lot.setValue(2.00)
        self.spin_max_lot.setSuffix(" L")
        self.spin_max_lot.setStyleSheet("font-family: monospace; font-size: 11px; font-weight: 700; color: #ffd700;")
        self.spin_max_lot.valueChanged.connect(self._on_max_lot_changed)
        row_ml.addWidget(self.spin_max_lot)
        ml_layout.addLayout(row_ml)
        left_layout.addWidget(self.frame_max_lot)

        # Feed Source Selector
        left_layout.addWidget(QLabel("Market Data Feed:"))
        self.combo_feed = QComboBox()
        self.combo_feed.addItems([
            "Auto (MT5 with Emulator Fallback)",
            "Native MetaTrader 5 Only",
            "Realtime Market Emulator (24/7)"
        ])
        self.combo_feed.currentIndexChanged.connect(self._on_feed_changed)
        left_layout.addWidget(self.combo_feed)

        # Telemetry info box
        self.lbl_feed_info = QLabel("Ticks: 0 | Latency: 0.0 ms")
        self.lbl_feed_info.setStyleSheet("background-color: #080a10; border: 1px solid #141c2c; padding: 4px; font-size: 10px; font-family: monospace; color: #78909c;")
        left_layout.addWidget(self.lbl_feed_info)

        # Locked Kinetic OMS Specs
        left_layout.addSpacing(4)
        lbl_oms = QLabel("ACTIVE KINETIC OMS RULES")
        lbl_oms.setStyleSheet("font-size: 9.5px; font-weight: 700; color: #8b949e; letter-spacing: 0.8px;")
        left_layout.addWidget(lbl_oms)

        oms_box = QLabel(
            "• Stage 1 : Micro-BE (+0.75R)\n"
            "• Stage 2 : Smart Ratchet (+1.2R / 0.5R)\n"
            "• Stage 3 : Dynamic Trailing (+1.5R)\n"
            "• Stage 4 : Stale Decay (Bar 6 / -0.45R)\n"
            "• Max TP  : +2.7R ($/R Ceiling)\n"
            "• Barrier : 12 Bars (6h Cutoff)\n"
            "• Friction: Scaled Bid/Ask Spread"
        )
        oms_box.setObjectName("oms_box")
        oms_box.setStyleSheet("#oms_box { background-color: #080a10; border: 1px solid #181f2b; padding: 6px; color: #78909c; font-family: monospace; font-size: 9.5px; line-height: 1.35; }")
        left_layout.addWidget(oms_box)

        left_layout.addStretch()

        # Reset Session Button
        self.btn_reset = QPushButton("RESET PAPER ACCOUNT")
        self.btn_reset.setStyleSheet("background-color: #1a1622; border: 1px solid #3b2238; color: #f87171; font-weight: 700; padding: 6px; font-size: 10.5px;")
        self.btn_reset.clicked.connect(self._reset_account_dialog)
        left_layout.addWidget(self.btn_reset)

        splitter.addWidget(left_panel)

        # Right Main Stage
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Top: Live Metrics Panel
        self.metrics_panel = LiveMetricsPanel()
        right_layout.addWidget(self.metrics_panel)

        # Upper: Real-Time Candlestick Chart
        self.chart_widget = LiveRealtimeChartWidget()
        right_layout.addWidget(self.chart_widget, stretch=3)

        # Middle: Active Open Position HUD
        self.position_hud = LivePositionHUD()
        self.position_hud.close_requested.connect(self._on_panic_close_requested)
        right_layout.addWidget(self.position_hud)

        # Lower: Trade Journal & Telemetry Tabs
        self.journal_widget = LiveTradeJournalWidget()
        right_layout.addWidget(self.journal_widget, stretch=2)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

    def _wire_signals(self):
        # Feed -> UI & Agent
        self.feed.tick_received.connect(self._on_feed_tick)
        self.feed.candle_updated.connect(self._on_feed_candle)
        self.feed.connection_changed.connect(self._on_feed_connection_changed)
        self.feed.history_loaded.connect(self._on_feed_history_loaded)

        # Agent -> UI
        self.agent.order_opened.connect(self._on_order_opened)
        self.agent.order_closed.connect(self._on_order_closed)
        self.agent.position_updated.connect(self._on_position_updated)
        self.agent.oms_event.connect(self._on_oms_event)
        self.agent.telemetry_updated.connect(self.journal_widget.update_telemetry)
        self.agent.agent_status_changed.connect(self._on_agent_status_changed)

    def _on_feed_tick(self, tick: dict):
        self.last_tick = tick
        self.chart_widget.on_tick(tick)
        self.agent.on_tick(tick)

        # Update telemetry strip
        self.lbl_feed_info.setText(
            f"Tick #{self.feed.tick_count:,} | "
            f"Latency: {tick.get('latency_ms', 0):.1f}ms | "
            f"Sprd: ${tick.get('spread', 0):.2f}"
        )

        # Refresh metrics floating equity
        stats = self.broker.get_stats()
        dt_utc = datetime.fromtimestamp(tick.get("time", time.time()), timezone.utc)
        cur_sess = self.agent.get_current_session(dt_utc)
        self.metrics_panel.update_metrics(stats, current_session=cur_sess or "Off-Session")

    def _on_feed_candle(self, candle: dict):
        self.chart_widget.on_candle_updated(candle)
        if len(self.recent_candles) == 0 or self.recent_candles[-1]["time"] != candle["time"]:
            self.recent_candles.append(candle)
        else:
            self.recent_candles[-1] = candle

        if len(self.recent_candles) > 100:
            self.recent_candles.pop(0)

        # Evaluate on candle update/close
        if candle.get("is_closed", False):
            self.agent.on_candle_closed(candle, self.recent_candles)

    def _on_feed_connection_changed(self, is_connected: bool, source: str, msg: str):
        if is_connected:
            self.lbl_feed_status.setText(f"[FEED: {source} (ACTIVE)]")
            self.lbl_feed_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #00e676; font-weight: 700;")
        else:
            self.lbl_feed_status.setText("[FEED: DISCONNECTED]")
            self.lbl_feed_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #ff5252; font-weight: 700;")
        self.journal_widget._log_event(f"[FEED] {source} -> {msg}")

    def _on_feed_history_loaded(self, candles: list):
        self.recent_candles = list(candles)
        self.chart_widget.set_initial_candles(candles)
        self.journal_widget._log_event(f"[FEED] Loaded {len(candles)} historical M30 bars to seed chart.")

    def _on_order_opened(self, pos: dict):
        self.chart_widget.display_active_order(pos)
        self.position_hud.update_position(pos, self.last_tick.get("bid", pos["entry_price"]))
        self.journal_widget._log_event(
            f"[ORDER OPENED] {pos['direction']} {pos['lot']:.2f}L @ ${pos['entry_price']:,.2f} | "
            f"SL: ${pos['current_sl']:,.2f} | TP: ${pos['current_tp']:,.2f}"
        )
        # Record into Unified Audit Database
        self.db.record_order_opened(pos, source="DESKTOP")

        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            self.act_pos_info.setText(f"📊 Posisi: {pos['direction']} {pos['lot']:.2f}L @ ${pos['entry_price']:.2f}")
            self.tray_icon.showMessage(
                f"🟢 NEW TRADE OPENED: {pos['direction']}",
                f"{pos['lot']:.2f}L @ ${pos['entry_price']:,.2f} | SL: ${pos['current_sl']:,.2f} | TP: ${pos['current_tp']:,.2f}",
                QSystemTrayIcon.Information,
                4000
            )

    def _on_order_closed(self, trade: dict):
        self.chart_widget.clear_order_lines()
        self.position_hud.set_standby(True)
        self.journal_widget.add_closed_trade(trade)
        stats = self.broker.get_stats()
        self.metrics_panel.update_metrics(stats)

        # Record into Unified Audit Database
        self.db.record_order_closed(trade)

        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            self.act_pos_info.setText("📊 Posisi: Standby (Belum Ada Order)")
            pnl = trade.get('net_pnl', 0.0)
            res_str = "PROFIT 💰" if pnl >= 0 else "LOSS 🔻"
            self.tray_icon.showMessage(
                f"🏁 TRADE CLOSED [{res_str}]",
                f"Net PnL: {'+' if pnl>=0 else ''}${pnl:.2f} USD ({trade.get('exit_reason', 'Closed')})",
                QSystemTrayIcon.Information,
                4500
            )

    def _on_position_updated(self, pos: dict):
        live_p = self.last_tick.get("bid", pos["entry_price"]) if pos["direction"] == "BUY" else self.last_tick.get("ask", pos["entry_price"])
        self.position_hud.update_position(pos, live_p)

    def _on_oms_event(self, stage: str, details: str, ref_price: float):
        self.journal_widget.log_oms_event(stage, details, ref_price)
        if "Micro-Breakeven" in stage:
            self.chart_widget.update_sl_line(ref_price, "MICRO-BE")
        elif "Ratchet" in stage:
            self.chart_widget.update_sl_line(ref_price, "RATCHET +0.5R")
        elif "Trailing" in stage:
            self.chart_widget.update_sl_line(ref_price, "TRAILING")
        elif "Stale Decay" in stage:
            self.chart_widget.update_sl_line(ref_price, "STALE -0.45R")

        # Record into Unified Audit Database
        trade_id = self.broker.open_position.get("id", "") if self.broker.open_position else ""
        self.db.record_oms_event(trade_id, stage, details, ref_price)

        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                f"⚡ {stage}",
                f"{details} | SL Baru: ${ref_price:.2f}",
                QSystemTrayIcon.Information,
                3500
            )

    def _on_panic_close_requested(self):
        if self.broker.open_position is None:
            return
        p = self.last_tick.get("bid" if self.broker.open_position["direction"] == "BUY" else "ask", 0.0)
        self.agent.manual_close(p)

    def _toggle_agent_armed(self):
        new_state = not self.agent.is_armed
        self.agent.set_armed(new_state)

    def _on_agent_status_changed(self, armed: bool, text: str):
        if armed:
            self.btn_toggle_agent.setText("⚡ ARMED (ACTIVELY TRADING)")
            self.btn_toggle_agent.setStyleSheet("""
                QPushButton { background-color: #004d40; border: 1px solid #00bfa5; color: #ffffff; font-size: 11.5px; font-weight: 800; padding: 8px; }
                QPushButton:hover { background-color: #00695c; }
            """)
            self.lbl_agent_status.setText("[AGENT: ARMED & HUNTING]")
            self.lbl_agent_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #00e676; font-weight: 700;")
        else:
            self.btn_toggle_agent.setText("⏸ PAUSED (DISARMED)")
            self.btn_toggle_agent.setStyleSheet("""
                QPushButton { background-color: #4a1515; border: 1px solid #ef4444; color: #fca5a5; font-size: 11.5px; font-weight: 800; padding: 8px; }
                QPushButton:hover { background-color: #5c1b1b; }
            """)
            self.lbl_agent_status.setText("[AGENT: PAUSED]")
            self.lbl_agent_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #f87171; font-weight: 700;")

    def _on_sizing_changed(self, idx: int):
        self.broker.lot_mode = "dynamic" if idx == 0 else "flat"
        self.frame_max_lot.setVisible(idx == 0)

    def _on_max_lot_changed(self, val: float):
        self.broker.max_lot = float(val)

    def _on_feed_changed(self, idx: int):
        types = ["auto", "mt5", "emulator"]
        self.feed.set_source(types[idx])

    def _reset_capital_to(self, val: float):
        self.spin_capital.setValue(val)
        self.broker.reset(new_capital=val)
        self.metrics_panel.update_metrics(self.broker.get_stats())
        self.journal_widget._log_event(f"[ACCOUNT] Reset simulated capital to ${val:,.2f} USD")

    def _reset_account_dialog(self):
        ret = QMessageBox.question(
            self, "Reset Paper Account",
            "Are you sure you want to reset all simulated paper trades and balance?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            cap = float(self.spin_capital.value())
            self.broker.reset(new_capital=cap)
            self.position_hud.set_standby(True)
            self.chart_widget.clear_order_lines()
            self.journal_widget.tbl_trades.setRowCount(0)
            self.metrics_panel.update_metrics(self.broker.get_stats())
            self.journal_widget._log_event(f"[ACCOUNT] Full paper account reset to ${cap:,.2f} USD")

    def _open_web_app(self):
        import webbrowser
        webbrowser.open("http://localhost:8501")

    def _open_historical_workstation(self):
        from src.frame.gui.app import MainWindow
        if not hasattr(self, "historical_win") or self.historical_win is None:
            self.historical_win = MainWindow()
        self.historical_win.show()
        self.historical_win.raise_()
        self.historical_win.activateWindow()

    def _enable_windows_keepalive(self):
        try:
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_AWAYMODE_REQUIRED = 0x00000040
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
        except Exception:
            pass

    def _disable_windows_keepalive(self):
        try:
            ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass

    def _create_tray_icon_pixmap(self) -> QIcon:
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#090d14"))
        p.setPen(QColor("#d4af37"))
        p.drawRoundedRect(4, 4, 56, 56, 12, 12)

        # Falcon F
        font = QFont("Arial", 28, QFont.Bold)
        p.setFont(font)
        p.setPen(QColor("#d4af37"))
        p.drawText(pm.rect(), Qt.AlignCenter, "F")

        # Green pulse dot
        p.setBrush(QColor("#00e676"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(44, 44, 14, 14)
        p.end()
        return QIcon(pm)

    def _init_system_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return

        icon = self._create_tray_icon_pixmap()
        self.setWindowIcon(icon)

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("FLOWDEV FRAME // Live Realtime Trader (Active Online)")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #0b0f19; border: 1px solid #1e293b;
                color: #e2e8f0; font-family: sans-serif; font-size: 11px; padding: 4px;
            }
            QMenu::item { padding: 6px 16px; border-radius: 3px; }
            QMenu::item:selected { background-color: #1e293b; color: #38bdf8; }
            QMenu::separator { height: 1px; background-color: #1e293b; margin: 4px 6px; }
        """)

        act_show = menu.addAction("🖥️ Tampilkan Jendela Utama (Show Window)")
        act_show.triggered.connect(self._restore_from_tray)

        menu.addSeparator()

        self.act_status = menu.addAction("🦅 Agent: ARMED & HUNTING")
        self.act_status.setEnabled(False)

        self.act_pos_info = menu.addAction("📊 Posisi: Standby (Belum Ada Order)")
        self.act_pos_info.setEnabled(False)

        menu.addSeparator()

        act_pause = menu.addAction("⏸️ Pause / Resume Agent")
        act_pause.triggered.connect(self._toggle_agent_armed)

        act_panic = menu.addAction("⚡ Panic Close Active Position")
        act_panic.triggered.connect(self._on_panic_close_requested)

        menu.addSeparator()

        act_backtest = menu.addAction("📈 Buka Backtest Workstation")
        act_backtest.triggered.connect(self._open_historical_workstation)

        menu.addSeparator()

        act_quit = menu.addAction("🚪 Tutup Aplikasi Total (Exit Completely)")
        act_quit.triggered.connect(self._force_quit)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self._restore_from_tray()

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "FLOWDEV FRAME // Tetap Online",
                "Jendela desktop disembunyikan. Bot tetap berjalan di background secara realtime!",
                QSystemTrayIcon.Information,
                3000
            )
        else:
            self._force_quit()

    def _force_quit(self):
        self._disable_windows_keepalive()
        self.feed.stop()
        if hasattr(self, "tray_icon") and self.tray_icon is not None:
            self.tray_icon.hide()
        QApplication.quit()

    def _apply_role_permissions(self):
        is_auditor = self.operator_user.get("role") == "AUDITOR_VIEWER"
        if is_auditor:
            self.btn_reset.setEnabled(False)
            self.btn_reset.setToolTip("[AUDITOR READ-ONLY] Reset akun hanya dapat dilakukan oleh MASTER_TRADER.")
            self.btn_toggle_agent.setEnabled(False)
            self.btn_toggle_agent.setToolTip("[AUDITOR READ-ONLY] Switch agent dibatasi untuk MASTER_TRADER.")
            if hasattr(self, "position_hud") and hasattr(self.position_hud, "btn_close"):
                self.position_hud.btn_close.setEnabled(False)
                self.position_hud.btn_close.setToolTip("[AUDITOR READ-ONLY] Panic close posisi dibatasi untuk MASTER_TRADER.")
        else:
            self.btn_reset.setEnabled(True)
            self.btn_reset.setToolTip("")
            self.btn_toggle_agent.setEnabled(True)
            self.btn_toggle_agent.setToolTip("")
            if hasattr(self, "position_hud") and hasattr(self.position_hud, "btn_close"):
                self.position_hud.btn_close.setEnabled(True)
                self.position_hud.btn_close.setToolTip("")

    def _lock_session(self):
        from src.frame.security.auth_dialog import DesktopAuthGatekeeper
        self.hide()
        dialog = DesktopAuthGatekeeper(parent=self, is_lock_screen=True)
        if dialog.exec() == QDialog.Accepted:
            self.operator_user = dialog.authenticated_user or self.operator_user
            self.lbl_operator.setText(f"👤 {self.operator_user.get('display_name', 'OPERATOR').upper()}")
            self._apply_role_permissions()
            self.showNormal()
            self.raise_()
            self.activateWindow()
        else:
            self._force_quit()

def run_live_app():
    from src.frame.security.auth_dialog import DesktopAuthGatekeeper
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Try restoring trusted session or authenticate
    user = DesktopAuthGatekeeper.try_restore_session()
    if not user:
        gate = DesktopAuthGatekeeper()
        if gate.exec() != QDialog.Accepted:
            sys.exit(0)
        user = gate.authenticated_user

    win = LiveTradingWindow(operator_user=user)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_live_app()
