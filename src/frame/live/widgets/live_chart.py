import json, pathlib
from typing import List, Dict, Any, Optional

try:
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QButtonGroup, QSizePolicy
    from PySide6.QtCore import Qt, QUrl, Signal
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QButtonGroup, QSizePolicy
    from PyQt6.QtCore import Qt, QUrl, pyqtSignal as Signal
    from PyQt6.QtWebEngineWidgets import QWebEngineView

_LIVE_JS_CACHED = None

def _get_live_js_bundle() -> str:
    global _LIVE_JS_CACHED
    if _LIVE_JS_CACHED is None:
        possible_paths = [
            pathlib.Path(__file__).resolve().parent.parent.parent / "gui" / "assets" / "lightweight-charts.standalone.production.js",
            pathlib.Path(r"c:\Ngoding\bot_trading\src\frame\gui\assets\lightweight-charts.standalone.production.js"),
        ]
        for p in possible_paths:
            if p.exists():
                _LIVE_JS_CACHED = p.read_text(encoding="utf-8")
                break
        if _LIVE_JS_CACHED is None:
            _LIVE_JS_CACHED = ""
    return _LIVE_JS_CACHED

def get_tradingview_html(symbol: str = "OANDA:XAUUSD", interval: str = "30") -> str:
    """Official TradingView Advanced Real-Time Chart Widget (Sub-millisecond WebSocket streaming)."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <style>
        body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; background-color: #050505; overflow: hidden; }}
        .tradingview-widget-container {{ width: 100%; height: 100%; }}
    </style>
</head>
<body>
    <div class="tradingview-widget-container">
        <div id="tv_chart" style="width: 100%; height: 100%;"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
            new TradingView.widget({{
                "autosize": true,
                "symbol": "{symbol}",
                "interval": "{interval}",
                "timezone": "Asia/Jakarta",
                "theme": "dark",
                "style": "1",
                "locale": "en",
                "toolbar_bg": "#050505",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "hide_side_toolbar": false,
                "allow_symbol_change": true,
                "container_id": "tv_chart",
                "backgroundColor": "#050505",
                "gridColor": "rgba(255, 255, 255, 0.055)",
                "overrides": {{
                    "paneProperties.background": "#050505",
                    "paneProperties.backgroundType": "solid",
                    "paneProperties.vertGridProperties.color": "#151515",
                    "paneProperties.horzGridProperties.color": "#151515",
                    "scalesProperties.textColor": "#a3a3a3",
                    "mainSeriesProperties.candleStyle.upColor": "#00c896",
                    "mainSeriesProperties.candleStyle.downColor": "#ff5252",
                    "mainSeriesProperties.candleStyle.borderUpColor": "#00c896",
                    "mainSeriesProperties.candleStyle.borderDownColor": "#ff5252",
                    "mainSeriesProperties.candleStyle.wickUpColor": "#00c896",
                    "mainSeriesProperties.candleStyle.wickDownColor": "#ff5252"
                }},
                "withdateranges": true,
                "hide_volume": false,
                "save_image": false,
                "details": false,
                "hotlist": false,
                "calendar": false
            }});
        </script>
    </div>
</body>
</html>"""

def get_lightweight_chart_html() -> str:
    js_bundle = _get_live_js_bundle()
    script_tag = f"<script>{js_bundle}</script>" if js_bundle else '<script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>'
    
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Live Realtime Chart</title>
    {script_tag}
    <style>
        body, html {{
            margin: 0; padding: 0; width: 100%; height: 100%;
            background-color: #050505; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        #chart {{ width: 100%; height: 100%; }}
        #badge {{
            position: absolute; top: 10px; left: 14px; z-index: 10;
            background: rgba(5, 5, 5, 0.92); border: 1px solid #242424;
            border-radius: 4px; padding: 4px 8px; font-size: 11px;
            color: #8b949e; font-family: 'Consolas', monospace; pointer-events: none;
        }}
        #badge span.val {{ color: #f0f6fc; font-weight: bold; }}
        #badge span.live {{ color: #00e676; font-weight: bold; animation: blink 1.2s infinite; }}
        @keyframes blink {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}
    </style>
