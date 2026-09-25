"""
TradingView Chart Widget for FRAME Workstation
Ultra-clean, clutter-free institutional quant audit workbench.
Eliminates text overlap, isolates volume scale, and provides rapid step navigation.
"""

import json, pathlib, datetime
import pandas as pd
import numpy as np
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QFrame, QCheckBox, QApplication
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QKeyEvent
from PySide6.QtWebEngineWidgets import QWebEngineView

from .tradingview_template import get_tradingview_html

class TradingViewChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.trades: List[Dict[str, Any]] = []
        self.filtered_trades: List[Dict[str, Any]] = []
        self.current_month: str = ""
        self.df: pd.DataFrame = None
        self.selected_trade: Dict[str, Any] = None

        self.setFocusPolicy(Qt.StrongFocus)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # -------------------------------------------------------------
        # 1. Row 1: Unified Command & Audit Strip (Compact ~34px)
        # -------------------------------------------------------------
        cmd_frame = QFrame()
        cmd_frame.setStyleSheet("""
            QFrame {
                background-color: #080c14;
                border: 1px solid #141c2c;
                border-radius: 3px;
                padding: 2px 4px;
            }
            QLabel {
                font-size: 11px;
                color: #78909c;
                font-weight: 600;
            }
            QComboBox {
                font-size: 11px;
                padding: 2px 6px;
                background-color: #0f1523;
                border: 1px solid #1e293b;
                color: #e2e8f0;
            }
            QPushButton {
                font-size: 11px;
                padding: 3px 8px;
                background-color: #131b2c;
                border: 1px solid #233148;
                color: #cbd5e1;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1e293b;
                border-color: #3b82f6;
            }
            QCheckBox {
                color: #8b949e;
                font-size: 11px;
                margin-left: 4px;
            }
        """)
        cmd_layout = QHBoxLayout(cmd_frame)
        cmd_layout.setContentsMargins(4, 2, 4, 2)
        cmd_layout.setSpacing(6)

        # Month Selector
        cmd_layout.addWidget(QLabel("Month:"))
        self.combo_month = QComboBox()
        self.combo_month.setMinimumWidth(95)
        self.combo_month.currentIndexChanged.connect(self._on_month_changed)
        cmd_layout.addWidget(self.combo_month)

        # Filter Selector
        cmd_layout.addWidget(QLabel("Filter:"))
        self.combo_filter = QComboBox()
        self.combo_filter.setMinimumWidth(115)
        self.combo_filter.addItems([
            "All Outcomes",
            "Wins Only (+PnL)",
            "Losses Only (-PnL)",
            "Max TP (+2.7R)",
            "Protected Stops",
            "Time Barriers"
        ])
        self.combo_filter.currentIndexChanged.connect(self._apply_filter)
        cmd_layout.addWidget(self.combo_filter)

        # Prev / Next Controls
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setToolTip("Previous Trade (Left Arrow / A)")
        self.btn_prev.clicked.connect(self._on_prev_trade)
        cmd_layout.addWidget(self.btn_prev)

        self.combo_trade = QComboBox()
        self.combo_trade.setMinimumWidth(260)
        self.combo_trade.currentIndexChanged.connect(self._on_trade_selected)
        cmd_layout.addWidget(self.combo_trade)

        self.btn_next = QPushButton("▶")
        self.btn_next.setToolTip("Next Trade (Right Arrow / D)")
        self.btn_next.clicked.connect(self._on_next_trade)
        cmd_layout.addWidget(self.btn_next)

        # Separator
        cmd_layout.addWidget(self._make_v_sep())

        # Clean Toggles (All default to clean state!)
        self.chk_lines = QCheckBox("SL/TP Lines")
        self.chk_lines.setChecked(True)
        self.chk_lines.stateChanged.connect(self._render_current_view)
        cmd_layout.addWidget(self.chk_lines)

        self.chk_all_trades = QCheckBox("Other Trades")
        self.chk_all_trades.setChecked(False)  # OFF by default to eliminate clutter!
        self.chk_all_trades.setToolTip("Show background trades as subtle dots without text")
        self.chk_all_trades.stateChanged.connect(self._render_current_view)
        cmd_layout.addWidget(self.chk_all_trades)

        self.chk_ema200 = QCheckBox("EMA 200")
        self.chk_ema200.setChecked(False)  # OFF by default for clean candles
        self.chk_ema200.stateChanged.connect(self._render_current_view)
        cmd_layout.addWidget(self.chk_ema200)

        self.chk_ema50 = QCheckBox("EMA 50")
        self.chk_ema50.setChecked(False)
        self.chk_ema50.stateChanged.connect(self._render_current_view)
        cmd_layout.addWidget(self.chk_ema50)

        self.chk_vol = QCheckBox("Volume")
        self.chk_vol.setChecked(False)  # OFF by default so vertical scale is 100% price
        self.chk_vol.stateChanged.connect(self._render_current_view)
        cmd_layout.addWidget(self.chk_vol)

        cmd_layout.addStretch()

        # Action Buttons
        self.btn_fit = QPushButton("🔍 Fit")
        self.btn_fit.setToolTip("Fit Entire Month View (Key F)")
        self.btn_fit.clicked.connect(self._fit_content)
        cmd_layout.addWidget(self.btn_fit)

        self.btn_snap = QPushButton("📸 Snapshot")
        self.btn_snap.setToolTip("Copy Chart Screenshot to Clipboard & Save to reports/img")
        self.btn_snap.clicked.connect(self._take_snapshot)
        cmd_layout.addWidget(self.btn_snap)

        main_layout.addWidget(cmd_frame)

        # -------------------------------------------------------------
        # 2. Row 2: Streamlined Quant Telemetry HUD (Compact 28px Strip)
        # -------------------------------------------------------------
        self.hud_frame = QFrame()
        self.hud_frame.setStyleSheet("""
            QFrame {
                background-color: #0b101a;
                border: 1px solid #162032;
                border-radius: 3px;
                padding: 3px 6px;
            }
            QLabel {
                font-family: 'Consolas', monospace;
                font-size: 11px;
                color: #94a3b8;
            }
        """)
        hud_layout = QHBoxLayout(self.hud_frame)
        hud_layout.setContentsMargins(6, 2, 6, 2)
        hud_layout.setSpacing(8)

        self.lbl_hud_signal = QLabel("<b>SIGNAL:</b> Standing by")
        hud_layout.addWidget(self.lbl_hud_signal, stretch=1)
        hud_layout.addWidget(self._make_v_sep())

        self.lbl_hud_pricing = QLabel("<b>PRICING:</b> --")
        hud_layout.addWidget(self.lbl_hud_pricing, stretch=1)
        hud_layout.addWidget(self._make_v_sep())

        self.lbl_hud_oms = QLabel("<b>KINETIC OMS:</b> --")
        hud_layout.addWidget(self.lbl_hud_oms, stretch=1)
        hud_layout.addWidget(self._make_v_sep())

        self.lbl_hud_outcome = QLabel("<b>REALIZED:</b> --")
        hud_layout.addWidget(self.lbl_hud_outcome, stretch=1)

        main_layout.addWidget(self.hud_frame)

        # -------------------------------------------------------------
        # 3. Row 3: TradingView QWebEngineView Container
        # -------------------------------------------------------------
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background-color: #080b11; border: 1px solid #141c2c;")
        main_layout.addWidget(self.web_view, stretch=1)

        # Load blank initial chart
        self._load_chart([], [], [])

    def _make_v_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #1a2436;")
        return sep

    # -------------------------------------------------------------
    # Keyboard Navigation
    # -------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_A):
            self._on_prev_trade()
            event.accept()
        elif key in (Qt.Key_Right, Qt.Key_D):
            self._on_next_trade()
            event.accept()
        elif key == Qt.Key_F:
            self._fit_content()
            event.accept()
        elif key == Qt.Key_B:
            self.chk_lines.setChecked(not self.chk_lines.isChecked())
            event.accept()
        else:
            super().keyPressEvent(event)

    # -------------------------------------------------------------
    # Data Loading & Filtering
    # -------------------------------------------------------------
    def load_data(self, df_m30: pd.DataFrame, trades_list: List[Dict[str, Any]]):
        self.df = df_m30
        self.trades = trades_list

        trade_months = sorted(list(set([t.get('month', '') for t in trades_list if t.get('month')])))
        df_months = sorted(list(df_m30['timestamp_utc'].dt.strftime('%Y-%m').unique())) if (df_m30 is not None and not df_m30.empty and 'timestamp_utc' in df_m30.columns) else []

        months = trade_months if trade_months else df_months

        self.combo_month.blockSignals(True)
        self.combo_month.clear()
        self.combo_month.addItems(months)
        self.combo_month.blockSignals(False)

        if months:
            self.combo_month.setCurrentIndex(len(months) - 1)
            self._on_month_changed(len(months) - 1)

    def _on_month_changed(self, idx: int):
        month = self.combo_month.currentText()
        if not month:
            return
        self.current_month = month
        self._apply_filter()

    def _apply_filter(self):
        if not self.current_month:
            return

        month_trades = [t for t in self.trades if t.get('month') == self.current_month]
        filter_mode = self.combo_filter.currentText()

        if "Wins Only" in filter_mode:
            filtered = [t for t in month_trades if t.get('pnl', 0.0) > 0]
        elif "Losses Only" in filter_mode:
            filtered = [t for t in month_trades if t.get('pnl', 0.0) <= 0]
        elif "Max TP" in filter_mode:
            filtered = [t for t in month_trades if "Max TP" in str(t.get('exit_reason', ''))]
        elif "Protected" in filter_mode:
            filtered = [t for t in month_trades if "Protected" in str(t.get('exit_reason', ''))]
        elif "Time Barrier" in filter_mode:
            filtered = [t for t in month_trades if "Time" in str(t.get('exit_reason', '')) or "Friday" in str(t.get('exit_reason', ''))]
        else:
            filtered = month_trades

        self.filtered_trades = filtered

        self.combo_trade.blockSignals(True)
        self.combo_trade.clear()
        self.combo_trade.addItem(f"— Month Overview ({len(filtered)} trades) —")

        for i, t in enumerate(filtered):
            ts = str(t.get('time', ''))[:16]
            d = t.get('dir', '')
            pnl = t.get('pnl', 0.0)
            reason = str(t.get('exit_reason', '')).split('(')[0].strip()
            pnl_sign = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            self.combo_trade.addItem(f"#{i+1:03d} | {ts} | {d:4s} | {pnl_sign:>8s} | {reason}")

        self.combo_trade.blockSignals(False)

        if len(filtered) > 0:
            self.combo_trade.setCurrentIndex(1)
        else:
            self.combo_trade.setCurrentIndex(0)

    def _on_prev_trade(self):
        cur = self.combo_trade.currentIndex()
        count = self.combo_trade.count()
        if count <= 1:
            return
        new_idx = cur - 1 if cur > 1 else count - 1
        self.combo_trade.setCurrentIndex(new_idx)

    def _on_next_trade(self):
        cur = self.combo_trade.currentIndex()
        count = self.combo_trade.count()
        if count <= 1:
            return
        new_idx = cur + 1 if cur < count - 1 else 1
        self.combo_trade.setCurrentIndex(new_idx)

    def _on_trade_selected(self, idx: int):
        if idx <= 0 or not self.filtered_trades:
            self.selected_trade = None
            self._reset_hud()
            self._render_current_view()
            return

        trade_idx = idx - 1
        if 0 <= trade_idx < len(self.filtered_trades):
            t = self.filtered_trades[trade_idx]
            self.selected_trade = t
            self._update_hud(trade_idx, t)
            self._render_current_view()

    # -------------------------------------------------------------
    # HUD Telemetry Updates
    # -------------------------------------------------------------
    def _reset_hud(self):
        self.lbl_hud_signal.setText("<b>SIGNAL:</b> Month overview")
        self.lbl_hud_pricing.setText("<b>PRICING:</b> Select trade to view levels")
        self.lbl_hud_oms.setText("<b>KINETIC OMS:</b> Brackets ready")
        self.lbl_hud_outcome.setText("<b>REALIZED:</b> --")

    def _update_hud(self, idx: int, t: Dict[str, Any]):
        d = t.get('dir', '')
        ts = str(t.get('time', ''))[:16]
        sess = str(t.get('session', '')).split('(')[0].strip()
        conf = t.get('conf', 0.0)
        pnl = t.get('pnl', 0.0)
        ep = t.get('entry', 0.0)
        exit_p = t.get('exit', 0.0)
        sl_dist = t.get('sl_dist', 0.0)
        reason = str(t.get('exit_reason', ''))
        equity = t.get('equity', 0.0)
        bars_held = t.get('bars_held', 1)
        hours_held = bars_held * 0.5

        sl_val = round(ep - sl_dist, 2) if d == "BUY" else round(ep + sl_dist, 2)
        tp_val = round(ep + (2.7 * sl_dist), 2) if d == "BUY" else round(ep - (2.7 * sl_dist), 2)
        be_val = round(ep + (0.75 * sl_dist), 2) if d == "BUY" else round(ep - (0.75 * sl_dist), 2)
        r_mult = round(pnl / (sl_dist * 1.0), 2) if sl_dist > 0 else 0.0

        dir_color = "#00e676" if d == "BUY" else "#ff5252"
        pnl_color = "#00e676" if pnl >= 0 else "#ff5252"

        lot_val = t.get('lot', 0.01)
        self.lbl_hud_signal.setText(
            f"<b>SIGNAL #{idx+1:03d}:</b> <span style='color:{dir_color}; font-weight:bold;'>[{d}]</span> {ts} "
            f"• <span style='color:#ffd700;'>{sess}</span> • Conf: <b>{conf:.1f}%</b>"
        )
        self.lbl_hud_pricing.setText(
            f"<b>PRICING:</b> Entry: <span style='color:#82b1ff; font-weight:bold;'>${ep:,.2f}</span> | "
            f"Exit: <span style='color:#ffd700;'>${exit_p:,.2f}</span> | "
            f"Lot: <span style='color:#ffd700; font-weight:bold;'>{lot_val:.2f}L</span> | "
            f"Risk: <span style='color:#ff5252;'>${sl_dist:.2f} (1.0R)</span>"
        )
        be_tag = "[ACT]" if (pnl > 0 and "Protected" in reason) else ""
        self.lbl_hud_oms.setText(
            f"<b>OMS:</b> BE: <span style='color:#00e5ff;'>${be_val:,.2f} {be_tag}</span> | "
            f"TP: <span style='color:#00e676;'>${tp_val:,.2f} (+2.7R)</span> | Held: <b>{bars_held}b ({hours_held:.1f}h)</b>"
        )
        self.lbl_hud_outcome.setText(
            f"<b>REALIZED:</b> <span style='color:{pnl_color}; font-weight:bold;'>{pnl:+,.2f} USD ({r_mult:+,.2f}R)</span> "
            f"• <span style='color:#cbd5e1;'>{reason}</span> • Eq: <b>${equity:,.2f}</b>"
        )

    # -------------------------------------------------------------
    # Rendering & HTML Generation
    # -------------------------------------------------------------
    def _render_current_view(self):
        if self.df is None or not self.current_month:
            return

        df_month = self.df[self.df['timestamp_utc'].dt.strftime('%Y-%m') == self.current_month].copy()
        if len(df_month) == 0:
            return

        df_month = df_month.drop_duplicates(subset=['timestamp_utc']).sort_values('timestamp_utc')

        candle_records = []
        volume_records = []
        ema50_records = []
        ema200_records = []

        has_vol = 'volume' in df_month.columns
        has_ema50 = 'ema50' in df_month.columns
        has_ema200 = 'ema200' in df_month.columns

        for _, row in df_month.iterrows():
            ts = int(row['timestamp_utc'].timestamp())
            o = round(float(row['open']), 2)
            h = round(float(row['high']), 2)
            l = round(float(row['low']), 2)
            c = round(float(row['close']), 2)

            candle_records.append({'time': ts, 'open': o, 'high': h, 'low': l, 'close': c})

            if has_vol:
                vol_val = float(row['volume'])
                vol_color = 'rgba(0, 230, 118, 0.35)' if c >= o else 'rgba(255, 82, 82, 0.35)'
                volume_records.append({'time': ts, 'value': vol_val, 'color': vol_color})

            if has_ema50 and not pd.isna(row['ema50']):
                ema50_records.append({'time': ts, 'value': round(float(row['ema50']), 2)})
            if has_ema200 and not pd.isna(row['ema200']):
                ema200_records.append({'time': ts, 'value': round(float(row['ema200']), 2)})

        # ---------------------------------------------------------
        # Build Clutter-Free Markers
        # ---------------------------------------------------------
        markers = []
        show_all_bg = self.chk_all_trades.isChecked()

        # If user toggled Show Other Trades, display them as tiny dots with NO text
        if show_all_bg:
            month_trades = [t for t in self.trades if t.get('month') == self.current_month]
            for t in month_trades:
                if self.selected_trade and t.get('time') == self.selected_trade.get('time'):
                    continue
                try:
                    t_time = int(pd.to_datetime(t.get('time')).timestamp())
                    d = t.get('dir', '')
                    markers.append({
                        'time': t_time,
                        'position': 'belowBar' if d == "BUY" else 'aboveBar',
                        'color': '#00bfa5' if d == "BUY" else '#e57373',
                        'shape': 'circle',
                        'text': '',  # ZERO text clutter!
                        'size': 1
                    })
                except Exception:
                    continue

        # ONLY the Active Selected Trade gets prominent Entry and Exit markers
        if self.selected_trade:
            t = self.selected_trade
            d = t.get('dir', '')
            pnl = t.get('pnl', 0.0)
            lot_val = t.get('lot', 0.01)
            reason = str(t.get('exit_reason', '')).split('(')[0].strip()

            try:
                # 1. Entry Marker
                t_time = int(pd.to_datetime(t.get('time')).timestamp())
                entry_color = '#00e676' if d == "BUY" else '#ff5252'
                markers.append({
                    'time': t_time,
                    'position': 'belowBar' if d == "BUY" else 'aboveBar',
                    'color': entry_color,
                    'shape': 'arrowUp' if d == "BUY" else 'arrowDown',
                    'text': f"ENTRY [{d}] {lot_val:.2f}L",
                    'size': 2
                })

                # 2. Exit Marker (at exit candle)
                if t.get('exit_time'):
                    exit_ts = int(pd.to_datetime(t.get('exit_time')).timestamp())
                    exit_color = '#00e676' if pnl >= 0 else '#ff5252'
                    markers.append({
                        'time': exit_ts,
                        'position': 'aboveBar' if d == "BUY" else 'belowBar',
                        'color': exit_color,
                        'shape': 'circle',
                        'text': f"EXIT: {pnl:+,.1f}$ [{reason}]",
                        'size': 2
                    })
            except Exception:
                pass

        # Sort markers chronologically
        markers.sort(key=lambda m: m['time'])

        # ---------------------------------------------------------
        # Build Clean Price Lines on Axis (Short institutional tags)
        # ---------------------------------------------------------
        price_lines = []
        focus_ts = 0

        if self.selected_trade:
            try:
                focus_ts = int(pd.to_datetime(self.selected_trade.get('time')).timestamp())
            except Exception:
                focus_ts = 0

            if self.chk_lines.isChecked():
                t = self.selected_trade
                d = t.get('dir', '')
                ep = t.get('entry', 0.0)
                exit_p = t.get('exit', 0.0)
                sl_dist = t.get('sl_dist', 0.0)
                pnl = t.get('pnl', 0.0)
                r_mult = round(pnl / (sl_dist * 1.0), 2) if sl_dist > 0 else 0.0

                sl_val = round(ep - sl_dist, 2) if d == "BUY" else round(ep + sl_dist, 2)
                tp_val = round(ep + (2.7 * sl_dist), 2) if d == "BUY" else round(ep - (2.7 * sl_dist), 2)
                be_val = round(ep + (0.75 * sl_dist), 2) if d == "BUY" else round(ep - (0.75 * sl_dist), 2)

                price_lines = [
                    {'price': ep, 'color': '#2979ff', 'title': 'ENTRY', 'style': 'solid', 'lineWidth': 2},
                    {'price': sl_val, 'color': '#ff1744', 'title': 'SL (-1.0R)', 'style': 'dashed', 'lineWidth': 1},
                    {'price': tp_val, 'color': '#00e676', 'title': 'TP (+2.7R)', 'style': 'dashed', 'lineWidth': 1},
                    {'price': be_val, 'color': '#00e5ff', 'title': 'BE (+0.75R)', 'style': 'dotted', 'lineWidth': 1},
                ]

                if exit_p and exit_p > 0:
                    price_lines.append({
                        'price': exit_p,
                        'color': '#ffd700',
                        'title': f'EXIT ({r_mult:+,.1f}R)',
                        'style': 'dotted',
                        'lineWidth': 1
                    })

        self._load_chart(
            candles=candle_records,
            markers=markers,
            lines=price_lines,
            ema50=ema50_records,
            ema200=ema200_records,
            volume=volume_records,
            focus_ts=focus_ts
        )

    def _load_chart(
        self,
        candles: list,
        markers: list,
        lines: list,
        ema50: list = None,
        ema200: list = None,
        volume: list = None,
        focus_ts: int = 0
    ):
        candles_json = json.dumps(candles)
        markers_json = json.dumps(markers)
        lines_json = json.dumps(lines)
        ema50_json = json.dumps(ema50 or [])
        ema200_json = json.dumps(ema200 or [])
        volume_json = json.dumps(volume or [])

        html = get_tradingview_html(
            candles_json=candles_json,
            markers_json=markers_json,
            lines_json=lines_json,
            ema50_json=ema50_json,
            ema200_json=ema200_json,
            volume_json=volume_json,
            show_ema50=self.chk_ema50.isChecked(),
            show_ema200=self.chk_ema200.isChecked(),
            show_volume=self.chk_vol.isChecked(),
            focus_ts=focus_ts
        )
        self.web_view.setHtml(html, QUrl("file:///"))

    def _fit_content(self):
        self.web_view.page().runJavaScript("if (typeof chart !== 'undefined') chart.timeScale().fitContent();")

    def _take_snapshot(self):
        out_dir = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\reports\img")
        out_dir.mkdir(parents=True, exist_ok=True)

        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        trade_label = "all"
        if self.selected_trade:
            t_dir = self.selected_trade.get('dir', 'trade')
            t_month = self.selected_trade.get('month', 'audit')
            trade_label = f"{t_month}_{t_dir}_{self.combo_trade.currentIndex()}"

        file_path = out_dir / f"tv_snapshot_{trade_label}_{now_str}.png"

        pixmap = self.web_view.grab()
        pixmap.save(str(file_path), "PNG")
        QApplication.clipboard().setPixmap(pixmap)

        self.lbl_hud_signal.setText(f"<b>[SNAPSHOT SAVED]</b> {file_path.name} (copied to clipboard)")
