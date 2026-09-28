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
        QMessageBox, QSystemTrayIcon, QMenu, QDialog, QLineEdit
    )
    from PySide6.QtCore import Qt, QTimer, QLocale, Signal, QObject
    from PySide6.QtGui import QFont, QColor, QAction, QIcon, QPixmap, QPainter, QBrush, QPen
except ImportError:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLabel, QPushButton, QComboBox, QSplitter, QFrame, QDoubleSpinBox, 
        QMessageBox, QSystemTrayIcon, QMenu, QDialog, QLineEdit
    )
    from PyQt6.QtCore import Qt, QTimer, QLocale, pyqtSignal as Signal, QObject
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

DEFAULT_CLOUD_SERVER_URL = "https://flowdevframe.streamlit.app"

# -------------------------------------------------------------
# Cloud Server 24/7 Client Synchronizer (Zero-UI Non-Blocking Async Channel)
# -------------------------------------------------------------
import urllib.request, urllib.parse, threading

class CloudServerClient:
    def __init__(self, base_url: str = DEFAULT_CLOUD_SERVER_URL, secret_key: str = "cron_secret_flowdev_falcon_2026"):
        self.base_url = base_url.rstrip("/") if base_url else DEFAULT_CLOUD_SERVER_URL
        self.secret_key = secret_key

    def fetch_state(self) -> Optional[dict]:
        if not self.base_url:
            return None
        url = f"{self.base_url}/?api=state&key={urllib.parse.quote(self.secret_key)}"
        
        # 1. Primary: High-performance HTTPX client with full cookie/redirect support
        try:
            import httpx
            with httpx.Client(follow_redirects=True, timeout=5.0) as client:
                resp = client.get(url, headers={"User-Agent": "FlowdevDesktopCockpit/1.0"})
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and "status" in data:
                            return data
                    except Exception:
                        pass
                    # If status 200 received from Streamlit Cloud, cloud instance is actively running!
                    return {"status": "online", "mode": "cloud_active"}
        except Exception:
            pass

        # 2. Fallback: Standard urllib request
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FlowdevDesktopCockpit/1.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                if resp.status == 200:
                    try:
                        return json.loads(resp.read().decode("utf-8"))
                    except Exception:
                        return {"status": "online", "mode": "cloud_active"}
        except Exception:
            pass
        return None

    def _send_quick_get(self, url: str) -> bool:
        try:
            import httpx
            with httpx.Client(follow_redirects=True, timeout=5.0) as client:
                resp = client.get(url, headers={"User-Agent": "FlowdevDesktopCockpit/1.0"})
                return resp.status_code == 200
        except Exception:
            pass
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FlowdevDesktopCockpit/1.0"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def panic_close(self) -> bool:
        if not self.base_url: return False
        return self._send_quick_get(f"{self.base_url}/?api=panic_close&key={urllib.parse.quote(self.secret_key)}")

    def toggle_agent(self, armed: bool) -> bool:
        if not self.base_url: return False
        return self._send_quick_get(f"{self.base_url}/?api=toggle_agent&armed={1 if armed else 0}&key={urllib.parse.quote(self.secret_key)}")

    def reset(self, capital: float) -> bool:
        if not self.base_url: return False
        return self._send_quick_get(f"{self.base_url}/?api=reset&capital={capital}&key={urllib.parse.quote(self.secret_key)}")

    def update_config(self, lot_mode: str, max_lot: float, symbol: Optional[str] = None) -> bool:
        if not self.base_url: return False
        url = f"{self.base_url}/?api=config&lot_mode={lot_mode}&max_lot={max_lot}&key={urllib.parse.quote(self.secret_key)}"
        if symbol:
            url += f"&symbol={urllib.parse.quote(symbol)}"
        return self._send_quick_get(url)

