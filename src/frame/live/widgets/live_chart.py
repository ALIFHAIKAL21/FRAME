"""
FLOWDEV FRAME - Low-Latency Real-Time Candlestick Chart Widget
Hardware-accelerated WebGL Lightweight Chart updating tick-by-tick.
Draws live forming candles, entry lines, dynamic SL ratchet/trail lines, and TP targets.
Uses bundled offline Lightweight Charts library for 0ms network latency and 60 FPS rendering.
"""

import json, pathlib
from typing import List, Dict, Any, Optional

try:
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame
    from PyQt6.QtCore import Qt, QUrl
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

def get_live_chart_html() -> str:
    js_bundle = _get_live_js_bundle()
    # Fallback to CDN only if local file cannot be found
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
            background-color: #080c14; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        #chart {{ width: 100%; height: 100%; }}
        #badge {{
            position: absolute; top: 10px; left: 14px; z-index: 10;
            background: rgba(13, 17, 26, 0.85); border: 1px solid #1c2638;
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
        <span class="live">● LIVE</span> XAU/USD M30 &nbsp;|&nbsp; 
        BID: <span id="b_bid" class="val">—</span> &nbsp;|&nbsp; 
        ASK: <span id="b_ask" class="val">—</span> &nbsp;|&nbsp; 
        SPREAD: <span id="b_spd" class="val">—</span>
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
                    background: {{ color: '#080c14' }},
                    textColor: '#8b949e',
                    fontSize: 11,
                    fontFamily: 'Consolas, monospace',
                }},
                grid: {{
                    vertLines: {{ color: 'rgba(255, 255, 255, 0.04)' }},
                    horzLines: {{ color: 'rgba(255, 255, 255, 0.04)' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {{ color: '#00bfa5', width: 1, style: 2 }},
                    horzLine: {{ color: '#00bfa5', width: 1, style: 2 }},
                }},
                rightPriceScale: {{
                    borderColor: '#1c2638',
                    autoScale: true,
                }},
                timeScale: {{
                    borderColor: '#1c2638',
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

        function updateCandleWithHUD(c, bid, ask, spd) {{
            if (!candleSeries) initChart();
            if (candleSeries && c) {{
                candleSeries.update(c);
            }}
            updateTickHUD(bid, ask, spd);
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
                title: `${{dir}} ${{lot}}L @ ${{entry.toFixed(2)}}`,
            }});

            slLine = candleSeries.createPriceLine({{
                price: sl,
                color: '#ff1744',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `SL: ${{sl.toFixed(2)}}`,
            }});

            tpLine = candleSeries.createPriceLine({{
                price: tp,
                color: '#00e676',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `TP (+2.7R) @ ${{tp.toFixed(2)}}`,
            }});
        }}

        function updateSLLine(new_sl, stageTitle) {{
            if (slLine) {{
                slLine.applyOptions({{
                    price: new_sl,
                    title: `SL [${{stageTitle}}] @ ${{new_sl.toFixed(2)}}`,
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
</html>
"""

class LiveRealtimeChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
        self.web_view.setHtml(get_live_chart_html())
        layout.addWidget(self.web_view)

        self.candles_history: List[Dict[str, Any]] = []

    def set_initial_candles(self, candles: List[Dict[str, Any]]):
        self.candles_history = list(candles)
        data_json = json.dumps(candles)
        js = f"if (typeof loadCandles === 'function') {{ loadCandles({data_json}); }}"
        self.web_view.page().runJavaScript(js)

    def on_tick(self, tick_data: dict):
        bid = tick_data.get("bid", 0.0)
        ask = tick_data.get("ask", 0.0)
        spd = tick_data.get("spread", 0.0)
        js = f"if (typeof updateTickHUD === 'function') {{ updateTickHUD({bid}, {ask}, {spd}); }}"
        self.web_view.page().runJavaScript(js)

    def on_candle_updated(self, candle: dict):
        c_clean = {
            "time": int(candle["time"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"])
        }
        data_json = json.dumps(c_clean)
        js = f"if (typeof updateCandle === 'function') {{ updateCandle({data_json}); }}"
        self.web_view.page().runJavaScript(js)

    def update_tick_and_candle(self, tick: dict, candle: dict):
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        spd = float(tick.get("spread", 0.0))
        c_clean = {
            "time": int(candle["time"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"])
        }
        data_json = json.dumps(c_clean)
        js = f"if (typeof updateCandleWithHUD === 'function') {{ updateCandleWithHUD({data_json}, {bid}, {ask}, {spd}); }}"
        self.web_view.page().runJavaScript(js)

    def display_active_order(self, pos: dict):
        entry = float(pos["entry_price"])
        sl = float(pos["current_sl"])
        tp = float(pos["current_tp"])
        direction = str(pos["direction"])
        lot = float(pos["lot"])
        js = f"if (typeof setOrderLines === 'function') {{ setOrderLines({entry}, {sl}, {tp}, '{direction}', {lot}); }}"
        self.web_view.page().runJavaScript(js)

    def update_sl_line(self, new_sl: float, stage_label: str):
        js = f"if (typeof updateSLLine === 'function') {{ updateSLLine({new_sl}, '{stage_label}'); }}"
        self.web_view.page().runJavaScript(js)

    def clear_order_lines(self):
        js = "if (typeof clearOrderLines === 'function') { clearOrderLines(); }"
        self.web_view.page().runJavaScript(js)
