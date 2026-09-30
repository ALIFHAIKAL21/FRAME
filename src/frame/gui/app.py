"""
Flowdev FRAME Workstation: Main Desktop Application Window
Engineered specifically for Flowdev Internal Development & Testing.
Clean, legacy, minimalist aesthetic. No clutter, no unnecessary icons.
"""

import sys, os, pathlib, json
from typing import Optional, Dict, Any


try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLabel, QPushButton, QComboBox, QTabWidget, QTableWidget, 
        QTableWidgetItem, QHeaderView, QSplitter, QFrame, QProgressBar, 
        QPlainTextEdit, QMessageBox, QFileDialog, QDoubleSpinBox, QDialog
    )
    from PySide6.QtCore import Qt, QTimer, QLocale
    from PySide6.QtGui import QFont, QColor
except ImportError:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLabel, QPushButton, QComboBox, QTabWidget, QTableWidget, 
        QTableWidgetItem, QHeaderView, QSplitter, QFrame, QProgressBar, 
        QPlainTextEdit, QMessageBox, QFileDialog, QDoubleSpinBox, QDialog
    )
    from PyQt6.QtCore import Qt, QTimer, QLocale
    from PyQt6.QtGui import QFont, QColor

from src.frame.gui.styles import QSS_STYLE
from src.frame.gui.widgets.metrics_panel import MetricsPanel
from src.frame.gui.widgets.chart_canvas import ChartCanvas
from src.frame.gui.widgets.tradingview_chart import TradingViewChartWidget
from src.frame.gui.worker import BacktestWorker

ALL_MONTHS_CHRONO = [
    f"{y}-{m:02d}"
    for y in range(2021, 2027)
    for m in (range(10, 13) if y == 2021 else (range(1, 9) if y == 2026 else range(1, 13)))
]
ALL_MONTHS_REVERSE = list(reversed(ALL_MONTHS_CHRONO))

