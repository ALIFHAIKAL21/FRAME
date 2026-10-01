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
                    try:
                        self.sync_failed.emit()
                    except Exception:
                        pass
            except (RuntimeError, Exception):
                try:
                    self.sync_failed.emit()
                except Exception:
                    pass
            finally:
                with self._lock:
                    self._in_progress = False

        threading.Thread(target=_worker, daemon=True).start()


class LiveTradingWindow(QMainWindow):
    # [PERF] Signals used to safely apply restored state & trades on main thread after background DB load
    _state_loaded = Signal(dict)
    _trades_loaded = Signal(list)

    @property
    def active_broker(self) -> LivePaperBroker:
        return self.broker

    @property
    def active_agent(self) -> LiveAgent:
        return self.agent

    # Backward compatibility aliases
    @property
    def broker_a(self) -> LivePaperBroker:
        return self.broker

    @property
    def broker_b(self) -> LivePaperBroker:
        return self.broker

    @property
    def agent_a(self) -> LiveAgent:
        return self.agent

    @property
    def agent_b(self) -> LiveAgent:
        return self.agent

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
        # [PERF] TradeAuditDB init deferred to background thread — prevents 2-5s Neon TCP block on main thread
        self.db = None  # Will be set by background thread

        # Core Quantitative Trading Engine:
        # Strictly Single Locked Final Model (Pretrained 15ch MOMENT-1-large Foundation Model)
        self.broker = LivePaperBroker(initial_capital=250.0, lot_mode="dynamic", max_lot=2.0, session_id="MOMENT_LOCKED_PROD")
        self.agent = LiveAgent(broker=self.broker, session_id="MOMENT_LOCKED_PROD", session_name="MOMENT-1-large (Locked Production)")
        self.active_session: str = "MOMENT_LOCKED"

        self.feed = LiveMarketFeed(symbol="XAUUSD", poll_interval_ms=250)

        # State
        self.last_tick: dict = {}
        self.recent_candles: list = []
        self.m30_candles: list = []
        self.current_symbol: str = "XAUUSD"
        self.current_pair_display: str = "XAU/USD"
        # [PERF] Throttle tick UI update to 1Hz (instead of every 250ms tick)
        self._last_tick_ui_time: float = 0.0

        # Cloud Server 24/7 Client State (Zero-UI Non-Blocking Async Channel)
        self.cloud_client = CloudServerClient(DEFAULT_CLOUD_SERVER_URL)
        self.cloud_worker = CloudSyncWorker(self.cloud_client, parent=self)
        self.cloud_worker.state_ready.connect(self._on_cloud_state_ready)
        self.cloud_worker.sync_failed.connect(self._on_cloud_sync_failed)

        # [PERF] Cloud sync interval increased 3s -> 10s to reduce Neon query load
        self.cloud_sync_timer = QTimer(self)
        self.cloud_sync_timer.setInterval(10000)
        self.cloud_sync_timer.timeout.connect(self.cloud_worker.request_sync)
        self.cloud_sync_timer.start()

        # Standalone Desktop Cockpit
        self._init_ui()
        self._wire_signals()
        self._apply_role_permissions()

        # [PERF] DB init + data load in background; UI apply happens on main thread via signal
        self._state_loaded.connect(self._apply_persisted_state)
        self._trades_loaded.connect(self._apply_persisted_trades)

        def _bg_init_db():
            try:
                db = TradeAuditDB()
                self.db = db
                # Load state DATA only (no Qt widgets touched here)
                state_data = self._fetch_persisted_state_data()
                if state_data:
                    # Emit signal -> main thread will apply UI changes safely
                    self._state_loaded.emit(state_data)

                # Load closed trades from DB
                trades_data = self._fetch_persisted_trades_data(db=db)
                if trades_data:
                    self._trades_loaded.emit(trades_data)

                # Trigger first cloud sync after DB ready
                self.cloud_worker.request_sync()
            except Exception as e:
                print(f"[PERF] Background DB init error: {e}")

        threading.Thread(target=_bg_init_db, daemon=True).start()

        # Start live market feed
        self.feed.start()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(4)

        # -------------------------------------------------------------
        # 1. Header Bar (Controlled by Master Cockpit)
        # -------------------------------------------------------------
        self.header_frame = QFrame()
        self.header_frame.setObjectName("header_frame")
        self.header_frame.setFixedHeight(46)
        self.header_frame.setStyleSheet("#header_frame { background-color: #06090e; border: 1px solid #1a2230; border-radius: 4px; }")
        h_layout = QHBoxLayout(self.header_frame)
        h_layout.setContentsMargins(12, 2, 12, 2)
        h_layout.setSpacing(8)

        lbl_brand = QLabel("FLOWDEV // LIVE REALTIME TRADER")
        lbl_brand.setStyleSheet("font-size: 11px; font-weight: 800; color: #d4af37; letter-spacing: 1px;")

        self.lbl_feed_status = QLabel("[FEED: INITIALIZING]")
        self.lbl_feed_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #38bdf8; font-weight: 700;")

        self.lbl_agent_status = QLabel("[AGENT: STANDBY]")
        self.lbl_agent_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #f87171; font-weight: 700;")

        self.lbl_cloud_status = QLabel("[CLOUD: ONLINE 🟢]")
        self.lbl_cloud_status.setStyleSheet("font-size: 10.5px; font-family: monospace; color: #00e676; font-weight: 700; background-color: #080808; padding: 4px 8px; border: 1px solid #262626; border-radius: 3px;")

        h_layout.addWidget(lbl_brand)
        h_layout.addWidget(self.lbl_feed_status)
        h_layout.addWidget(self.lbl_agent_status)
        h_layout.addWidget(self.lbl_cloud_status)
        h_layout.addStretch()

        self.btn_open_web = QPushButton("CLOUD APP")
        self.btn_open_web.setStyleSheet("background-color: #111111; border: 1px solid #303030; font-size: 10px; padding: 4px 8px; font-weight: 700; color: #d1d5db;")
        self.btn_open_web.clicked.connect(self._open_web_app)
        h_layout.addWidget(self.btn_open_web)

        self.btn_switch_historical = QPushButton("BACKTEST")
        self.btn_switch_historical.setStyleSheet("background-color: #111111; border: 1px solid #303030; font-size: 10px; padding: 4px 8px; font-weight: 700; color: #cbd5e1;")
        self.btn_switch_historical.clicked.connect(self._open_historical_workstation)
        h_layout.addWidget(self.btn_switch_historical)

        main_layout.addWidget(self.header_frame)

        # Backward compatibility placeholders
        self.session_bar = QFrame()
        self.lbl_model_badge = QLabel()
        self.lbl_model_stats = QLabel()
        self.btn_arm_both = QPushButton()
        self.btn_standby_both = QPushButton()
        self.btn_tab_b = QPushButton()
        self.btn_tab_a = QPushButton()

        # -------------------------------------------------------------
        # 2. Main Content Splitter (Left Sidebar Controls + Right Main Stage)
        # -------------------------------------------------------------
        splitter = QSplitter(Qt.Horizontal)

        # Left Control Panel (Styled identically to Backtest Simulation Controls)
        left_panel = QFrame()
        left_panel.setObjectName("left_panel")
        left_panel.setFixedWidth(275)
        left_panel.setStyleSheet("#left_panel { background-color: #0d111a; border: 1px solid #1c2333; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        lbl_ctrl_title = QLabel("AGENT EXECUTION CONTROLS")
        lbl_ctrl_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #8b949e; letter-spacing: 1px;")
        left_layout.addWidget(lbl_ctrl_title)

        # 0. Locked Neural Architecture
        left_layout.addWidget(QLabel("Locked Neural Architecture:"))
        self.combo_model = QComboBox()
        self.combo_model.addItems([
            "MOMENT-1-large Pretrained [LOCKED PRODUCTION]"
        ])
        self.combo_model.setEnabled(False)
        self.combo_model.setStyleSheet("color: #00e676; font-weight: 800; background-color: #05140d; border: 1px solid #059669;")
        left_layout.addWidget(self.combo_model)

        # 1. Target Trading Pair
        left_layout.addWidget(QLabel("Target Trading Pair:"))
        self.combo_asset = QComboBox()
        self.combo_asset.addItems(["XAU/USD (Spot Gold)", "BTC/USD (Bitcoin Crypto)"])
        self.combo_asset.currentIndexChanged.connect(self._on_pair_changed)
        left_layout.addWidget(self.combo_asset)

        # 2. Account Capital ($250 - $500 USD)
        left_layout.addWidget(QLabel("Account Capital ($250 - $500 USD):"))
        self.spin_capital = QDoubleSpinBox()
        self.spin_capital.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.spin_capital.setRange(250.0, 500.0)
        self.spin_capital.setSingleStep(50.0)
        self.spin_capital.setValue(250.0)
        self.spin_capital.setPrefix("$ ")
        self.spin_capital.setDecimals(2)
        self.spin_capital.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px; font-weight: 700; color: #00e676;")
        left_layout.addWidget(self.spin_capital)

        # Quick Preset Buttons: $250 and $500
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for val, lot in [(250, 0.02), (500, 0.04)]:
            btn = QPushButton(f"${val}")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #121824;
                    border: 1px solid #1f293d;
                    padding: 3px 2px;
                    font-size: 10px;
                    font-family: monospace;
                    color: #8b949e;
                }
                QPushButton:hover {
                    background-color: #1a2333;
                    border-color: #00bfa5;
                    color: #f0f6fc;
                }
            """)
            btn.clicked.connect(lambda _, v=val, l=lot: (self._reset_capital_to(float(v)), self.spin_max_lot.setValue(l)))
            preset_row.addWidget(btn)
        left_layout.addLayout(preset_row)

        # 3. Position Sizing Mode
        left_layout.addWidget(QLabel("Position Sizing Mode:"))
        self.combo_sizing = QComboBox()
        self.combo_sizing.addItems([
            "Dynamic Compounding",
            "Flat 0.01 Lot (Baseline)"
        ])
        self.combo_sizing.currentIndexChanged.connect(self._on_sizing_changed)
        left_layout.addWidget(self.combo_sizing)

        # 4. Max Lot Cap Frame
        self.frame_max_lot = QFrame()
        self.frame_max_lot.setObjectName("frame_max_lot")
        self.frame_max_lot.setStyleSheet("#frame_max_lot { background-color: #080c14; border: 1px solid #161e2e; border-radius: 3px; }")
        max_lot_layout = QVBoxLayout(self.frame_max_lot)
        max_lot_layout.setContentsMargins(6, 4, 6, 4)
        max_lot_layout.setSpacing(3)

        row_cap = QHBoxLayout()
        row_cap.addWidget(QLabel("Max Lot Cap:"))
        self.spin_max_lot = QDoubleSpinBox()
        self.spin_max_lot.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        self.spin_max_lot.setRange(0.01, 0.05)
        self.spin_max_lot.setSingleStep(0.01)
        self.spin_max_lot.setValue(0.02)
        self.spin_max_lot.setSuffix(" L")
        self.spin_max_lot.setDecimals(2)
        self.spin_max_lot.setStyleSheet("font-family: monospace; font-size: 11px; font-weight: 700; color: #ffd700;")
        self.spin_max_lot.valueChanged.connect(self._on_max_lot_changed)
        row_cap.addWidget(self.spin_max_lot)
        max_lot_layout.addLayout(row_cap)

        lbl_formula = QLabel("Rule: Trend Gate (EMA200) + Daily Breaker + Auto Cap Locked")
        lbl_formula.setStyleSheet("color: #78909c; font-size: 9.0px; font-family: monospace;")
        max_lot_layout.addWidget(lbl_formula)
        left_layout.addWidget(self.frame_max_lot)

        # 5. Market Data Feed
        left_layout.addWidget(QLabel("Market Data Feed:"))
        self.combo_feed = QComboBox()
        self.combo_feed.addItems([
            "Auto (MT5 with Emulator Fallback)",
            "Native MetaTrader 5 Only",
            "Realtime Market Emulator (24/7)"
        ])
        self.combo_feed.currentIndexChanged.connect(self._on_feed_changed)
        left_layout.addWidget(self.combo_feed)

        # 6. Locked OMS Specs
        left_layout.addSpacing(4)
        lbl_oms_spec = QLabel("LOCKED OMS PARAMETERS")
        lbl_oms_spec.setStyleSheet("font-size: 10px; font-weight: 700; color: #8b949e; letter-spacing: 1px;")
        left_layout.addWidget(lbl_oms_spec)

        oms_box = QLabel(
            "• Model   : MOMENT-1-large (15-Ch)\n"
            "• Sizing  : Dual-Mode (Cap 0.02L)\n"
            "• Micro-BE: +0.75R (Off if ATR<10p)\n"
            "• Ratchet : +1.2R (0.5R)\n"
            "• Trail   : +1.5R (0.6R)\n"
            "• Decay   : Adapt (9b <14p / 6b >=14p)\n"
            "• Dyn TP  : 1.0R (<18p) / 2.7R (>=18p)\n"
            "• Vol Gate: F3(13p) + F6(20p) + F7(65p)\n"
            "• Barrier : 12 Bars (6h) / Macro EMA200"
        )
        oms_box.setObjectName("oms_box")
        oms_box.setStyleSheet("#oms_box { background-color: #080a10; border: 1px solid #181f2b; padding: 6px; color: #78909c; font-family: monospace; font-size: 10px; line-height: 1.3; }")
        left_layout.addWidget(oms_box)

        left_layout.addStretch()

        # Primary Action Button (Matches EXECUTE SIMULATION in Backtest)
        self.btn_toggle_agent = QPushButton("⚡ ARM AGENT (LIVE)")
        self.btn_toggle_agent.setStyleSheet("""
            QPushButton {
                background-color: #004d40;
                border: 1px solid #00bfa5;
                color: #ffffff;
                font-size: 12px;
                font-weight: 700;
                padding: 8px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: #00695c;
                border-color: #1de9b6;
            }
        """)
        self.btn_toggle_agent.clicked.connect(self._toggle_agent_armed)
        left_layout.addWidget(self.btn_toggle_agent)

        # Secondary Action Button (Matches EXPORT REPORT in Backtest)
        self.btn_reset = QPushButton("RESET PAPER ACCOUNT")
        self.btn_reset.setStyleSheet("background-color: #161e2e; border: 1px solid #27334a; padding: 7px; font-size: 11px; color: #f87171;")
        self.btn_reset.clicked.connect(self._reset_account_dialog)
        left_layout.addWidget(self.btn_reset)

        # Placeholders for radar widgets if referenced
        self.lbl_radar_pair = QLabel()
        self.lbl_radar_status = QLabel()
        self.lbl_radar_market = QLabel()
        self.lbl_feed_info = QLabel()

        splitter.addWidget(left_panel)

        # Right Main Stage Tabs & Panels
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Top: Live Metrics Panel (Identical 7-Card Grid to Backtest)
        self.metrics_panel = LiveMetricsPanel()
        right_layout.addWidget(self.metrics_panel)

        # Upper: Real-Time Candlestick Chart
        self.chart_widget = LiveRealtimeChartWidget()
        right_layout.addWidget(self.chart_widget, stretch=5)

        # Middle: Active Open Position HUD
        self.position_hud = LivePositionHUD()
        self.position_hud.close_requested.connect(self._on_panic_close_requested)
        right_layout.addWidget(self.position_hud)

        # Lower: Trade Journal & Telemetry Tabs
        self.journal_widget = LiveTradeJournalWidget()
        self.journal_widget.setMinimumHeight(240)
        right_layout.addWidget(self.journal_widget, stretch=3)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, stretch=1)

        # 3. Bottom Terminal / Status Strip (Matches Backtest bottom_frame)
        self.bottom_frame = QFrame()
        self.bottom_frame.setObjectName("bottom_frame")
        self.bottom_frame.setStyleSheet("#bottom_frame { background-color: #080a0f; border: 1px solid #161e2e; }")
        b_layout = QHBoxLayout(self.bottom_frame)
        b_layout.setContentsMargins(8, 4, 8, 4)
        b_layout.setSpacing(8)

        self.lbl_status_line = QLabel("[ENGINE] MOMENT-1-large Production Ready | Feed: Initializing... | Cloud: Online")
        self.lbl_status_line.setStyleSheet("font-family: monospace; font-size: 10px; color: #8b949e;")
        b_layout.addWidget(self.lbl_status_line)
        b_layout.addStretch()

        main_layout.addWidget(self.bottom_frame)

    def _wire_signals(self):
        # Chart Timeframe -> Feed & UI
        self.chart_widget.timeframe_changed.connect(self._on_timeframe_selected)

        # Feed -> UI & Dual Agents (Synchronous Market Dispatch)
        self.feed.tick_received.connect(self._on_feed_tick)
        self.feed.candle_updated.connect(self._on_feed_candle)
        self.feed.connection_changed.connect(self._on_feed_connection_changed)
        self.feed.history_loaded.connect(self._on_feed_history_loaded)

        # M30 AI Engine Aggregator (Strictly locked to M30)
        self.feed.m30_candle_closed.connect(self._on_m30_candle_closed)
        self.feed.m30_history_loaded.connect(self._on_m30_history_loaded)

        # AI Agent Signals (Strictly locked to Pretrained MOMENT-1-large Model)
        self.agent.order_opened.connect(self._on_order_opened)
        self.agent.order_closed.connect(self._on_order_closed)
        self.agent.position_updated.connect(self._on_position_updated)
        self.agent.oms_event.connect(self._on_oms_event)
        self.agent.telemetry_updated.connect(self._on_telemetry)
        self.agent.agent_status_changed.connect(self._on_agent_status_changed)

        # Initial UI synchronization
        self._update_session_bar_ui()
        self._update_agent_button_text()

    # -------------------------------------------------------------
    # Production Model Control Methods
    # -------------------------------------------------------------
    def _switch_active_session(self, session_key: str = "B"):
        self._refresh_active_ui()

    def set_agent_armed(self, armed: bool):
        self.agent.set_armed(armed)
        self._update_agent_button_text()
        self._update_session_bar_ui()
        self._persist_current_state()
        state_str = "⚡ ARMED & SCANNING M30" if armed else "🛑 PLACED ON SAFE STANDBY"
        self.journal_widget._log_event(f"[MISSION CONTROL] MOMENT-1-large {state_str}")

    def _arm_both_sessions(self):
        self.set_agent_armed(True)

    def _standby_all_sessions(self):
        self.set_agent_armed(False)

    def _update_session_bar_ui(self):
        stats = self.broker.get_stats()
        pos = self.broker.open_position
        stats["open_position"] = pos
        self.metrics_panel.update_metrics(stats)

        if hasattr(self, "lbl_status_line"):
            pos_str = f"Active Pos: {pos['direction']} {pos['lot']:.2f}L ({pos.get('floating_r', 0.0):+.2f}R)" if pos else "Position: FLAT"
            arm_str = "ARMED" if self.agent.is_armed else "STANDBY"
            lat = self.last_tick.get('latency_ms', 0.0) if self.last_tick else 0.0
            sprd = self.last_tick.get('spread', 0.0) if self.last_tick else 0.0
            self.lbl_status_line.setText(
                f"[ENGINE] MOMENT-1-large Production Active | Agent: {arm_str} | {pos_str} | Latency: {lat:.1f}ms | Spread: ${sprd:.2f} | Ticks: {self.feed.tick_count:,}"
            )

    def _refresh_active_ui(self):
        broker = self.broker
        agent = self.agent
        stats = broker.get_stats()
        pos = broker.open_position

        live_p = None
        if pos and self.last_tick:
            live_p = self.last_tick.get("bid" if pos["direction"] == "BUY" else "ask", pos["entry_price"])

        # 1. Update Metrics
        cur_sess = agent.get_current_session(datetime.now(timezone.utc))
        self.metrics_panel.update_metrics(stats, current_session=cur_sess or "Off-Session")

        # 2. Update HUD
        if pos:
            self.position_hud.update_position(pos, live_p)
            self.journal_widget.update_active_position(pos, live_p)
            self.chart_widget.display_active_order(pos, live_p)
        else:
            self.position_hud.set_standby(True, symbol=self.current_pair_display)
            self.journal_widget.clear_active_position()
            self.chart_widget.clear_order_lines()

        # 3. Update Journal table with closed trades
        self.journal_widget.set_trades(broker.trade_history)

        # 4. Update Left Panel Sizing & Capital Controls
        self.spin_capital.blockSignals(True)
        self.spin_capital.setValue(broker.initial_capital)
        self.spin_capital.blockSignals(False)

        self.combo_sizing.blockSignals(True)
        self.combo_sizing.setCurrentIndex(0 if broker.lot_mode == "dynamic" else 1)
        self.combo_sizing.blockSignals(False)

        self.spin_max_lot.blockSignals(True)
        self.spin_max_lot.setValue(broker.max_lot)
        self.spin_max_lot.blockSignals(False)

        # 5. Update Arm button & header indicators
        self._update_agent_button_text()

    # -------------------------------------------------------------
    # Real-Time Event Dispatchers
    # -------------------------------------------------------------
    def _on_feed_tick(self, tick: dict):
        self.last_tick = tick
        self.agent.on_tick(tick)

        # Throttle heavy UI refresh to max 1Hz
        now = time.monotonic()
        if now - self._last_tick_ui_time < 1.0:
            return
        self._last_tick_ui_time = now

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

        # Update model status bar
        self._update_session_bar_ui()

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

    def _on_m30_history_loaded(self, candles: list):
        self.m30_candles = list(candles)
        self.journal_widget._log_event(f"[AI ENGINE] Loaded {len(candles)} historical M30 bars for MOMENT-1-large.")

    def _on_m30_candle_closed(self, candle: dict):
        if len(self.m30_candles) == 0 or self.m30_candles[-1]["time"] != candle["time"]:
            self.m30_candles.append(candle)
        else:
            self.m30_candles[-1] = candle

        if len(self.m30_candles) > 120:
            self.m30_candles.pop(0)

        # Trigger AI inference on MOMENT model
        self.agent.on_candle_closed(candle, self.m30_candles)
        self._update_session_bar_ui()
        if hasattr(self, "cloud_client") and self.cloud_client:
            self._sync_with_cloud_server()

    def _on_order_opened(self, pos: dict):
        sl_price = float(pos.get("current_sl", pos.get("sl_price", 0.0)))
        tp_price = float(pos.get("current_tp", pos.get("tp_price", 0.0)))
        lot = float(pos.get("lot", 0.01))
        ep = float(pos.get("entry_price", 0.0))
        d = str(pos.get("direction", "BUY"))
        live_p = self.last_tick.get("bid", ep) if d == "BUY" else self.last_tick.get("ask", ep)

        try:
            self.chart_widget.display_active_order(pos, live_p)
            self.position_hud.update_position(pos, live_p)
            self.journal_widget.update_active_position(pos, live_p)
        except Exception as e:
            print(f"[UI Order Error] {e}")

        self.journal_widget._log_event(
            f"[MOMENT] ORDER OPENED: {d} {lot:.2f}L @ ${ep:,.2f} | "
            f"SL: ${sl_price:,.2f} | TP: ${tp_price:,.2f} | ID: {pos.get('id')}"
        )

        try:
            if self.db is not None:
                self.db.record_order_opened(pos, source="MOMENT_LOCKED_PROD")
        except Exception as e:
            print(f"[DB Order Error] {e}")

        self._persist_current_state()
        self._update_session_bar_ui()

        # Trigger compact institutional popup notification
        try:
            from .widgets.order_popup import LiveOrderPopup
            popup = LiveOrderPopup(pos, parent=self)
            popup.show_anchored(self)
        except Exception as e:
            print(f"[Order Popup Error] {e}")

        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            try:
                self.tray_icon.showMessage(
                    f"[MOMENT] NEW TRADE: {d}",
                    f"{lot:.2f}L @ ${ep:,.2f} | SL: ${sl_price:,.2f} | TP: ${tp_price:,.2f}",
                    QSystemTrayIcon.Information,
                    4000
                )
            except Exception:
                pass

    def _on_order_closed(self, trade: dict):
        pnl = trade.get('net_pnl', 0.0)
        res_str = "PROFIT 💰" if pnl >= 0 else "LOSS 🔻"

        self.chart_widget.clear_order_lines()
        self.position_hud.set_standby(True)
        self.journal_widget.clear_active_position()
        self.journal_widget.add_closed_trade(trade)
        stats = self.broker.get_stats()
        self.metrics_panel.update_metrics(stats)

        self.journal_widget._log_event(
            f"[MOMENT] TRADE CLOSED [{res_str}]: Net PnL: {'+' if pnl>=0 else ''}${pnl:.2f} USD | "
            f"Exit: ${trade.get('exit_price', 0.0):,.2f} ({trade.get('exit_reason', 'Closed')})"
        )

        try:
            if self.db is not None:
                self.db.record_order_closed(trade)
        except Exception as e:
            print(f"[DB Order Close Error] {e}")

        self._persist_current_state()
        self._update_session_bar_ui()

        if hasattr(self, "tray_icon") and self.tray_icon is not None and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                f"[MOMENT] TRADE CLOSED [{res_str}]",
                f"Net PnL: {'+' if pnl>=0 else ''}${pnl:.2f} USD",
                QSystemTrayIcon.Information,
                4500
            )

    def _on_position_updated(self, pos: dict):
        live_p = self.last_tick.get("bid", pos["entry_price"]) if pos["direction"] == "BUY" else self.last_tick.get("ask", pos["entry_price"])
        self.position_hud.update_position(pos, live_p)
        self.journal_widget.update_active_position(pos, live_p)
        self.chart_widget.display_active_order(pos, live_p)
        self._update_session_bar_ui()

    def _on_oms_event(self, stage: str, details: str, ref_price: float):
        self.journal_widget.log_oms_event(f"[MOMENT] {stage}", details, ref_price)
        if "Micro-Breakeven" in stage:
            self.chart_widget.update_sl_line(ref_price, "MICRO-BE")
        elif "Ratchet" in stage:
            self.chart_widget.update_sl_line(ref_price, "RATCHET")
        elif "Trailing" in stage:
            self.chart_widget.update_sl_line(ref_price, "TRAIL")
        elif "Stale Decay" in stage:
            self.chart_widget.update_sl_line(ref_price, "STALE")

        trade_id = self.broker.open_position.get("id", "") if self.broker.open_position else ""
        if self.db is not None:
            self.db.record_oms_event(trade_id, f"[MOMENT] {stage}", details, ref_price)

        self._persist_current_state()
        self._update_session_bar_ui()

    def _on_telemetry(self, tele: dict):
        self.journal_widget.update_telemetry(tele)
        def _bg_record():
            try:
                if self.db is None:
                    return
                executed = tele.get("action") in ["BUY", "SELL"] and float(tele.get("conf", 0.0)) >= 32.0
                self.db.record_ai_telemetry(tele, executed=executed, source="MOMENT_LOCKED_PROD")
            except Exception:
                pass
        threading.Thread(target=_bg_record, daemon=True).start()

    # Backward compatibility delegate methods
    def _on_session_order_opened(self, pos: dict, session_key: str = "B"):
        self._on_order_opened(pos)

    def _on_session_order_closed(self, trade: dict, session_key: str = "B"):
        self._on_order_closed(trade)

    def _on_session_position_updated(self, pos: dict, session_key: str = "B"):
        self._on_position_updated(pos)

    def _on_session_oms_event(self, stage: str, details: str, ref_price: float, session_key: str = "B"):
        self._on_oms_event(stage, details, ref_price)

    def _on_session_telemetry(self, tele: dict, session_key: str = "B"):
        self._on_telemetry(tele)

    def _on_session_status_changed(self, armed: bool, text: str, session_key: str = "B"):
        self._on_agent_status_changed(armed, text)

    def _on_session_status_changed(self, armed: bool, text: str, session_key: str):
        if session_key == self.active_session:
            self._update_agent_button_text()
        self._update_session_bar_ui()

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
        self.journal_widget._log_event(f"[FEED] Loaded {len(candles)} historical bars to seed chart view ({self.feed.current_timeframe}).")

    def _on_cloud_state_ready(self, state: dict):
        self.lbl_cloud_status.setText("[CLOUD: ONLINE 🟢]")
        self.lbl_cloud_status.setStyleSheet("font-size: 10.5px; font-family: monospace; color: #00e676; font-weight: 700; background-color: #080808; padding: 4px 8px; border: 1px solid #262626; border-radius: 3px;")
        
        b_info = state.get("broker", {})
        if "stats" in b_info:
            self.metrics_panel.update_metrics(b_info["stats"])
        
        if "cash" in b_info:
            self.active_broker.cash = float(b_info["cash"])

        pos = b_info.get("open_position")
        self.active_broker.open_position = pos
        if pos:
            ref_p = float(self.last_tick.get("bid" if pos.get("direction") == "BUY" else "ask", pos.get("entry_price", 0.0)))
            self.position_hud.update_position(pos, ref_p)
            sl_price = pos.get("current_sl", pos.get("sl_price", 0.0))
            self.chart_widget.draw_order_lines(pos["direction"], pos["entry_price"], sl_price, pos["tp_price"])
        else:
            self.position_hud.set_standby(True)
            self.chart_widget.clear_order_lines()

        cloud_armed = state.get("is_armed")
        if cloud_armed is not None and cloud_armed != self.active_agent.is_armed:
            self.active_agent.set_armed(cloud_armed)

    def _on_cloud_sync_failed(self):
        self.lbl_cloud_status.setText("[DESKTOP LOCAL 🟡]")
        self.lbl_cloud_status.setStyleSheet("font-size: 10.5px; font-family: monospace; color: #ffd700; font-weight: 700; background-color: #080808; padding: 4px 8px; border: 1px solid #262626; border-radius: 3px;")

    def _sync_with_cloud_server(self):
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

        if self.active_broker.open_position is None:
            return
        p = self.last_tick.get("bid" if self.active_broker.open_position["direction"] == "BUY" else "ask", 0.0)
        self.active_agent.manual_close(p)


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
            self.btn_toggle_agent.setText("🛑 PAUSE AGENT (STANDBY)")
            self.btn_toggle_agent.setStyleSheet("""
                QPushButton {
                    background-color: #3b1016;
                    border: 1px solid #ef4444;
                    color: #fca5a5;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 8px;
                    letter-spacing: 0.5px;
                }
                QPushButton:hover {
                    background-color: #5c1822;
                    border-color: #f87171;
                    color: #ffffff;
                }
            """)
            self.lbl_agent_status.setText(f"[AGENT: ARMED ({self.current_symbol})]")
            self.lbl_agent_status.setStyleSheet("font-size: 11px; font-family: monospace; color: #00e676; font-weight: 700;")
        else:
            self.btn_toggle_agent.setText("⚡ ARM AGENT (LIVE)")
            self.btn_toggle_agent.setStyleSheet("""
                QPushButton {
                    background-color: #004d40;
                    border: 1px solid #00bfa5;
                    color: #ffffff;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 8px;
                    letter-spacing: 0.5px;
                }
                QPushButton:hover {
                    background-color: #00695c;
                    border-color: #1de9b6;
                }
            """)
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
        """Saves current desktop operational state for the locked MOMENT production model."""
        state = {
            "session_id": "MOMENT_LOCKED_PROD",
            "model_choice": "pretrained",
            "model_name": "MOMENT-1-large Pretrained (Locked Production)",
            "cash": float(self.broker.cash),
            "initial_capital": float(self.broker.initial_capital),
            "open_position": self.broker.open_position,
            "last_candle_time": getattr(self.agent, "last_evaluated_bar_time", 0),
            "last_session_traded": getattr(self.agent, "last_session_traded", ""),
            "is_armed": bool(self.agent.is_armed),
            "symbol": getattr(self, "current_symbol", "XAUUSD"),
            "lot_mode": getattr(self.broker, "lot_mode", "dynamic"),
            "max_lot": getattr(self.broker, "max_lot", 2.0),
            "broker": {
                "cash": float(self.broker.cash),
                "open_position": self.broker.open_position,
                "stats": self.broker.get_stats()
            },
            "updated_at_utc": datetime.now(timezone.utc).isoformat()
        }

        def _bg_persist():
            try:
                if self.db is not None:
                    self.db.save_operational_state(state, "GLOBAL_STATE")

                state_file = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\data\cloud_trader_state.json")
                state_file.parent.mkdir(parents=True, exist_ok=True)
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2, default=str)
            except Exception as e:
                print(f"[Persist State Error] {e}")

        threading.Thread(target=_bg_persist, daemon=True).start()

    def _fetch_persisted_state_data(self) -> Optional[dict]:
        # 1. Primary: Direct sync from Neon Cloud Database (Fresh 24/7 source of truth)
        if self.db is not None:
            try:
                state_data = self.db.get_operational_state("GLOBAL_STATE")
                if state_data and isinstance(state_data, dict):
                    print("[RECOVERY] State loaded from Neon Cloud Database.")
                    return state_data
            except Exception:
                pass

        # 2. Secondary: Local disk JSON backup
        state_file = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\data\cloud_trader_state.json")
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data and isinstance(data, dict):
                    print("[RECOVERY] State loaded from local JSON backup.")
                    return data
            except Exception:
                pass

        return None

    def _fetch_persisted_trades_data(self, db=None) -> List[dict]:
        target_db = db or self.db
        if target_db is None:
            try:
                target_db = TradeAuditDB()
            except Exception:
                return []
        try:
            with target_db._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT trade_id, symbol, direction, lot_size, entry_price, exit_price,
                           sl_dist, net_pnl, friction, balance_after, bars_held,
                           open_time, close_time, exit_reason, win_flag, source
                    FROM live_trades
                    WHERE status = 'CLOSED' AND exit_price IS NOT NULL
                    ORDER BY id ASC
                """)
                rows = cur.fetchall()
                trades = []
                for r in rows:
                    if isinstance(r, dict):
                        d = dict(r)
                    else:
                        d = {
                            "trade_id": r[0], "symbol": r[1], "direction": r[2], "lot_size": r[3],
                            "entry_price": r[4], "exit_price": r[5], "sl_dist": r[6], "net_pnl": r[7],
                            "friction": r[8], "balance_after": r[9], "bars_held": r[10],
                            "open_time": r[11], "close_time": r[12], "exit_reason": r[13], "win_flag": r[14],
                            "source": r[15] if len(r) > 15 else "DESKTOP"
                        }
                    t_clean = {
                        "id": d.get("trade_id", ""),
                        "session_id": d.get("source", "MOMENT_LOCKED_PROD"),
                        "source": d.get("source", "MOMENT_LOCKED_PROD"),
                        "direction": d.get("direction", "BUY"),
                        "lot": float(d.get("lot_size") or 0.01),
                        "lot_size": float(d.get("lot_size") or 0.01),
                        "entry_price": float(d.get("entry_price") or 0.0),
                        "exit_price": float(d.get("exit_price") or 0.0),
                        "sl_dist": float(d.get("sl_dist") or 0.0),
                        "net_pnl": float(d.get("net_pnl") or 0.0),
                        "friction": float(d.get("friction") or 0.17),
                        "balance": float(d.get("balance_after") or 0.0),
                        "balance_after": float(d.get("balance_after") or 0.0),
                        "bars_held": int(d.get("bars_held") or 1),
                        "open_time": str(d.get("open_time") or ""),
                        "close_time": str(d.get("close_time") or ""),
                        "exit_reason": str(d.get("exit_reason") or "Closed"),
                        "win": int(d.get("win_flag") if d.get("win_flag") is not None else (1 if float(d.get("net_pnl") or 0.0) > 0 else 0))
                    }
                    trades.append(t_clean)
                return trades
        except Exception as e:
            print(f"[RECOVERY] Fetch trades error: {e}")
            return []

    def _apply_persisted_trades(self, trades: list):
        try:
            if not trades:
                return
            self.broker.trade_history = list(trades)
            self.journal_widget.load_history_trades(self.broker.trade_history)
            self.metrics_panel.update_metrics(self.broker.get_stats())
            self._update_session_bar_ui()
            print(f"[RECOVERY] Applied {len(trades)} trade(s) to locked MOMENT broker.")
        except Exception as e:
            print(f"[RECOVERY] Apply trades error: {e}")

    def _load_persisted_state(self):
        state_data = self._fetch_persisted_state_data()
        if state_data:
            self._state_loaded.emit(state_data)

    def _apply_persisted_state(self, state_data: dict):
        try:
            target_data = state_data.get("broker") or state_data.get("model_b") or state_data
            if "cash" in target_data:
                self.broker.cash = float(target_data["cash"])
            if "initial_capital" in target_data:
                self.broker.initial_capital = float(target_data["initial_capital"])
            if "is_armed" in state_data:
                self.agent.set_armed(bool(state_data["is_armed"]))
            if target_data.get("open_position"):
                self.broker.open_position = target_data["open_position"]

            self._refresh_active_ui()
            self._update_session_bar_ui()
            print(f"[RECOVERY] Applied locked MOMENT state (cash=${self.broker.cash})")
        except Exception as e:
            print(f"[RECOVERY] Apply state error: {e}")


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
            self.lbl_operator.setText(f"👤 {self.operator_user.get('username', 'OPERATOR').upper()}")
            self.lbl_operator.setToolTip(self.operator_user.get("display_name", "OPERATOR"))
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