</head>
<body>
    <div id="badge">
        <span class="live">● LIVE</span> <span id="b_tf">XAU/USD M30</span> &nbsp;|&nbsp; 
        BID: <span id="b_bid" class="val">--</span> &nbsp;|&nbsp; 
        ASK: <span id="b_ask" class="val">--</span> &nbsp;|&nbsp; 
        SPREAD: <span id="b_spd" class="val">--</span>
    </div>
    <div id="chart"></div>

    <script>
        let chart = null;
        let candleSeries = null;
        let entryLine = null;
        let slLine = null;
        let tpLine = null;

        function initChart() {{
            if (chart) return;
            const container = document.getElementById('chart');
            if (!container) return;

            chart = LightweightCharts.createChart(container, {{
                layout: {{
                    background: {{ color: '#050505' }},
                    textColor: '#8b949e',
                    fontSize: 11,
                    fontFamily: 'Consolas, monospace',
                }},
                grid: {{
                    vertLines: {{ color: 'rgba(255, 255, 255, 0.035)' }},
                    horzLines: {{ color: 'rgba(255, 255, 255, 0.035)' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {{ color: '#00bfa5', width: 1, style: 2 }},
                    horzLine: {{ color: '#00bfa5', width: 1, style: 2 }},
                }},
                rightPriceScale: {{
                    borderColor: '#242424',
                    autoScale: true,
                }},
                timeScale: {{
                    borderColor: '#242424',
                    timeVisible: true,
                    secondsVisible: false,
                }},
            }});

            candleSeries = chart.addCandlestickSeries({{
                upColor: '#00e676',
                downColor: '#ff5252',
                borderUpColor: '#00e676',
                borderDownColor: '#ff5252',
                wickUpColor: '#00e676',
                wickDownColor: '#ff5252',
            }});

            window.addEventListener('resize', () => {{
                if (chart) chart.resize(window.innerWidth, window.innerHeight);
            }});
        }}

        function loadCandles(candles) {{
            if (!candleSeries) initChart();
            if (candleSeries && candles && candles.length > 0) {{
                candleSeries.setData(candles);
                chart.timeScale().fitContent();
            }}
        }}

        function updateCandle(c) {{
            if (!candleSeries) initChart();
            if (candleSeries && c) {{
                candleSeries.update(c);
            }}
        }}

        function updateTickHUD(bid, ask, spd) {{
            const b1 = document.getElementById('b_bid');
            if (b1) {{
                b1.innerText = Number(bid).toFixed(2);
                document.getElementById('b_ask').innerText = Number(ask).toFixed(2);
                document.getElementById('b_spd').innerText = '$' + Number(spd).toFixed(2);
            }}
        }}

        function setOrderLines(entry, sl, tp, dir, lot) {{
            clearOrderLines();
            if (!candleSeries) return;

            const isBuy = (dir === 'BUY');
            const entryColor = isBuy ? '#2979ff' : '#ff9100';

            entryLine = candleSeries.createPriceLine({{
                price: entry,
                color: entryColor,
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: `${dir} ${lot}L @ ${entry.toFixed(2)}`,
            }});

            slLine = candleSeries.createPriceLine({{
                price: sl,
                color: '#ff1744',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `SL: ${sl.toFixed(2)}`,
            }});

            tpLine = candleSeries.createPriceLine({{
                price: tp,
                color: '#00e676',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `TP (+2.7R) @ ${tp.toFixed(2)}`,
            }});
        }}

        function updateSLLine(new_sl, stageTitle) {{
            if (slLine) {{
                slLine.applyOptions({{
                    price: new_sl,
                    title: `SL [${stageTitle}] @ ${new_sl.toFixed(2)}`,
                }});
            }}
        }}

        function clearOrderLines() {{
            if (candleSeries) {{
                if (entryLine) {{ candleSeries.removePriceLine(entryLine); entryLine = null; }}
                if (slLine) {{ candleSeries.removePriceLine(slLine); slLine = null; }}
                if (tpLine) {{ candleSeries.removePriceLine(tpLine); tpLine = null; }}
            }}
        }}

        window.onload = initChart;
    </script>
</body>
</html>"""


class TradeOverlayCard(QFrame):
    """
    Floating institutional HUD pinned over the live chart canvas.
    Displays active trade levels (Entry, SL, TP, RR, floating PnL) in both
    TradingView and Flowdev OMS modes.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("""
            TradeOverlayCard {
                background-color: rgba(5, 5, 5, 0.96);
                border: 1px solid #242424;
                border-radius: 6px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        # Header row: Direction & Lot | PnL
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.lbl_dir = QLabel("BUY 0.01L")
        self.lbl_dir.setStyleSheet("""
            background-color: #1e3a8a; color: #93c5fd; font-weight: 800;
            padding: 3px 8px; border-radius: 3px; font-size: 11px; font-family: monospace;
        """)
        top_row.addWidget(self.lbl_dir)

        self.lbl_pnl = QLabel("+$0.00")
        self.lbl_pnl.setStyleSheet("font-size: 13px; font-weight: 800; font-family: monospace; color: #00e676;")
        top_row.addWidget(self.lbl_pnl)
        top_row.addStretch()

        self.lbl_stage = QLabel("STAGE 0")
        self.lbl_stage.setStyleSheet("color: #38bdf8; font-size: 9.5px; font-family: monospace; font-weight: 700; background: #0c1c2e; padding: 2px 6px; border-radius: 2px; border: 1px solid #1e3a5f;")
        top_row.addWidget(self.lbl_stage)
        layout.addLayout(top_row)

        # Levels grid: TP, ENTRY, SL
        self.lbl_tp = QLabel("🟢 TP (+2.7R): $0.00")
        self.lbl_tp.setStyleSheet("color: #00e676; font-size: 10.5px; font-family: monospace; font-weight: 700;")
        layout.addWidget(self.lbl_tp)

        self.lbl_entry = QLabel("🔵 ENTRY:     $0.00")
        self.lbl_entry.setStyleSheet("color: #93c5fd; font-size: 10.5px; font-family: monospace; font-weight: 600;")
        layout.addWidget(self.lbl_entry)

        self.lbl_sl = QLabel("🔴 SL:         $0.00")
        self.lbl_sl.setStyleSheet("color: #ff5252; font-size: 10.5px; font-family: monospace; font-weight: 700;")
        layout.addWidget(self.lbl_sl)

        self.set_standby()

    def set_standby(self):
        self.hide()

    def update_position(self, pos: dict, live_price: Optional[float] = None):
        if not pos or not pos.get("direction"):
            self.set_standby()
            return

        d = str(pos.get("direction", "BUY")).upper()
        lot = float(pos.get("lot", 0.01))
        ep = float(pos.get("entry_price", 0.0))
        sl = float(pos.get("current_sl", pos.get("sl_price", 0.0)))
        tp = float(pos.get("current_tp", pos.get("tp_price", 0.0)))
        pnl = float(pos.get("floating_pnl", 0.0))
        r_val = float(pos.get("floating_r", 0.0))

        if d == "BUY":
            self.lbl_dir.setText(f"BUY {lot:.2f}L")
            self.lbl_dir.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-weight: 800; padding: 3px 8px; border-radius: 3px; font-size: 11px; font-family: monospace;")
        else:
            self.lbl_dir.setText(f"SELL {lot:.2f}L")
            self.lbl_dir.setStyleSheet("background-color: #7c2d12; color: #fdba74; font-weight: 800; padding: 3px 8px; border-radius: 3px; font-size: 11px; font-family: monospace;")

        pnl_col = "#00e676" if pnl >= 0 else "#ff5252"
        self.lbl_pnl.setText(f"{'+' if pnl>=0 else ''}${pnl:,.2f} ({r_val:+.2f}R)")
        self.lbl_pnl.setStyleSheet(f"font-size: 13px; font-weight: 800; font-family: monospace; color: {pnl_col};")

        tp_diff = abs(tp - ep)
        sl_diff = abs(ep - sl)
        self.lbl_tp.setText(f"🟢 TP (+2.7R): ${tp:,.2f}  (+${tp_diff:.2f})")
        mkt_str = f"  [MKT: ${live_price:,.2f}]" if live_price else ""
        self.lbl_entry.setText(f"🔵 ENTRY:     ${ep:,.2f}{mkt_str}")
        self.lbl_sl.setText(f"🔴 SL:         ${sl:,.2f}  (-${sl_diff:.2f})")

        stage = "STAGE 0: INITIAL SL"
        if pos.get("trail_activated"):
            stage = "STAGE 3: TRAILING"
        elif pos.get("ratchet_activated"):
            stage = "STAGE 2: RATCHET"
        elif pos.get("be_activated"):
            stage = "STAGE 1: MICRO-BE"
        elif pos.get("stale_decay_activated"):
            stage = "STAGE 4: STALE"
        self.lbl_stage.setText(stage)

        self.adjustSize()
        self.show()
        self.raise_()

    def update_sl(self, new_sl: float, stage_title: str):
        self.lbl_sl.setText(f"🔴 SL [{stage_title}]: ${new_sl:,.2f}")
        self.lbl_stage.setText(stage_title)
        self.adjustSize()


class LiveRealtimeChartWidget(QWidget):
    timeframe_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.current_timeframe = "30M"
        self.chart_mode = "tradingview"  # "tradingview" or "flowdev_oms"
        self.candles_history: List[Dict[str, Any]] = []
        self.active_position: Optional[Dict[str, Any]] = None

        # -------------------------------------------------------------
        # 1. Institutional Multi-Timeframe Toolbar
        # -------------------------------------------------------------
        self.toolbar = QFrame()
        self.toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toolbar.setFixedHeight(38)
        self.toolbar.setStyleSheet("""
            QFrame {
                background-color: #050505;
                border-bottom: 1px solid #202020;
                padding: 4px 8px;
            }
        """)
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(4, 2, 4, 4)
        tb_layout.setSpacing(4)

        lbl_tf = QLabel("TIMEFRAME:")
        lbl_tf.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800; font-family: monospace;")
        tb_layout.addWidget(lbl_tf)

        self.tf_buttons = {}
        self.tf_group = QButtonGroup(self)
        self.tf_group.setExclusive(True)

        timeframes = [("1M", "1"), ("5M", "5"), ("15M", "15"), ("30M", "30"), ("1H", "60"), ("4H", "240"), ("1D", "D")]
        for tf_label, tv_res in timeframes:
            btn = QPushButton(tf_label)
            btn.setCheckable(True)
            btn.setChecked(tf_label == "30M")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #090909; border: 1px solid #292929;
                    color: #8b949e; font-size: 10.5px; font-weight: 700;
                    padding: 3px 8px; border-radius: 2px; font-family: monospace;
                }
                QPushButton:hover { background-color: #1b1b1b; color: #f0f6fc; }
                QPushButton:checked {
                    background-color: #004d40; border: 1px solid #00bfa5;
                    color: #00e676; font-weight: 800;
                }
            """)
            btn.clicked.connect(lambda _, l=tf_label: self.set_timeframe(l))
            self.tf_group.addButton(btn)
            self.tf_buttons[tf_label] = btn
            tb_layout.addWidget(btn)

        tb_layout.addSpacing(12)

        # Mode Selector (TradingView vs Flowdev OMS)
        self.btn_mode_tv = QPushButton("📊 TRADINGVIEW LIVE")
        self.btn_mode_tv.setCheckable(True)
        self.btn_mode_tv.setChecked(True)
        self.btn_mode_tv.setStyleSheet("""
            QPushButton {
                background-color: #090909; border: 1px solid #292929;
                color: #8b949e; font-size: 10.5px; font-weight: 700;
                padding: 3px 8px; border-radius: 2px;
            }
            QPushButton:checked {
                background-color: #181818; border: 1px solid #5a5a5a;
                color: #f0f0f0; font-weight: 800;
            }
        """)
        self.btn_mode_tv.clicked.connect(lambda: self.set_chart_mode("tradingview"))

        self.btn_mode_oms = QPushButton("⚡ FLOWDEV OMS WEBGL")
        self.btn_mode_oms.setCheckable(True)
        self.btn_mode_oms.setStyleSheet("""
            QPushButton {
                background-color: #090909; border: 1px solid #292929;
                color: #8b949e; font-size: 10.5px; font-weight: 700;
                padding: 3px 8px; border-radius: 2px;
            }
            QPushButton:checked {
                background-color: #181818; border: 1px solid #5a5a5a;
                color: #f0f0f0; font-weight: 800;
            }
        """)
        self.btn_mode_oms.clicked.connect(lambda: self.set_chart_mode("flowdev_oms"))

        tb_layout.addWidget(self.btn_mode_tv)
        tb_layout.addWidget(self.btn_mode_oms)

        tb_layout.addStretch()

        # Engine Safety Tag
        lbl_safety = QLabel("[🔒 AI SNIPER ENGINE: LOCKED TO M30]")
        lbl_safety.setStyleSheet("color: #b8b8b8; font-size: 10px; font-weight: 800; font-family: monospace; background: #080808; padding: 2px 6px; border: 1px solid #292929; border-radius: 2px;")
        tb_layout.addWidget(lbl_safety)

        layout.addWidget(self.toolbar)

        # -------------------------------------------------------------
        # 2. Web Engine View & Floating Order Overlay
        # -------------------------------------------------------------
        self.web_view = QWebEngineView(self)
        self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.web_view.setMinimumHeight(250)
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
        layout.addWidget(self.web_view)

        # Visual SL/TP Floating Card (Visible on both TradingView & OMS modes)
        self.overlay_card = TradeOverlayCard(self.web_view)

        self._reload_chart_html()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlay()

    def _reposition_overlay(self):
        if hasattr(self, "overlay_card") and self.overlay_card:
            w = self.web_view.width()
            card_w = self.overlay_card.sizeHint().width()
            target_x = max(10, w - max(card_w, 240) - 20)
            self.overlay_card.move(target_x, 15)
            self.overlay_card.raise_()

    def _get_tv_symbol(self) -> str:
        sym = getattr(self, "symbol", "XAUUSD").upper()
        if "BTC" in sym:
            return "BINANCE:BTCUSDT"
        return "OANDA:XAUUSD"

    def set_symbol(self, symbol: str):
        self.symbol = symbol.upper()
        self._reload_chart_html()

    def _get_tv_interval(self, tf_label: str) -> str:
        mapping = {
            "1M": "1", "5M": "5", "15M": "15", "30M": "30",
            "1H": "60", "4H": "240", "1D": "D"
        }
        return mapping.get(tf_label, "30")

    def _reload_chart_html(self):
        if self.chart_mode == "tradingview":
            tv_res = self._get_tv_interval(self.current_timeframe)
            tv_sym = self._get_tv_symbol()
            html = get_tradingview_html(symbol=tv_sym, interval=tv_res)
            self.web_view.setHtml(html)
        else:
            self.web_view.setHtml(get_lightweight_chart_html())
            if self.candles_history:
                data_json = json.dumps(self.candles_history)
                js = f"setTimeout(function() {{ if (typeof loadCandles === 'function') {{ loadCandles({data_json}); }} }}, 200);"
                self.web_view.page().runJavaScript(js)

        # Restore active order visuals if an order is currently active
        if self.active_position:
            pos = self.active_position
            self.overlay_card.update_position(pos)
            self._reposition_overlay()
            if self.chart_mode == "flowdev_oms":
                p_dir = pos.get("direction", "BUY")
                p_ep = float(pos.get("entry_price", 0.0))
                p_sl = float(pos.get("current_sl", pos.get("sl_price", 0.0)))
                p_tp = float(pos.get("current_tp", pos.get("tp_price", 0.0)))
                p_lot = float(pos.get("lot", 0.01))
                js_lines = f"setTimeout(function() {{ if (typeof setOrderLines === 'function') {{ setOrderLines({p_ep}, {p_sl}, {p_tp}, '{p_dir}', {p_lot}); }} }}, 400);"
                self.web_view.page().runJavaScript(js_lines)

    def set_chart_mode(self, mode: str):
        if self.chart_mode != mode:
            self.chart_mode = mode
            self.btn_mode_tv.setChecked(mode == "tradingview")
            self.btn_mode_oms.setChecked(mode == "flowdev_oms")
            self._reload_chart_html()

    def set_timeframe(self, tf_label: str):
        self.current_timeframe = tf_label
        if tf_label in self.tf_buttons:
            self.tf_buttons[tf_label].setChecked(True)
        self._reload_chart_html()
        self.timeframe_changed.emit(tf_label)

    def set_initial_candles(self, candles: List[Dict[str, Any]]):
        self.candles_history = list(candles)
        if self.chart_mode == "flowdev_oms":
            data_json = json.dumps(candles)
            js = f"if (typeof loadCandles === 'function') {{ loadCandles({data_json}); }}"
            self.web_view.page().runJavaScript(js)

    def on_tick(self, tick_data: dict):
        if self.chart_mode == "flowdev_oms":
            bid = tick_data.get("bid", 0.0)
            ask = tick_data.get("ask", 0.0)
            spd = tick_data.get("spread", 0.0)
            js = f"if (typeof updateTickHUD === 'function') {{ updateTickHUD({bid}, {ask}, {spd}); }}"
            self.web_view.page().runJavaScript(js)

    def on_candle_updated(self, candle: dict):
        if self.chart_mode == "flowdev_oms":
            c_clean = {
                "time": int(candle["time"]),
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"])
            }
            c_json = json.dumps(c_clean)
            js = f"if (typeof updateCandle === 'function') {{ updateCandle({c_json}); }}"
            self.web_view.page().runJavaScript(js)

    def update_tick_and_candle(self, tick_data: dict, candle: dict):
        if self.chart_mode == "flowdev_oms":
            c_clean = {
                "time": int(candle["time"]),
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"])
            }
            c_json = json.dumps(c_clean)
            bid = tick_data.get("bid", 0.0)
            ask = tick_data.get("ask", 0.0)
            spd = tick_data.get("spread", 0.0)
            js = f"if (typeof updateCandleWithHUD === 'function') {{ updateCandleWithHUD({c_json}, {bid}, {ask}, {spd}); }}"
            self.web_view.page().runJavaScript(js)

    def display_active_order(self, pos: dict, live_price: Optional[float] = None):
        """Displays visual TP/SL markers and overlay on the chart."""
        if not pos or not pos.get("direction"):
            self.clear_order_lines()
            return
        self.active_position = dict(pos)
        self.overlay_card.update_position(pos, live_price)
        self._reposition_overlay()

        if self.chart_mode == "flowdev_oms":
            direction = pos.get("direction", "BUY")
            entry_price = float(pos.get("entry_price", 0.0))
            sl_price = float(pos.get("current_sl", pos.get("sl_price", 0.0)))
            tp_price = float(pos.get("current_tp", pos.get("tp_price", 0.0)))
            lot = float(pos.get("lot", 0.01))
            self.draw_order_lines(direction, entry_price, sl_price, tp_price, lot)

    def draw_order_lines(self, direction: str, entry_price: float, sl_price: float, tp_price: float, lot: float = 0.01):
        if self.chart_mode == "flowdev_oms":
            js = f"if (typeof setOrderLines === 'function') {{ setOrderLines({entry_price}, {sl_price}, {tp_price}, '{direction}', {lot}); }}"
            self.web_view.page().runJavaScript(js)

    def update_sl_line(self, new_sl: float, stage_title: str):
        if self.active_position:
            self.active_position["current_sl"] = new_sl
        self.overlay_card.update_sl(new_sl, stage_title)
        self._reposition_overlay()

        if self.chart_mode == "flowdev_oms":
            js = f"if (typeof updateSLLine === 'function') {{ updateSLLine({new_sl}, '{stage_title}'); }}"
            self.web_view.page().runJavaScript(js)

    def clear_order_lines(self):
        self.active_position = None
        self.overlay_card.set_standby()
        if self.chart_mode == "flowdev_oms":
            js = "if (typeof clearOrderLines === 'function') { clearOrderLines(); }"
            self.web_view.page().runJavaScript(js)
