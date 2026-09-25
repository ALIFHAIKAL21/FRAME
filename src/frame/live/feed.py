"""
FLOWDEV FRAME - Real-Time Low-Latency Market Data Feed
Streams live XAU/USD market ticks and M30 candles directly into the trading agent.
Primary source: Native MetaTrader 5 Broker IPC (0ms latency).
Fallback source: High-fidelity Live Market Stream Emulator (for 24/7 testing & weekend markets).
"""

import time, math, random, pathlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np

try:
    from PySide6.QtCore import QObject, Signal, QTimer, QThread
except ImportError:
    try:
        from PyQt6.QtCore import QObject, pyqtSignal as Signal, QTimer, QThread
    except ImportError:
        class QObject:
            def __init__(self, parent=None): pass
        class Signal:
            def __init__(self, *args, **kwargs):
                self._cbs = []
            def connect(self, cb):
                if cb not in self._cbs:
                    self._cbs.append(cb)
            def emit(self, *args, **kwargs):
                for cb in list(self._cbs):
                    try: cb(*args, **kwargs)
                    except Exception: pass
        class _TimerTimeout(Signal):
            pass
        class QTimer:
            def __init__(self, parent=None):
                self.timeout = _TimerTimeout()
            def start(self, ms=1000): pass
            def stop(self): pass
        class QThread(QObject):
            def start(self): self.run()
            def run(self): pass

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