class CloudSyncWorker(QObject):
    state_ready = Signal(dict)
    sync_failed = Signal()

    def __init__(self, client: CloudServerClient, parent=None):
        super().__init__(parent)
        self.client = client
        self._lock = threading.Lock()
        self._in_progress = False

    def request_sync(self):
        with self._lock:
            if self._in_progress:
                return
            self._in_progress = True

        def _worker():
            try:
                # 1. Primary: Direct high-speed sync from Neon Cloud Database
                parent_win = self.parent()
                if parent_win and hasattr(parent_win, "db"):
                    db_state = parent_win.db.get_operational_state("GLOBAL_STATE")
                    if db_state and isinstance(db_state, dict):
                        db_state["status"] = "online"
                        db_state["broker"] = {
                            "cash": float(db_state.get("cash", 250.0)),
                            "open_position": db_state.get("open_position")
                        }
                        self.state_ready.emit(db_state)
                        return

                # 2. Secondary: Fallback to HTTP client
                state = self.client.fetch_state()
                if state and state.get("status") == "online":
                    self.state_ready.emit(state)
                else:
                    self.sync_failed.emit()
            except Exception:
                self.sync_failed.emit()
            finally:
                with self._lock:
                    self._in_progress = False

        threading.Thread(target=_worker, daemon=True).start()


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
        self.current_symbol: str = "XAUUSD"
        self.current_pair_display: str = "XAU/USD" 
        
        # Cloud Server 24/7 Client State (Zero-UI Non-Blocking Async Channel)
        self.cloud_client = CloudServerClient(DEFAULT_CLOUD_SERVER_URL)
        self.cloud_worker = CloudSyncWorker(self.cloud_client, parent=self)
        self.cloud_worker.state_ready.connect(self._on_cloud_state_ready)
        self.cloud_worker.sync_failed.connect(self._on_cloud_sync_failed)

        self.cloud_sync_timer = QTimer(self)
        self.cloud_sync_timer.setInterval(3000)
        self.cloud_sync_timer.timeout.connect(self.cloud_worker.request_sync)
        self.cloud_sync_timer.start()
        self.cloud_worker.request_sync()

        # Standalone Desktop Cockpit
        self._init_ui()
        self._wire_signals()
        self._apply_role_permissions()

        # Load persisted session state (Auto-Recovery of open trade, balance, symbol, armed status)
        self._load_persisted_state()

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

        self.btn_open_web = QPushButton("OPEN CLOUD WEB APP")
        self.btn_open_web.setToolTip("Open 1:1 Identical Cloud Web Application (Streamlit)")
        self.btn_open_web.setStyleSheet("""
            QPushButton {
                background-color: #1e1b4b; border: 1px solid #4338ca;
                font-size: 10.5px; padding: 4px 10px; font-weight: 700; color: #a5b4fc;
            }
            QPushButton:hover { background-color: #312e81; border-color: #6366f1; color: #ffffff; }
        """)
        self.btn_open_web.clicked.connect(self._open_web_app)

        self.btn_switch_historical = QPushButton("OPEN BACKTEST WORKSTATION")
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

        self.btn_lock = QPushButton("LOCK")
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
        h_layout.addSpacing(12)
        self.lbl_cloud_status = QLabel("[CLOUD: STANDBY 🟡]")
        self.lbl_cloud_status.setStyleSheet("font-size: 10.5px; font-family: monospace; color: #ffd700; font-weight: 700; background-color: #0f172a; padding: 4px 8px; border: 1px solid #1e293b; border-radius: 3px;")
        h_layout.addWidget(self.lbl_cloud_status)
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

        lbl_ctrl = QLabel("MISSION CONTROL & TARGET ASSET")
        lbl_ctrl.setStyleSheet("font-size: 10px; font-weight: 700; color: #8b949e; letter-spacing: 1px;")
        left_layout.addWidget(lbl_ctrl)

        # Target Asset Selector
        left_layout.addWidget(QLabel("SELECT TRADING PAIR:"))
        self.combo_asset = QComboBox()
        self.combo_asset.addItems(["XAU/USD (Spot Gold)", "BTC/USD (Bitcoin Crypto)"])
        self.combo_asset.setStyleSheet("""
            QComboBox {
                background-color: #121824; border: 1px solid #1f293d;
                color: #f0f6fc; font-weight: 700; padding: 5px; font-size: 11px;
                border-radius: 3px;
            }
            QComboBox:hover { border-color: #00bfa5; }
        """)
        self.combo_asset.currentIndexChanged.connect(self._on_pair_changed)
        left_layout.addWidget(self.combo_asset)

        # Tactical Radar Box (Clear Direction & Readiness)
        self.radar_box = QFrame()
        self.radar_box.setStyleSheet("""
            QFrame {
                background-color: #080d16; border: 1px solid #1c2638;
                border-radius: 4px; padding: 6px;
            }
        """)
        radar_layout = QVBoxLayout(self.radar_box)
        radar_layout.setContentsMargins(6, 6, 6, 6)
        radar_layout.setSpacing(3)

        self.lbl_radar_pair = QLabel("TARGET: XAU/USD (Spot Gold)")
        self.lbl_radar_pair.setStyleSheet("color: #38bdf8; font-size: 10.5px; font-weight: 700; font-family: monospace;")
        radar_layout.addWidget(self.lbl_radar_pair)

        self.lbl_radar_status = QLabel("STATUS: [ STANDBY / IDLE ]")
        self.lbl_radar_status.setStyleSheet("color: #f87171; font-size: 10px; font-weight: 700; font-family: monospace;")
        radar_layout.addWidget(self.lbl_radar_status)

        self.lbl_radar_market = QLabel("MARKET: Forex (Weekend Shield Active)")
        self.lbl_radar_market.setStyleSheet("color: #94a3b8; font-size: 9.5px; font-family: monospace;")
        radar_layout.addWidget(self.lbl_radar_market)

        left_layout.addWidget(self.radar_box)

        # Explicit Targeted Trade Toggle
        self.btn_toggle_agent = QPushButton("[ START AGENT TRADE (XAU/USD) ]")
        self.btn_toggle_agent.setStyleSheet("""
            QPushButton {
                background-color: #004d40; border: 1px solid #00bfa5;
                color: #ffffff; font-size: 11px; font-weight: 800; padding: 9px;
                border-radius: 3px; letter-spacing: 0.5px;
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
        # Chart Timeframe -> Feed & UI
        self.chart_widget.timeframe_changed.connect(self._on_timeframe_selected)

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
        self.agent.telemetry_updated.connect(self._on_telemetry_updated)
        self.agent.agent_status_changed.connect(self._on_agent_status_changed)

    def _on_telemetry_updated(self, tele: dict):
        self.journal_widget.update_telemetry(tele)
        try:
            executed = tele.get("action") in ["BUY", "SELL"] and float(tele.get("conf", 0.0)) >= 32.0
            self.db.record_ai_telemetry(tele, executed=executed, source="DESKTOP")
        except Exception:
            pass

    def _on_feed_tick(self, tick: dict):
        self.last_tick = tick
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
        if self.last_tick:
            self.chart_widget.update_tick_and_candle(self.last_tick, candle)
        else:
            self.chart_widget.on_candle_updated(candle)

        if len(self.recent_candles) == 0 or self.recent_candles[-1]["time"] != candle["time"]:
            self.recent_candles.append(candle)
        else:
            self.recent_candles[-1] = candle

        if len(self.recent_candles) > 100:
            self.recent_candles.pop(0)

        # Evaluate on candle update/close
        if candle.get("is_closed", False):
            # Always run AI inference & kinetic OMS on Desktop so operator has instant live telemetry!
            self.agent.on_candle_closed(candle, self.recent_candles)
            if hasattr(self, "cloud_client") and self.cloud_client:
                self._sync_with_cloud_server()

    def _on_timeframe_selected(self, tf_str: str):
        self.feed.set_timeframe(tf_str)
        self.journal_widget._log_event(f"[CHART] Active view timeframe set to {tf_str} | AI strategy locked on M30")

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
        sl_price = float(pos.get("current_sl", pos.get("sl_price", 0.0)))
        tp_price = float(pos.get("current_tp", pos.get("tp_price", 0.0)))
        lot = float(pos.get("lot", 0.01))
        ep = float(pos.get("entry_price", 0.0))
        d = str(pos.get("direction", "BUY"))

        # 1. Update Chart
        try:
            self.chart_widget.display_active_order(pos)
        except Exception as e:
            print(f"[Chart Order Error] {e}")

        # 2. Update Position HUD
        try:
            live_p = self.last_tick.get("bid", ep) if d == "BUY" else self.last_tick.get("ask", ep)
            self.position_hud.update_position(pos, live_p)
        except Exception as e:
            print(f"[HUD Order Error] {e}")

        # 3. Journal Log
        self.journal_widget._log_event(
            f"[ORDER OPENED] {d} {lot:.2f}L @ ${ep:,.2f} | "
            f"SL: ${sl_price:,.2f} | TP: ${tp_price:,.2f}"
        )

        # 4. Record into Unified Audit Database
        try:
            self.db.record_order_opened(pos, source="DESKTOP")
        except Exception as e:
            print(f"[DB Order Error] {e}")

        # 5. Persist state to disk immediately
        self._persist_current_state()

        # 5. Tray Notification
        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            try:
                self.act_pos_info.setText(f"Posisi: {d} {lot:.2f}L @ ${ep:,.2f}")
                self.tray_icon.showMessage(
                    f"NEW TRADE OPENED: {d}",
                    f"{lot:.2f}L @ ${ep:,.2f} | SL: ${sl_price:,.2f} | TP: ${tp_price:,.2f}",
                    QSystemTrayIcon.Information,
                    4000
                )
            except Exception:
                pass

    def _on_order_closed(self, trade: dict):
        self.chart_widget.clear_order_lines()
        self.position_hud.set_standby(True)
        self.journal_widget.add_closed_trade(trade)
        stats = self.broker.get_stats()
        self.metrics_panel.update_metrics(stats)

        # Record into Unified Audit Database
        self.db.record_order_closed(trade)

        # Persist closed state to disk immediately
        self._persist_current_state()

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

        # Persist updated OMS SL to disk immediately
        self._persist_current_state()

        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                f"⚡ {stage}",
                f"{details} | SL Baru: ${ref_price:.2f}",
                QSystemTrayIcon.Information,
                3500
            )

    def _on_cloud_state_ready(self, state: dict):
        self.lbl_cloud_status.setText("[CLOUD: ONLINE 🟢]")
        self.lbl_cloud_status.setStyleSheet("font-size: 10.5px; font-family: monospace; color: #00e676; font-weight: 700; background-color: #0f172a; padding: 4px 8px; border: 1px solid #1e293b; border-radius: 3px;")
        
        b_info = state.get("broker", {})
        if "stats" in b_info:
            self.metrics_panel.update_metrics(b_info["stats"])
        
        if "cash" in b_info:
            self.broker.cash = float(b_info["cash"])

        pos = b_info.get("open_position")
        self.broker.open_position = pos
        if pos:
            self.position_hud.update_position(pos)
            sl_price = pos.get("current_sl", pos.get("sl_price", 0.0))
            self.chart_widget.draw_order_lines(pos["direction"], pos["entry_price"], sl_price, pos["tp_price"])
        else:
            self.position_hud.set_standby(True)
            self.chart_widget.clear_order_lines()

        cloud_armed = state.get("is_armed")
        if cloud_armed is not None and cloud_armed != self.agent.is_armed:
            self.agent.set_armed(cloud_armed)

    def _on_cloud_sync_failed(self):
        self.lbl_cloud_status.setText("[DESKTOP LOCAL 🟡]")
        self.lbl_cloud_status.setStyleSheet("font-size: 10.5px; font-family: monospace; color: #ffd700; font-weight: 700; background-color: #0f172a; padding: 4px 8px; border: 1px solid #1e293b; border-radius: 3px;")

    def _sync_with_cloud_server(self):
        """Non-blocking background sync request."""
        if hasattr(self, "cloud_worker"):
            self.cloud_worker.request_sync()

    def _on_panic_close_requested(self):
        if self.cloud_client:
            def _async_panic():
                try:
                    self.cloud_client.panic_close()
                except Exception:
                    pass
            threading.Thread(target=_async_panic, daemon=True).start()

        if self.broker.open_position is None:
            return
        p = self.last_tick.get("bid" if self.broker.open_position["direction"] == "BUY" else "ask", 0.0)
        self.agent.manual_close(p)


    def _on_pair_changed(self, idx: int):
        pairs = [("XAUUSD", "XAU/USD"), ("BTCUSD", "BTC/USD")]
        sym, disp = pairs[idx]
        self.current_symbol = sym
        self.current_pair_display = disp

        # 1. Update Chart
        self.chart_widget.set_symbol(sym)
        # 2. Update Market Feed
        self.feed.set_symbol(sym)
        # 3. Update Trading Agent
        self.agent.set_symbol(sym)

        self.position_hud.set_standby(True, symbol=disp)
        # 4. Update Radar HUD
        self.lbl_radar_pair.setText(f"TARGET: {'XAU/USD (Spot Gold)' if sym == 'XAUUSD' else 'BTC/USD (Bitcoin Crypto)'}")
        if sym == "BTCUSD":
            self.lbl_radar_market.setText("MARKET: 24/7 Crypto Active (Weekend Trading OK)")
        else:
            self.lbl_radar_market.setText("MARKET: Forex (Weekend Shield Active)")

        self._update_agent_button_text()
        self.journal_widget._log_event(f"[ASSET] Target pair set to {disp} | Operator can start trading")

        # 5. Sync to Cloud Server
        if hasattr(self, "cloud_client") and self.cloud_client:
            threading.Thread(target=lambda: self.cloud_client.update_config(self.broker.lot_mode, self.broker.max_lot, symbol=sym), daemon=True).start()

    def _update_agent_button_text(self):
        if self.agent.is_armed:
            self.btn_toggle_agent.setText(f"[ PAUSE AGENT TRADE ({self.current_pair_display}) ]")
            self.btn_toggle_agent.setStyleSheet("""
                QPushButton { background-color: #4a1515; border: 1px solid #ef4444; color: #fca5a5; font-size: 11px; font-weight: 800; padding: 9px; border-radius: 3px; }
                QPushButton:hover { background-color: #5c1b1b; }
            """)
            self.lbl_radar_status.setText(f"STATUS: [ ARMED & HUNTING ON {self.current_pair_display} ]")
            self.lbl_radar_status.setStyleSheet("color: #00e676; font-size: 10px; font-weight: 700; font-family: monospace;")
            self.lbl_agent_status.setText(f"[AGENT: ARMED ({self.current_symbol})]")
            self.lbl_agent_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #00e676; font-weight: 700;")
        else:
            self.btn_toggle_agent.setText(f"[ START AGENT TRADE ({self.current_pair_display}) ]")
            self.btn_toggle_agent.setStyleSheet("""
                QPushButton { background-color: #004d40; border: 1px solid #00bfa5; color: #ffffff; font-size: 11px; font-weight: 800; padding: 9px; border-radius: 3px; }
                QPushButton:hover { background-color: #00695c; }
            """)
            self.lbl_radar_status.setText("STATUS: [ STANDBY / WAITING OPERATOR ]")
            self.lbl_radar_status.setStyleSheet("color: #f87171; font-size: 10px; font-weight: 700; font-family: monospace;")
            self.lbl_agent_status.setText(f"[AGENT: STANDBY ({self.current_symbol})]")
            self.lbl_agent_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #f87171; font-weight: 700;")

    def _toggle_agent_armed(self):
        new_state = not self.agent.is_armed
        self.agent.set_armed(new_state)
        self._update_agent_button_text()
        self._persist_current_state()
        if hasattr(self, "cloud_client") and self.cloud_client:
            threading.Thread(target=lambda: self.cloud_client.toggle_agent(new_state), daemon=True).start()

    def _on_agent_status_changed(self, armed: bool, text: str):
        self._update_agent_button_text()

    def _on_sizing_changed(self, idx: int):
        self.broker.lot_mode = "dynamic" if idx == 0 else "flat"
        self.frame_max_lot.setVisible(idx == 0)
        if hasattr(self, "cloud_client") and self.cloud_client:
            threading.Thread(target=lambda: self.cloud_client.update_config(self.broker.lot_mode, self.broker.max_lot), daemon=True).start()

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
        self._persist_current_state()

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
            self._persist_current_state()
            if hasattr(self, "cloud_client") and self.cloud_client:
                threading.Thread(target=lambda: self.cloud_client.reset(cap), daemon=True).start()

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

    def _persist_current_state(self):
        """Saves current desktop operational state to Neon Cloud PostgreSQL and local file."""
        try:
            state_data = {
                "cash": float(self.broker.cash),
                "open_position": self.broker.open_position,
                "last_candle_time": getattr(self.agent, "last_evaluated_bar_time", 0),
                "last_session_traded": getattr(self.agent, "last_session_traded", ""),
                "is_armed": bool(self.agent.is_armed),
                "symbol": getattr(self, "current_symbol", "XAUUSD"),
                "lot_mode": getattr(self.broker, "lot_mode", "dynamic"),
                "max_lot": getattr(self.broker, "max_lot", 2.0),
                "updated_at_utc": datetime.now(timezone.utc).isoformat()
            }
            # 1. Primary: Save to Neon Cloud Database
            self.db.save_operational_state(state_data, "GLOBAL_STATE")

            # 2. Local disk backup
            state_file = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\data\cloud_trader_state.json")
            state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, default=str)
        except Exception as e:
            print(f"[Persist State Error] {e}")

    def _load_persisted_state(self):
        """Restores persisted operational state on Desktop startup (Auto-Recovery from Neon DB)."""
        # 1. Primary: Load from Neon Cloud PostgreSQL
        state_data = self.db.get_operational_state("GLOBAL_STATE")

        # 2. Fallback: Local JSON file
        if not state_data:
            state_file = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\data\cloud_trader_state.json")
            if state_file.exists():
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state_data = json.load(f)
                except Exception:
                    pass

        if not state_data:
            try:
                active_row = self.db.get_active_order()
                if active_row:
                    state_data = {
                        "cash": 250.0,
                        "open_position": {
                            "id": active_row.get("trade_id", "ORD-RESTORED"),
                            "direction": active_row.get("direction", "BUY"),
                            "lot": float(active_row.get("lot_size", 0.01)),
                            "entry_price": float(active_row.get("entry_price", 0.0)),
                            "current_sl": float(active_row.get("final_sl") or active_row.get("initial_sl", 0.0)),
                            "initial_sl": float(active_row.get("initial_sl", 0.0)),
                            "sl_price": float(active_row.get("final_sl") or active_row.get("initial_sl", 0.0)),
                            "current_tp": float(active_row.get("tp_price", 0.0)),
                            "tp_price": float(active_row.get("tp_price", 0.0)),
                            "sl_dist": float(active_row.get("sl_dist", 400.0)),
                            "peak_r": float(active_row.get("peak_r", 0.0)),
                            "bars_held": int(active_row.get("bars_held", 1)),
                            "open_time": str(active_row.get("open_time", "")),
                            "friction": float(active_row.get("friction_cost", 0.17)),
                            "reason": f"Restored from DB ({active_row.get('trade_id')})"
                        },
                        "is_armed": True,
                        "symbol": active_row.get("symbol", "BTCUSD")
                    }
            except Exception:
                pass

        if not state_data:
            return

        # 1. Restore Cash & Sizing Parameters
        if "cash" in state_data:
            self.broker.cash = float(state_data["cash"])
            self.spin_capital.setValue(self.broker.cash)

        if "lot_mode" in state_data:
            self.broker.lot_mode = str(state_data["lot_mode"])
            self.combo_sizing.setCurrentIndex(0 if self.broker.lot_mode == "dynamic" else 1)

        if "max_lot" in state_data:
            self.broker.max_lot = float(state_data["max_lot"])
            self.spin_max_lot.setValue(self.broker.max_lot)

        # 2. Restore Symbol Selection
        persisted_sym = str(state_data.get("symbol", "BTCUSD")).upper()
        if persisted_sym in ["BTCUSD", "XAUUSD"]:
            pair_idx = 1 if "BTC" in persisted_sym else 0
            if self.combo_asset.currentIndex() != pair_idx:
                self.combo_asset.setCurrentIndex(pair_idx)
            else:
                self._on_pair_changed(pair_idx)

        # 3. Restore Armed State
        if "is_armed" in state_data:
            self.agent.set_armed(bool(state_data["is_armed"]))
            self._update_agent_button_text()

        # 4. Restore Open Position
        pos = state_data.get("open_position")
        if pos and isinstance(pos, dict) and pos.get("direction"):
            self.broker.open_position = pos
            ref_p = float(pos.get("entry_price", 0.0))
            self.position_hud.update_position(pos, ref_p)
            sl_price = float(pos.get("current_sl", pos.get("sl_price", 0.0)))
            tp_price = float(pos.get("current_tp", pos.get("tp_price", 0.0)))
            self.chart_widget.draw_order_lines(
                pos["direction"], ref_p, sl_price, tp_price, float(pos.get("lot", 0.01))
            )
            self.journal_widget._log_event(
                f"[RECOVERY] Resumed active {pos['direction']} {pos.get('lot', 0.01):.2f}L trade @ ${ref_p:,.2f} | SL: ${sl_price:,.2f}"
            )
            self.metrics_panel.update_metrics(self.broker.get_stats())

    def closeEvent(self, event):
        """Clean institutional exit: stops threads, releases memory, and exits cleanly."""
        try:
            self._persist_current_state()
            if hasattr(self, "cloud_sync_timer") and self.cloud_sync_timer.isActive():
                self.cloud_sync_timer.stop()
            if hasattr(self, "feed") and self.feed is not None:
                self.feed.stop()
        except Exception:
            pass
        event.accept()
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
            QApplication.quit()

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