class MainWindow(QMainWindow):
    def __init__(self, operator_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.operator_user = operator_user or {
            "username": "alifhaikal",
            "role": "MASTER_TRADER",
            "display_name": "Alif Haikal (Master Operator)"
        }
        self.setWindowTitle("FLOWDEV FRAME WORKSTATION // INTERNAL DEV BUILD")
        self.resize(1280, 820)
        self.setStyleSheet(QSS_STYLE)

        self.last_results = None
        self.worker = None
        self.live_win = None

        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Header Bar
        header_frame = QFrame()
        header_frame.setObjectName("header_frame")
        header_frame.setStyleSheet("#header_frame { background-color: #090d14; border: 1px solid #161e2e; }")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 4, 8, 4)

        lbl_brand = QLabel("FLOWDEV FRAME // RECURRENT ALGORITHMIC TRADE ENGINE")
        lbl_brand.setStyleSheet("font-size: 11px; font-weight: 800; color: #d4af37; letter-spacing: 1.2px;")

        lbl_device = QLabel("[ENV: RTX 4050 / CUDA 12.6]  [ASSET: XAU/USD M30]  [STATUS: READY]")
        lbl_device.setStyleSheet("font-size: 11px; font-family: 'Consolas', monospace; color: #8b949e;")

        btn_live = QPushButton("🔴 LIVE REALTIME TRADER")
        btn_live.setCursor(Qt.PointingHandCursor)
        btn_live.setToolTip("Open Dedicated Standalone Live Real-Time Market Simulator")
        btn_live.setStyleSheet("""
            QPushButton {
                background-color: #3b1016; border: 1px solid #ef4444;
                font-size: 10.5px; padding: 4px 12px; font-weight: 800; color: #fca5a5;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #5c1822; border-color: #f87171; color: #ffffff; }
        """)
        btn_live.clicked.connect(self._open_live_trader)

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
        h_layout.addSpacing(15)
        h_layout.addWidget(btn_live)
        h_layout.addStretch()
        h_layout.addWidget(lbl_device)
        h_layout.addSpacing(10)
        h_layout.addWidget(self.lbl_operator)
        h_layout.addSpacing(4)
        h_layout.addWidget(self.btn_lock)
        main_layout.addWidget(header_frame)

        # 2. Main Content Splitter (Left Sidebar Controls + Right Main Stage)
        splitter = QSplitter(Qt.Horizontal)

        # Left Control Panel
        left_panel = QFrame()
        left_panel.setObjectName("left_panel")
        left_panel.setFixedWidth(275)
        left_panel.setStyleSheet("#left_panel { background-color: #0d111a; border: 1px solid #1c2333; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        lbl_ctrl_title = QLabel("SIMULATION CONTROLS")
        lbl_ctrl_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #8b949e; letter-spacing: 1px;")
        left_layout.addWidget(lbl_ctrl_title)

        # 0. Deep Learning Model Selector
        left_layout.addWidget(QLabel("Deep Learning Model:"))
        self.combo_model = QComboBox()
        self.combo_model.setMaxVisibleItems(5)
        self.combo_model.addItems([
            "MOMENT-1-large Pretrained [LOCKED PRODUCTION]",
            "CNN-BiLSTM Baseline [LEGACY BENCHMARK]"
        ])
        left_layout.addWidget(self.combo_model)

        # 1. Period Scope Selector
        left_layout.addWidget(QLabel("Audit Time Scope:"))
        self.combo_period_mode = QComboBox()
        self.combo_period_mode.setMaxVisibleItems(10)
        self.combo_period_mode.addItems([
            "Annual Presets",
            "Single Month",
            "Custom Month Range",
            "Multi-Year (2021-2026)"
        ])
        left_layout.addWidget(self.combo_period_mode)

        # Sub-container for Period specifics
        self.frame_period_sub = QFrame()
        self.frame_period_sub.setObjectName("frame_period_sub")
        self.frame_period_sub.setStyleSheet("#frame_period_sub { background-color: #080c14; border: 1px solid #161e2e; border-radius: 3px; }")
        sub_period_layout = QVBoxLayout(self.frame_period_sub)
        sub_period_layout.setContentsMargins(6, 6, 6, 6)
        sub_period_layout.setSpacing(4)

        # 1a. Annual Presets Sub-widget
        self.widget_annual = QWidget()
        w_ann_layout = QVBoxLayout(self.widget_annual)
        w_ann_layout.setContentsMargins(0, 0, 0, 0)
        w_ann_layout.setSpacing(2)
        w_ann_layout.addWidget(QLabel("Select Year:"))
        self.combo_year = QComboBox()
        self.combo_year.setMaxVisibleItems(10)
        self.combo_year.addItems(["2026", "2025", "2024", "2023", "2022"])
        w_ann_layout.addWidget(self.combo_year)
        sub_period_layout.addWidget(self.widget_annual)

        # 1b. Single Month Sub-widget
        self.widget_single = QWidget()
        w_sgl_layout = QVBoxLayout(self.widget_single)
        w_sgl_layout.setContentsMargins(0, 0, 0, 0)
        w_sgl_layout.setSpacing(2)
        w_sgl_layout.addWidget(QLabel("Select Month:"))
        self.combo_single_month = QComboBox()
        self.combo_single_month.setMaxVisibleItems(12)
        self.combo_single_month.addItems(ALL_MONTHS_REVERSE)
        w_sgl_layout.addWidget(self.combo_single_month)
        sub_period_layout.addWidget(self.widget_single)

        # 1c. Custom Range Sub-widget
        self.widget_range = QWidget()
        w_rng_layout = QVBoxLayout(self.widget_range)
        w_rng_layout.setContentsMargins(0, 0, 0, 0)
        w_rng_layout.setSpacing(4)
        
        row_from = QHBoxLayout()
        row_from.addWidget(QLabel("From:"))
        self.combo_range_start = QComboBox()
        self.combo_range_start.setMaxVisibleItems(12)
        self.combo_range_start.addItems(ALL_MONTHS_CHRONO)
        self.combo_range_start.setCurrentText("2026-01")
        row_from.addWidget(self.combo_range_start)
        w_rng_layout.addLayout(row_from)

        row_to = QHBoxLayout()
        row_to.addWidget(QLabel("To:    "))
        self.combo_range_end = QComboBox()
        self.combo_range_end.setMaxVisibleItems(12)
        self.combo_range_end.addItems(ALL_MONTHS_CHRONO)
        self.combo_range_end.setCurrentText("2026-08")
        row_to.addWidget(self.combo_range_end)
        w_rng_layout.addLayout(row_to)
        sub_period_layout.addWidget(self.widget_range)

        # 1d. Multi-Year Sub-widget
        self.widget_multi = QWidget()
        w_mul_layout = QVBoxLayout(self.widget_multi)
        w_mul_layout.setContentsMargins(0, 0, 0, 0)
        lbl_mul_desc = QLabel("Complete 5-Year History\n(Oct 2021 - Aug 2026 / 59 Mo)")
        lbl_mul_desc.setStyleSheet("color: #00e5ff; font-size: 10px; font-family: monospace;")
        w_mul_layout.addWidget(lbl_mul_desc)
        sub_period_layout.addWidget(self.widget_multi)

        left_layout.addWidget(self.frame_period_sub)
        self.combo_period_mode.currentIndexChanged.connect(self._on_period_mode_changed)

        # 2. Account Capital (Locked $250 - $500 USD)
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

        # Quick Preset Buttons: Strictly $250 (0.02L) and $500 (0.04L)
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
            btn.clicked.connect(lambda _, v=val, l=lot: (self.spin_capital.setValue(float(v)), self.spin_max_lot.setValue(l)))
            preset_row.addWidget(btn)
        left_layout.addLayout(preset_row)

        # 3. Agent Position Sizing Mode
        left_layout.addWidget(QLabel("Position Sizing Mode:"))
        self.combo_sizing = QComboBox()
        self.combo_sizing.setMaxVisibleItems(10)
        self.combo_sizing.addItems([
            "Dual-Mode Comparison",
            "Dynamic Compounding",
            "Flat 0.01 Lot (Baseline)"
        ])
        left_layout.addWidget(self.combo_sizing)

        # Max Lot Cap Frame
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
        row_cap.addWidget(self.spin_max_lot)

        max_lot_layout.addLayout(row_cap)

        lbl_formula = QLabel("Rule: Trend Gate (EMA200) + Daily Breaker + Auto Cap Locked")
        lbl_formula.setStyleSheet("color: #78909c; font-size: 9.0px; font-family: monospace;")
        max_lot_layout.addWidget(lbl_formula)

        self.spin_capital.valueChanged.connect(lambda v: self.spin_max_lot.setValue(0.02 if v <= 300.0 else 0.04))

        left_layout.addWidget(self.frame_max_lot)
        self.combo_sizing.currentIndexChanged.connect(self._on_sizing_mode_changed)

        # Initialize visibility
        self._on_period_mode_changed(0)
        self._on_sizing_mode_changed(0)

        # 4. OMS Specs Info Box
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

        # Action Buttons
        self.btn_run = QPushButton("EXECUTE SIMULATION")
        self.btn_run.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #0e121a;
                border-color: #1a2230;
                color: #555e6d;
            }
        """)
        self.btn_run.clicked.connect(self._start_backtest)
        
        # RBAC Enforcement: Auditor Role is Read-Only
        if self.operator_user.get("role") == "AUDITOR_VIEWER":
            self.btn_run.setEnabled(False)
            self.btn_run.setToolTip("[AUDITOR READ-ONLY] Mode auditor hanya dapat meninjau hasil evaluasi. Eksekusi simulasi baru dibatasi untuk MASTER_TRADER.")

        left_layout.addWidget(self.btn_run)

        self.btn_export = QPushButton("EXPORT REPORT (JSON / PNG)")
        self.btn_export.setStyleSheet("background-color: #161e2e; border: 1px solid #27334a; padding: 7px; font-size: 11px;")
        self.btn_export.clicked.connect(self._export_reports)
        self.btn_export.setEnabled(False)
        left_layout.addWidget(self.btn_export)

        splitter.addWidget(left_panel)


        # Right Main Stage Tabs
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Top Metrics Cards Panel
        self.metrics_panel = MetricsPanel()
        right_layout.addWidget(self.metrics_panel)

        # Tabs Container
        self.tabs = QTabWidget()

        # Tab 1: Chart & Analytics
        tab_chart = QWidget()
        tab_chart_layout = QVBoxLayout(tab_chart)
        tab_chart_layout.setContentsMargins(4, 4, 4, 4)
        self.chart_canvas = ChartCanvas()
        tab_chart_layout.addWidget(self.chart_canvas)
        self.tabs.addTab(tab_chart, "PERFORMANCE ANALYTICS")

        # Tab 2: TradingView Visual Inspector
        self.tradingview_widget = TradingViewChartWidget()
        self.tabs.addTab(self.tradingview_widget, "TRADINGVIEW INSPECTOR")

        # Tab 3: Monthly Breakdown
        tab_monthly = QWidget()
        tab_monthly_layout = QVBoxLayout(tab_monthly)
        tab_monthly_layout.setContentsMargins(4, 4, 4, 4)
        self.tbl_monthly = QTableWidget()
        self.tbl_monthly.setColumnCount(7)
        self.tbl_monthly.setHorizontalHeaderLabels(["Month", "Trades", "Wins", "Losses", "Win Rate (%)", "Net PnL ($)", "Ending Balance ($)"])
        self.tbl_monthly.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tab_monthly_layout.addWidget(self.tbl_monthly)
        self.tabs.addTab(tab_monthly, "MONTHLY BREAKDOWN")

        # Tab 4: Trade Journal
        tab_journal = QWidget()
        tab_journal_layout = QVBoxLayout(tab_journal)
        tab_journal_layout.setContentsMargins(4, 4, 4, 4)
        self.tbl_trades = QTableWidget()
        self.tbl_trades.setColumnCount(10)
        self.tbl_trades.setHorizontalHeaderLabels([
            "Timestamp (UTC)", "Session", "Direction", "Lot Size", 
            "Entry Price", "Exit Price", "SL Dist ($)", "Net PnL ($)", 
            "Balance ($)", "Exit Reason"
        ])
        self.tbl_trades.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_trades.cellDoubleClicked.connect(self._on_trade_row_double_clicked)
        tab_journal_layout.addWidget(self.tbl_trades)
        self.tabs.addTab(tab_journal, "TRADE JOURNAL")

        # Tab 5: Diagnostics
        tab_diag = QWidget()
        tab_diag_layout = QVBoxLayout(tab_diag)
        tab_diag_layout.setContentsMargins(8, 8, 8, 8)
        self.txt_diag = QPlainTextEdit()
        self.txt_diag.setReadOnly(True)
        self.txt_diag.setProperty("class", "terminal")
        self.txt_diag.setStyleSheet("background-color: #080a10; border: 1px solid #161e2e; font-family: monospace; color: #8b949e; font-size: 11px;")
        tab_diag_layout.addWidget(self.txt_diag)
        self.tabs.addTab(tab_diag, "SYSTEM DIAGNOSTICS")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_panel)

        # Set splitter sizes
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, stretch=1)

        # 3. Bottom Terminal & Progress Bar
        bottom_frame = QFrame()
        bottom_frame.setObjectName("bottom_frame")
        bottom_frame.setStyleSheet("#bottom_frame { background-color: #080a0f; border: 1px solid #161e2e; }")
        b_layout = QVBoxLayout(bottom_frame)
        b_layout.setContentsMargins(6, 4, 6, 4)
        b_layout.setSpacing(4)

        prog_layout = QHBoxLayout()
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #8b949e; font-family: monospace;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #121722;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #00e676;
                border-radius: 3px;
            }
        """)

        prog_layout.addWidget(self.lbl_status)
        prog_layout.addStretch()
        prog_layout.addWidget(self.progress_bar)
        prog_layout.setStretch(2, 1)

        b_layout.addLayout(prog_layout)

        self.txt_terminal = QPlainTextEdit()
        self.txt_terminal.setReadOnly(True)
        self.txt_terminal.setFixedHeight(75)
        self.txt_terminal.setProperty("class", "terminal")
        self.txt_terminal.setStyleSheet("background-color: #06080d; border: 1px solid #121824; font-family: monospace; color: #8b949e; font-size: 10.5px;")
        b_layout.addWidget(self.txt_terminal)

        main_layout.addWidget(bottom_frame)

        self._log("FLOWDEV FRAME Workstation initialized. Standing by for audit commands.")
        self._populate_diagnostics()

    def _log(self, msg: str):
        self.txt_terminal.appendPlainText(msg)
        self.txt_terminal.verticalScrollBar().setValue(self.txt_terminal.verticalScrollBar().maximum())

    def _populate_diagnostics(self):
        diag_lines = [
            "==========================================================================",
            "                   FLOWDEV FRAME SYSTEM DIAGNOSTIC REPORT                 ",
            "==========================================================================",
            f"Python Runtime     : {sys.version.split()[0]} ({sys.executable})",
            f"New Pretrained Model: c:\\Ngoding\\xau_deep_sniper\\checkpoints\\best_moment_15ch_pretrained_lora.pt",
            f"Legacy Model Checkpt: c:\\Ngoding\\xau_deep_sniper\\checkpoints\\best_moment_15ch_lora.pt",
            f"15-Channel Parquet : c:\\Ngoding\\xau_deep_sniper\\data\\processed\\xauusd_m30_labeled_15ch.parquet",
            f"Causal Execution   : Zero-Lookahead Next-Open Fill (t+1) + Pessimistic SL/TP",
            f"Locked Capital Scope: $250.00 - $500.00 USD (Realistic Broker 1:100 Leverage)",
            f"Broker Protections : Stop Out at 50% Margin Level | Dynamic Lot Compounding",
            f"Locked Target Asset: XAU/USD (Gold Spot) on M30 Timeframe",
            f"Hardware Target    : NVIDIA GeForce RTX 4050 Laptop GPU (CUDA 12.6/13.4)",
            f"Kinetic Protections: Micro-BE (+0.75R) | Ratchet (+1.2R) | Trail (+1.5R) | Decay (Bar 6)",
            "=========================================================================="
        ]
        self.txt_diag.setPlainText("\n".join(diag_lines))

    def _on_period_mode_changed(self, idx: int):
        self.widget_annual.setVisible(idx == 0)
        self.widget_single.setVisible(idx == 1)
        self.widget_range.setVisible(idx == 2)
        self.widget_multi.setVisible(idx == 3)

    def _on_sizing_mode_changed(self, idx: int):
        # idx 0: Dual-Mode, idx 1: Dynamic, idx 2: Flat
        self.frame_max_lot.setVisible(idx != 2)

    def _start_backtest(self):
        period_idx = self.combo_period_mode.currentIndex()
        start_date = ""
        end_date = ""

        if period_idx == 0:  # Annual Presets
            mode = self.combo_year.currentText()
        elif period_idx == 1:  # Single Month
            sel_month = self.combo_single_month.currentText()
            mode = f"Month {sel_month}"
            start_date = sel_month
            end_date = sel_month
        elif period_idx == 2:  # Custom Month Range
            st_m = self.combo_range_start.currentText()
            en_m = self.combo_range_end.currentText()
            if st_m > en_m:
                st_m, en_m = en_m, st_m
            mode = f"{st_m} to {en_m}"
            start_date = st_m
            end_date = en_m
        else:  # Multi-Year
            mode = "Multi-Year (2021-2026)"

        capital = float(self.spin_capital.value())

        sz_idx = self.combo_sizing.currentIndex()
        if sz_idx == 0:
            sizing_mode = "dual"
        elif sz_idx == 1:
            sizing_mode = "dynamic"
        else:
            sizing_mode = "flat"

        max_lot = float(self.spin_max_lot.value())

        model_choice = "pretrained" if self.combo_model.currentIndex() == 0 else "legacy"
        model_tag = "MOMENT Pretrained" if model_choice == "pretrained" else "CNN-BiLSTM"

        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.progress_bar.setValue(5)
        self.lbl_status.setText(f"Running simulation: {mode} (${capital:,.0f} | {sizing_mode.upper()} | {model_tag})...")

        self.worker = BacktestWorker(
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            capital=capital,
            lot=0.01,
            sizing_mode=sizing_mode,
            max_lot=max_lot,
            model_choice=model_choice
        )
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.log_message.connect(self._log)
        self.worker.finished_backtest.connect(self._on_worker_finished)
        self.worker.error_occurred.connect(self._on_worker_error)
        self.worker.start()

    def _on_worker_progress(self, val: int, msg: str):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(msg)

    def _on_worker_finished(self, data: dict):
        self.last_results = data
        self.btn_run.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.progress_bar.setValue(100)
        self.lbl_status.setText("Audit Execution Completed.")

        # Update Metrics
        self.metrics_panel.update_metrics(data)

        # Update Chart Canvas
        self.chart_canvas.plot_results(data)

        # Update TradingView Inspector
        if hasattr(self, 'tradingview_widget'):
            self.tradingview_widget.load_data(data.get('df_candles'), data.get('trades', []))

        # Update Monthly Table
        self._populate_monthly_table(data.get('monthly', []))

        # Update Trade Journal Table
        self._populate_trade_table(data.get('trades', []))

        # Record simulation run into Unified Audit Database
        try:
            from src.frame.live.db_audit import TradeAuditDB
            db = TradeAuditDB()
            run_id = db.record_simulation_run(data)
            self._log(f"[DB AUDIT] Recorded simulation run to database (Run #{run_id})")
        except Exception as e:
            self._log(f"[DB AUDIT] Notice: Could not record to DB: {e}")

    def _on_worker_error(self, err_msg: str):
        self.btn_run.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Error in execution.")
        QMessageBox.critical(self, "Audit Error", f"Execution failed:\n{err_msg}")

    def _on_trade_row_double_clicked(self, row: int, col: int):
        if not self.last_results:
            return
        trades = self.last_results.get('trades', [])
        display_trades = trades[-300:] if len(trades) > 300 else trades
        if 0 <= row < len(display_trades):
            selected_t = display_trades[row]
            t_month = selected_t.get('month', '')
            t_time = selected_t.get('time', '')

            # Switch to TradingView Inspector tab (index 1)
            self.tabs.setCurrentIndex(1)

            # Reset filter to All Outcomes to ensure the trade is in the list
            self.tradingview_widget.combo_filter.blockSignals(True)
            self.tradingview_widget.combo_filter.setCurrentIndex(0)
            self.tradingview_widget.combo_filter.blockSignals(False)

            # Select month
            m_idx = self.tradingview_widget.combo_month.findText(t_month)
            if m_idx >= 0:
                self.tradingview_widget.combo_month.setCurrentIndex(m_idx)
                # Find trade in filtered_trades
                for i, t in enumerate(self.tradingview_widget.filtered_trades):
                    if t.get('time') == t_time:
                        self.tradingview_widget.combo_trade.setCurrentIndex(i + 1)
                        break

    def _populate_monthly_table(self, monthly_list: list):
        self.tbl_monthly.setRowCount(len(monthly_list))
        for row, m in enumerate(monthly_list):
            pnl_val = m.get('pnl', 0.0)
            pnl_color = QColor("#00e676") if pnl_val >= 0 else QColor("#ff5252")

            item_m = QTableWidgetItem(str(m.get('month', '')))
            item_tr = QTableWidgetItem(str(m.get('trades', 0)))
            item_w = QTableWidgetItem(str(m.get('wins', 0)))
            item_l = QTableWidgetItem(str(m.get('losses', 0)))
            item_wr = QTableWidgetItem(f"{m.get('win_rate', 0.0):.1f}%")
            item_pnl = QTableWidgetItem(f"${pnl_val:+,.2f}")
            item_pnl.setForeground(pnl_color)
            item_bal = QTableWidgetItem(f"${m.get('balance', 0.0):,.2f}")

            for c, itm in enumerate([item_m, item_tr, item_w, item_l, item_wr, item_pnl, item_bal]):
                itm.setTextAlignment(Qt.AlignCenter)
                self.tbl_monthly.setItem(row, c, itm)

    def _populate_trade_table(self, trades_list: list):
        # Limit display to last 300 trades for high performance
        display_trades = trades_list[-300:] if len(trades_list) > 300 else trades_list
        self.tbl_trades.setRowCount(len(display_trades))

        for row, t in enumerate(display_trades):
            pnl_val = t.get('pnl', 0.0)
            pnl_color = QColor("#00e676") if pnl_val >= 0 else QColor("#ff5252")

            item_ts = QTableWidgetItem(str(t.get('time', ''))[:16])
            item_sess = QTableWidgetItem(str(t.get('session', '')).split()[0])
            item_dir = QTableWidgetItem(str(t.get('dir', '')))
            item_dir.setForeground(QColor("#2979ff") if t.get('dir') == "BUY" else QColor("#ff9100"))

            lot_val = t.get('lot', 0.01)
            item_lot = QTableWidgetItem(f"{lot_val:.2f}L")
            item_lot.setForeground(QColor("#00e5ff") if lot_val > 0.01 else QColor("#8b949e"))

            item_ep = QTableWidgetItem(f"${t.get('entry', 0.0):,.2f}")
            item_exit = QTableWidgetItem(f"${t.get('exit', 0.0):,.2f}")
            item_sl = QTableWidgetItem(f"${t.get('sl_dist', 0.0):.2f}")
            item_pnl = QTableWidgetItem(f"${pnl_val:+,.2f}")
            item_pnl.setForeground(pnl_color)
            item_eq = QTableWidgetItem(f"${t.get('equity', 0.0):,.2f}")
            item_reason = QTableWidgetItem(str(t.get('exit_reason', '')))

            for c, itm in enumerate([item_ts, item_sess, item_dir, item_lot, item_ep, item_exit, item_sl, item_pnl, item_eq, item_reason]):
                itm.setTextAlignment(Qt.AlignCenter)
                self.tbl_trades.setItem(row, c, itm)

    def _export_reports(self):
        import numpy as np
        if not self.last_results:
            return
        out_dir = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        mode_clean = self.last_results.get('mode', 'audit').replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_").lower()
        sz_clean = self.last_results.get('sizing_mode', 'flat').lower()
        json_path = out_dir / f"workstation_{mode_clean}_{sz_clean}.json"

        with open(json_path, 'w') as f:
            export_data = dict(self.last_results)
            # Remove non-serializable DataFrame & giant curve arrays
            export_data.pop('df_candles', None)
            if 'equity_curve' in export_data:
                export_data['equity_curve_points'] = len(export_data['equity_curve'])
                del export_data['equity_curve']
            if 'equity_curve_flat' in export_data and export_data['equity_curve_flat'] is not None:
                del export_data['equity_curve_flat']
            if 'equity_curve_dyn' in export_data and export_data['equity_curve_dyn'] is not None:
                del export_data['equity_curve_dyn']
            json.dump(
                export_data, f, indent=4,
                default=lambda x: int(x) if isinstance(x, (np.integer, np.int64)) else (float(x) if isinstance(x, (np.floating, np.float64)) else str(x))
            )

        self._log(f"[EXPORT] Saved audit report JSON to: {json_path}")
        QMessageBox.information(self, "Export Completed", f"Report saved successfully to:\n{json_path}")

    def _open_live_trader(self):
        from src.frame.live.live_window import LiveTradingWindow
        if self.live_win is None:
            self.live_win = LiveTradingWindow(operator_user=self.operator_user)
        self.live_win.show()
        self.live_win.raise_()
        self.live_win.activateWindow()

    def _lock_session(self):
        from src.frame.security.auth_dialog import DesktopAuthGatekeeper
        self.hide()
        dialog = DesktopAuthGatekeeper(parent=self, is_lock_screen=True)
        if dialog.exec() == QDialog.Accepted:
            self.operator_user = dialog.authenticated_user or self.operator_user
            self.lbl_operator.setText(f"👤 {self.operator_user.get('display_name', 'OPERATOR').upper()}")
            if self.operator_user.get("role") == "AUDITOR_VIEWER":
                self.btn_run.setEnabled(False)
                self.btn_run.setToolTip("[AUDITOR READ-ONLY] Eksekusi simulasi dibatasi untuk MASTER_TRADER.")
            else:
                self.btn_run.setEnabled(True)
                self.btn_run.setToolTip("")
            self.showNormal()
            self.raise_()
            self.activateWindow()
        else:
            QApplication.quit()

def run_app():
    from src.frame.security.auth_dialog import DesktopAuthGatekeeper
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Try restoring trusted desktop session or prompt gatekeeper
    user = DesktopAuthGatekeeper.try_restore_session()
    if not user:
        gate = DesktopAuthGatekeeper()
        if gate.exec() != QDialog.Accepted:
            sys.exit(0)
        user = gate.authenticated_user

    window = MainWindow(operator_user=user)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_app()
