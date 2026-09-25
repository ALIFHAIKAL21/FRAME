"""
TradingView Lightweight Charts Template Generator
Generates self-contained HTML/JS using the local TradingView library.
Engineered for ultra-clean, clutter-free institutional quant audit.
"""

import pathlib, json
from typing import List, Dict, Any

_JS_CACHED = None

def _get_js_bundle() -> str:
    global _JS_CACHED
    if _JS_CACHED is None:
        js_path = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\src\frame\gui\assets\lightweight-charts.standalone.production.js")
        if js_path.exists():
            _JS_CACHED = js_path.read_text(encoding="utf-8")
        else:
            _JS_CACHED = ""
    return _JS_CACHED

def get_tradingview_html(
    candles_json: str,
    markers_json: str,
    lines_json: str,
    ema50_json: str = "[]",
    ema200_json: str = "[]",
    volume_json: str = "[]",
    show_ema50: bool = False,
    show_ema200: bool = False,
    show_volume: bool = False,
    focus_ts: int = 0
) -> str:
    js_code = _get_js_bundle()
    show_ema50_str = str(show_ema50).lower()
    show_ema200_str = str(show_ema200).lower()
    show_volume_str = str(show_volume).lower()

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>TradingView FRAME Inspector</title>
    <script>
    {js_code}
    </script>
    <style>
        body, html {{
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            background-color: #080b11;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            user-select: none;
        }}
        #chart {{
            width: 100%;
            height: 100%;
        }}
        #legend {{
            position: absolute;
            left: 10px;
            top: 10px;
            z-index: 999;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 11px;
            color: #8b949e;
            pointer-events: none;
            background: rgba(8, 11, 17, 0.88);
            padding: 4px 8px;
            border-radius: 3px;
            border: 1px solid #1a2233;
            box-shadow: 0 4px 10px rgba(0,0,0,0.5);
        }}
        .symbol-badge {{
            color: #d4af37;
            font-weight: 700;
            margin-right: 8px;
        }}
        .ohlc-val {{
            color: #e6edf3;
            margin-right: 5px;
        }}
        .bull-text {{ color: #00e676; font-weight: bold; }}
        .bear-text {{ color: #ff5252; font-weight: bold; }}

        #tooltip {{
            position: absolute;
            display: none;
            padding: 6px 10px;
            box-sizing: border-box;
            font-size: 11px;
            text-align: left;
            z-index: 1000;
            top: 42px;
            left: 10px;
            pointer-events: none;
            border: 1px solid #1e2638;
            border-radius: 3px;
            background: rgba(10, 14, 22, 0.94);
            color: #c9d1d9;
            font-family: 'Consolas', monospace;
            box-shadow: 0 4px 12px rgba(0,0,0,0.6);
        }}
    </style>
</head>
<body>
    <div id="legend">
        <span class="symbol-badge">XAU/USD M30</span>
        <span id="legend-ohlc">Move crosshair over candle for tick telemetry</span>
    </div>
    <div id="tooltip"></div>
    <div id="chart"></div>

    <script>
        const chartElement = document.getElementById('chart');
        const tooltip = document.getElementById('tooltip');
        const legendOhlc = document.getElementById('legend-ohlc');

        const chart = LightweightCharts.createChart(chartElement, {{
            width: chartElement.clientWidth,
            height: chartElement.clientHeight,
            layout: {{
                background: {{ type: 'solid', color: '#080b11' }},
                textColor: '#78909c',
                fontSize: 11,
                fontFamily: 'Consolas, monospace',
            }},
            grid: {{
                vertLines: {{ color: '#101520' }},
                horzLines: {{ color: '#101520' }},
            }},
            crosshair: {{
                mode: LightweightCharts.CrosshairMode.Normal,
                vertLine: {{
                    color: '#303f5a',
                    width: 1,
                    style: LightweightCharts.LineStyle.Dashed,
                }},
                horzLine: {{
                    color: '#303f5a',
                    width: 1,
                    style: LightweightCharts.LineStyle.Dashed,
                }},
            }},
            rightPriceScale: {{
                borderColor: '#182130',
                scaleMargins: {{
                    top: 0.12,
                    bottom: 0.15,
                }},
            }},
            timeScale: {{
                borderColor: '#182130',
                timeVisible: true,
                secondsVisible: false,
            }},
        }});

        // 1. Separate Volume Price Scale (bottom 15% strictly, never affects price scale)
        const volumeSeries = chart.addHistogramSeries({{
            priceFormat: {{
                type: 'volume',
            }},
            priceScaleId: 'vol_scale',
            visible: {show_volume_str},
        }});
        chart.priceScale('vol_scale').applyOptions({{
            scaleMargins: {{
                top: 0.85,
                bottom: 0,
            }},
        }});
        const volumeData = {volume_json};
        if (volumeData && volumeData.length > 0) {{
            volumeSeries.setData(volumeData);
        }}

        // 2. Candlestick Series
        const candleSeries = chart.addCandlestickSeries({{
            upColor: '#00e676',
            downColor: '#ff5252',
            borderVisible: false,
            wickUpColor: '#00e676',
            wickDownColor: '#ff5252',
        }});
        const candleData = {candles_json};
        if (candleData && candleData.length > 0) {{
            candleSeries.setData(candleData);
        }}

        // 3. EMA 50 (Trend Momentum)
        const ema50Series = chart.addLineSeries({{
            color: '#00b0ff',
            lineWidth: 1.5,
            title: 'EMA 50',
            crosshairMarkerVisible: false,
            visible: {show_ema50_str},
        }});
        const ema50Data = {ema50_json};
        if (ema50Data && ema50Data.length > 0) {{
            ema50Series.setData(ema50Data);
        }}

        // 4. EMA 200 (Macro Baseline)
        const ema200Series = chart.addLineSeries({{
            color: '#ffb300',
            lineWidth: 1.5,
            title: 'EMA 200',
            crosshairMarkerVisible: false,
            visible: {show_ema200_str},
        }});
        const ema200Data = {ema200_json};
        if (ema200Data && ema200Data.length > 0) {{
            ema200Series.setData(ema200Data);
        }}

        // 5. Clean Markers (Entry Arrow & Exit Dot)
        const markers = {markers_json};
        if (markers && markers.length > 0) {{
            candleSeries.setMarkers(markers);
        }}

        // 6. SL / TP / BE / Entry Price Lines
        const priceLinesData = {lines_json};
        if (priceLinesData && priceLinesData.length > 0) {{
            priceLinesData.forEach(line => {{
                let style = LightweightCharts.LineStyle.Solid;
                if (line.style === 'dashed') style = LightweightCharts.LineStyle.Dashed;
                if (line.style === 'dotted') style = LightweightCharts.LineStyle.Dotted;

                candleSeries.createPriceLine({{
                    price: line.price,
                    color: line.color,
                    lineWidth: line.lineWidth || 1,
                    lineStyle: style,
                    axisLabelVisible: true,
                    title: line.title,
                }});
            }});
        }}

        // 7. Interactive Crosshair Hover
        chart.subscribeCrosshairMove(param => {{
            if (!param.point || !param.time) {{
                tooltip.style.display = 'none';
                return;
            }}
            const price = param.seriesPrices.get(candleSeries);
            if (price) {{
                const diff = price.close - price.open;
                const diffPct = (diff / price.open) * 100;
                const sign = diff >= 0 ? '+' : '';
                const colorCls = diff >= 0 ? 'bull-text' : 'bear-text';

                legendOhlc.innerHTML = `O: <span class="ohlc-val">$${{price.open.toFixed(2)}}</span> ` +
                    `H: <span class="ohlc-val">$${{price.high.toFixed(2)}}</span> ` +
                    `L: <span class="ohlc-val">$${{price.low.toFixed(2)}}</span> ` +
                    `C: <span class="ohlc-val">$${{price.close.toFixed(2)}}</span> ` +
                    `Chg: <span class="${{colorCls}}">${{sign}}$${{diff.toFixed(2)}} (${{sign}}${{diffPct.toFixed(2)}}%)</span>`;

                tooltip.style.display = 'block';
                tooltip.innerHTML = `
                    <div style="color: #ffd700; font-weight: bold; margin-bottom: 3px;">XAU/USD M30</div>
                    <div>O: $${{price.open.toFixed(2)}} | H: $${{price.high.toFixed(2)}}</div>
                    <div>L: $${{price.low.toFixed(2)}} | C: $${{price.close.toFixed(2)}}</div>
                    <div>Change: <span class="${{colorCls}}">${{sign}}$${{diff.toFixed(2)}} (${{sign}}${{diffPct.toFixed(2)}}%)</span></div>
                `;
            }}
        }});

        window.addEventListener('resize', () => {{
            chart.applyOptions({{
                width: chartElement.clientWidth,
                height: chartElement.clientHeight,
            }});
        }});

        // 8. Robust Bar-Index Based Centering & Auto-Zoom
        function focusOnTarget(ts) {{
            if (!candleData || candleData.length === 0) return;
            if (!ts || ts <= 0) {{
                chart.timeScale().fitContent();
                return;
            }}
            let targetIdx = -1;
            for (let i = 0; i < candleData.length; i++) {{
                if (candleData[i].time >= ts) {{
                    targetIdx = i;
                    break;
                }}
            }}
            if (targetIdx === -1) targetIdx = candleData.length - 1;

            // Show exactly 22 bars before and 34 bars after (total ~56 bars / 28h window)
            const fromIdx = Math.max(0, targetIdx - 22);
            const toIdx = Math.min(candleData.length - 1, targetIdx + 34);

            const fromTime = candleData[fromIdx].time;
            const toTime = candleData[toIdx].time;

            chart.timeScale().setVisibleRange({{
                from: fromTime,
                to: toTime
            }});
        }}

        // Execute focus after chart DOM layout cycle
        setTimeout(() => {{
            const targetFocus = {focus_ts};
            if (targetFocus && targetFocus > 0) {{
                focusOnTarget(targetFocus);
            }} else {{
                chart.timeScale().fitContent();
            }}
        }}, 35);
    </script>
</body>
</html>
"""
    return html