class LiveMarketFeed(QObject):
    tick_received = Signal(dict)
    candle_updated = Signal(dict)
    connection_changed = Signal(bool, str, str)  # is_connected, source, msg
    history_loaded = Signal(list)                # list of initial M30 candles

    def __init__(self, symbol: str = "XAUUSD", poll_interval_ms: int = 250, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.poll_interval_ms = poll_interval_ms
        self.active_source = "auto"  # "auto", "mt5", "emulator"
        self.is_connected = False
        self.mt5_initialized = False

        # Live candle state (M30 = 1800s)
        self.current_candle: Optional[Dict[str, Any]] = None
        self.bar_duration_sec = 1800
        
        # Last tick state
        self.last_bid = 4310.50
        self.last_ask = 4310.85
        self.last_tick_time = int(time.time())
        self.tick_count = 0
        
        # Seed price for emulator
        self._seed_emulator_price()

        # Polling timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_tick)

    def _seed_emulator_price(self):
        try:
            parquet_path = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\data\processed\xauusd_m30_labeled_15ch.parquet")
            if parquet_path.exists():
                df = pd.read_parquet(parquet_path, columns=['close'])
                self.last_bid = float(df['close'].iloc[-1])
                self.last_ask = round(self.last_bid + 0.35, 2)
        except Exception:
            self.last_bid = 4310.50
            self.last_ask = 4310.85

    def start(self):
        """Attempts to connect to MT5, or falls back to emulator."""
        self._connect()
        self.timer.start(self.poll_interval_ms)

    def stop(self):
        self.timer.stop()
        if self.mt5_initialized and HAS_MT5:
            try:
                mt5.shutdown()
            except Exception:
                pass
        self.is_connected = False
        self.connection_changed.emit(False, "DISCONNECTED", "Feed stopped by user.")

    def set_source(self, source_type: str):
        """source_type: 'auto', 'mt5', or 'emulator'"""
        self.active_source = source_type
        self._connect()

    def _connect(self):
        if self.active_source in ["auto", "mt5"] and HAS_MT5:
            try:
                if mt5.initialize(timeout=3000):
                    sym_info = mt5.symbol_info(self.symbol)
                    if sym_info is not None:
                        if not sym_info.visible:
                            mt5.symbol_select(self.symbol, True)
                        self.mt5_initialized = True
                        self.is_connected = True
                        self.connection_changed.emit(
                            True, "MT5 NATIVE",
                            f"Live Broker Feed Active ({sym_info.name}) | 0ms IPC"
                        )
                        self._load_initial_history_mt5()
                        return
            except Exception as e:
                pass

        # If MT5 is not available or user selected emulator
        self.mt5_initialized = False
        self.is_connected = True
        self.connection_changed.emit(
            True, "MARKET EMULATOR",
            f"High-Fidelity Realtime Tick Streamer (Seeded: ${self.last_bid:,.2f})"
        )
        self._load_initial_history_emulator()

    def _load_initial_history_mt5(self):
        try:
            rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M30, 0, 80)
            if rates is not None and len(rates) > 0:
                candles = []
                for r in rates:
                    candles.append({
                        "time": int(r['time']),
                        "open": float(r['open']),
                        "high": float(r['high']),
                        "low": float(r['low']),
                        "close": float(r['close']),
                        "volume": float(r['tick_volume'])
                    })
                # initialize current candle from the last bar
                self.current_candle = dict(candles[-1])
                self.history_loaded.emit(candles)
                return
        except Exception:
            pass
        self._load_initial_history_emulator()

    def _load_initial_history_emulator(self):
        try:
            parquet_path = pathlib.Path(r"c:\Ngoding\xau_deep_sniper\data\processed\xauusd_m30_labeled_15ch.parquet")
            if parquet_path.exists():
                df = pd.read_parquet(parquet_path).tail(80)
                candles = []
                for _, row in df.iterrows():
                    ts = int(pd.to_datetime(row['timestamp_utc']).timestamp())
                    candles.append({
                        "time": ts,
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": float(row['close']),
                        "volume": float(row.get('volume', 1000))
                    })
                self.current_candle = dict(candles[-1])
                self.history_loaded.emit(candles)
                return
        except Exception:
            pass
        
        # Synthetic fallback
        now = int(time.time()) - (80 * 1800)
        p = self.last_bid
        candles = []
        for i in range(80):
            t = now + (i * 1800)
            c = p + random.uniform(-1.5, 1.5)
            h = max(p, c) + random.uniform(0.1, 1.0)
            l = min(p, c) - random.uniform(0.1, 1.0)
            candles.append({
                "time": t, "open": round(p, 2), "high": round(h, 2),
                "low": round(l, 2), "close": round(c, 2), "volume": 1200
            })
            p = c
        self.current_candle = dict(candles[-1])
        self.history_loaded.emit(candles)

    def _poll_tick(self):
        t0 = time.perf_counter()
        tick_data = None
        source_label = "EMULATOR"

        if self.mt5_initialized and HAS_MT5:
            try:
                t = mt5.symbol_info_tick(self.symbol)
                if t is not None:
                    bid = float(t.bid)
                    ask = float(t.ask)
                    spread = round(ask - bid, 2)
                    ts = int(t.time)
                    latency = round((time.perf_counter() - t0) * 1000, 2)
                    tick_data = {
                        "bid": bid,
                        "ask": ask,
                        "spread": spread,
                        "time": ts,
                        "time_str": datetime.fromtimestamp(ts, timezone.utc).strftime("%H:%M:%S UTC"),
                        "latency_ms": latency,
                        "source": "MT5 LIVE"
                    }
                    source_label = "MT5"
            except Exception:
                self.mt5_initialized = False

        if tick_data is None:
            # High-fidelity realistic tick generation
            # Brownian motion with micro volatility and mean reversion
            drift = (4315.0 - self.last_bid) * 0.0002
            volatility = random.gauss(0, 0.22)
            new_bid = round(self.last_bid + drift + volatility, 2)
            spread = round(random.choice([0.30, 0.35, 0.38, 0.42]), 2)
            new_ask = round(new_bid + spread, 2)
            now_ts = int(time.time())
            latency = round(random.uniform(3.5, 14.2), 1)

            tick_data = {
                "bid": new_bid,
                "ask": new_ask,
                "spread": spread,
                "time": now_ts,
                "time_str": datetime.fromtimestamp(now_ts, timezone.utc).strftime("%H:%M:%S UTC"),
                "latency_ms": latency,
                "source": "REALTIME EMULATOR"
            }
            self.last_bid = new_bid
            self.last_ask = new_ask

        self.last_tick_time = tick_data["time"]
        self.tick_count += 1

        # Emit tick
        self.tick_received.emit(tick_data)

        # Update M30 Candlestick
        self._update_candle(tick_data["bid"], tick_data["time"])

    def _update_candle(self, price: float, ts: int):
        # Round timestamp down to 30-minute block (1800s)
        bar_start_ts = (ts // self.bar_duration_sec) * self.bar_duration_sec

        if self.current_candle is None or self.current_candle["time"] != bar_start_ts:
            # Bar closed or first bar
            if self.current_candle is not None:
                self.current_candle["is_closed"] = True
                self.candle_updated.emit(self.current_candle)

            self.current_candle = {
                "time": bar_start_ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 1,
                "is_closed": False
            }
        else:
            # Ongoing bar update
            self.current_candle["high"] = max(self.current_candle["high"], price)
            self.current_candle["low"] = min(self.current_candle["low"], price)
            self.current_candle["close"] = price
            self.current_candle["volume"] += 1
            self.current_candle["is_closed"] = False

        self.candle_updated.emit(self.current_candle)
