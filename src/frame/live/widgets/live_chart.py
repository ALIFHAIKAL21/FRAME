"""
FLOWDEV FRAME - Low-Latency Real-Time Candlestick Chart Widget
Hardware-accelerated WebGL Lightweight Chart updating tick-by-tick.
Draws live forming candles, entry lines, dynamic SL ratchet/trail lines, and TP targets.
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

LIVE_CHART_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Live Realtime Chart</title>
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body, html {
            margin: 0; padding: 0; width: 100%; height: 100%;
            background-color: #080c14; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        #chart { width: 100%; height: 100%; }
        #badge {
            position: absolute; top: 10px; left: 14px; z-index: 10;
            background: rgba(13, 17, 26, 0.85); border: 1px solid #1c2638;
            border-radius: 4px; padding: 4px 8px; font-size: 11px;
            color: #8b949e; font-family: 'Consolas', monospace; pointer-events: none;
        }
        #badge span.val { color: #f0f6fc; font-weight: bold; }
        #badge span.live { color: #00e676; font-weight: bold; animation: blink 1.2s infinite; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
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

        function initChart() {
            chart = LightweightCharts.createChart(document.getElementById('chart'), {
                layout: {
                    background: { color: '#080c14' },
                    textColor: '#8b949e',
                    fontSize: 11,
                    fontFamily: 'Consolas, monospace',
                },
                grid: {
                    vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                    horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: { color: '#00bfa5', width: 1, style: 2 },
                    horzLine: { color: '#00bfa5', width: 1, style: 2 },
                },
                rightPriceScale: {
                    borderColor: '#1c2638',
                    autoScale: true,
                },
                timeScale: {
                    borderColor: '#1c2638',
                    timeVisible: true,
                    secondsVisible: false,
                },
            });

            candleSeries = chart.addCandlestickSeries({
                upColor: '#00e676',
                downColor: '#ff5252',
                borderUpColor: '#00e676',
                borderDownColor: '#ff5252',
                wickUpColor: '#00e676',
                wickDownColor: '#ff5252',
            });

            window.addEventListener('resize', () => {
                chart.resize(window.innerWidth, window.innerHeight);
            });
        }

        function loadCandles(candles) {
            if (!candleSeries) initChart();
            candleSeries.setData(candles);
            chart.timeScale().fitContent();
        }

        function updateCandle(c) {
            if (!candleSeries) return;
            candleSeries.update(c);
        }

        function updateTickHUD(bid, ask, spd) {
            document.getElementById('b_bid').innerText = bid.toFixed(2);
            document.getElementById('b_ask').innerText = ask.toFixed(2);
            document.getElementById('b_spd').innerText = '$' + spd.toFixed(2);
        }

        function setOrderLines(entry, sl, tp, dir, lot) {
            clearOrderLines();
            if (!candleSeries) return;

            const isBuy = (dir === 'BUY');
            const entryColor = isBuy ? '#2979ff' : '#ff9100';

            entryLine = candleSeries.createPriceLine({
                price: entry,
                color: entryColor,
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: `${dir} ${lot}L @ ${entry.toFixed(2)}`,
            });

            slLine = candleSeries.createPriceLine({
                price: sl,
                color: '#ff1744',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `SL: ${sl.toFixed(2)}`,
            });

            tpLine = candleSeries.createPriceLine({
                price: tp,
                color: '#00e676',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `TP (+2.7R) @ ${tp.toFixed(2)}`,
            });
        }

        function updateSLLine(new_sl, stageTitle) {
            if (slLine) {
                slLine.applyOptions({
                    price: new_sl,
                    title: `SL [${stageTitle}] @ ${new_sl.toFixed(2)}`,
                });
            }
        }

        function clearOrderLines() {
            if (entryLine) { candleSeries.removePriceLine(entryLine); entryLine = null; }
            if (slLine) { candleSeries.removePriceLine(slLine); slLine = null; }
            if (tpLine) { candleSeries.removePriceLine(tpLine); tpLine = null; }
        }

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
        self.web_view.setHtml(LIVE_CHART_HTML)
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
