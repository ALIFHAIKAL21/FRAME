# FLOWDEV FRAME - 24/7 Autonomous Cloud Live Trading Engine
# Serverless execution on Streamlit Community Cloud + Cron-Job.org.

import os, sys, time, json, math, pathlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np

_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.frame.constants import (
    INITIAL_EQUITY, FIXED_LOT, CONTRACT_SIZE, SPREAD_PIPS, SLIPPAGE_PIPS,
    COMMISSION_PER_LOT, SL_ATR_MULT, TP_MAX_R, BE_TRIGGER_R, BE_BUFFER_PRICE,
    RATCHET_TRIGGER_R, RATCHET_12_R, TRAIL_TRIGGER_R, TRAIL_DIST_R,
    STALE_DECAY_BARS, TIME_BARRIER_BARS
)
from src.frame.live.db_audit import TradeAuditDB
from src.frame.live.paper_broker import LivePaperBroker
from src.frame.live.telegram_bot import LiveTelegramNotifier

STATE_FILE = _ROOT / 'data' / 'cloud_trader_state.json'

class CloudMarketFeed:
    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol.upper()
        self.last_bid = 4321.20
        self.last_ask = 4321.55
        self.last_fetch_time = 0

    def set_symbol(self, symbol: str):
        self.symbol = symbol.upper()

    def _get_ticker(self) -> str:
        return "BTC-USD" if "BTC" in self.symbol else "GC=F"

    def fetch_live_price(self) -> Dict[str, Any]:
        try:
            import httpx
            headers = {'User-Agent': 'Mozilla/5.0'}
            ticker = self._get_ticker()
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d'
            with httpx.Client(timeout=4.0) as client:
                r = client.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    res = data['chart']['result'][0]
                    price = float(res['meta']['regularMarketPrice'])
                    if price > 1000.0:
                        self.last_bid = round(price, 2)
                        self.last_ask = round(price + 0.35, 2)
                        self.last_fetch_time = time.time()
                        return {'bid': self.last_bid, 'ask': self.last_ask, 'source': 'YAHOO_LIVE'}
        except Exception:
            pass
        return {'bid': self.last_bid, 'ask': self.last_ask, 'source': 'EMULATED_CACHE'}

    def fetch_m30_candles(self, limit: int = 64) -> List[Dict[str, Any]]:
        try:
            import httpx
            headers = {'User-Agent': 'Mozilla/5.0'}
            ticker = self._get_ticker()
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=30m&range=5d'
            with httpx.Client(timeout=5.0) as client:
                r = client.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    res = data['chart']['result'][0]
                    ts = res['timestamp']
                    quotes = res['indicators']['quote'][0]
                    candles = []
                    for i in range(len(ts)):
                        c = quotes['close'][i]
                        o = quotes['open'][i]
                        h = quotes['high'][i]
                        l = quotes['low'][i]
                        v = quotes['volume'][i] or 0
                        if None not in (c, o, h, l):
                            candles.append({
                                'time': int(ts[i]),
                                'open': float(o),
                                'high': float(h),
                                'low': float(l),
                                'close': float(c),
                                'volume': float(v)
                            })
                    if len(candles) >= limit:
                        return candles[-limit:]
                    return candles
        except Exception:
            pass
        return []

class CloudLiveTraderEngine:
    def __init__(self):
        self.feed = CloudMarketFeed()
        self.db = TradeAuditDB(_ROOT / 'data' / 'flowdev_trade_audit.db')
        self.telegram = LiveTelegramNotifier()
        self.broker = LivePaperBroker(initial_capital=INITIAL_EQUITY, lot_mode='flat', max_lot=0.01)
        self.symbol = "XAUUSD"
        self.last_evaluated_candle_time = 0
        self.last_session_traded = ''
        self.is_armed = True
        self.load_state()

    def load_state(self):
        # 1. Primary: Load from Neon Cloud PostgreSQL
        db_state = self.db.get_operational_state("GLOBAL_STATE")
        if db_state and isinstance(db_state, dict):
            self.broker.cash = float(db_state.get('cash', INITIAL_EQUITY))
            self.broker.open_position = db_state.get('open_position')
            self.last_evaluated_candle_time = int(db_state.get('last_candle_time', 0))
            self.last_session_traded = str(db_state.get('last_session_traded', ''))
            self.is_armed = bool(db_state.get('is_armed', True))
            self.symbol = str(db_state.get('symbol', 'XAUUSD'))
            self.feed.set_symbol(self.symbol)
            return

        # 2. Fallback: Local STATE_FILE
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    self.broker.cash = float(state.get('cash', INITIAL_EQUITY))
                    self.broker.open_position = state.get('open_position')
                    self.last_evaluated_candle_time = int(state.get('last_candle_time', 0))
                    self.last_session_traded = str(state.get('last_session_traded', ''))
                    self.is_armed = bool(state.get('is_armed', True))
                    self.symbol = str(state.get('symbol', 'XAUUSD'))
                    self.feed.set_symbol(self.symbol)
            except Exception:
                pass

    def save_state(self):
        state = {
            'cash': self.broker.cash,
            'open_position': self.broker.open_position,
            'last_candle_time': self.last_evaluated_candle_time,
            'last_session_traded': self.last_session_traded,
            'is_armed': self.is_armed,
            'symbol': self.symbol,
            'updated_at_utc': datetime.now(timezone.utc).isoformat()
        }
        # 1. Primary: Save to Neon Cloud PostgreSQL (Realtime sync)
        self.db.save_operational_state(state, "GLOBAL_STATE")

        # 2. Secondary: Local disk backup
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception:
            pass

    def get_current_session(self, now_utc: datetime) -> str:
        if "BTC" in getattr(self, "symbol", "XAUUSD").upper():
            return "CRYPTO_24_7"
        h = now_utc.hour + now_utc.minute / 60.0
        if 7.0 <= h < 8.5: return 'BLACKOUT_PRE_LONDON'
        if 1.0 <= h < 4.0: return 'ASIA_EARLY'
        if 4.5 <= h < 7.0: return 'ASIA_LATE'
        if 8.5 <= h < 12.5: return 'LONDON_CORE'
        if 13.0 <= h < 17.0: return 'NY_OPEN'
        if 17.5 <= h < 21.0: return 'NY_CORE'
        return 'OFF_SESSION'

    def reset(self, new_capital: float = INITIAL_EQUITY):
        self.broker.reset(new_capital)
        self.last_evaluated_candle_time = 0
        self.last_session_traded = ''
        self.save_state()

    def update_config(self, lot_mode: str, max_lot: float, symbol: Optional[str] = None):
        self.broker.lot_mode = lot_mode
        self.broker.max_lot = max_lot
        if symbol:
            self.symbol = symbol.upper()
            self.feed.set_symbol(self.symbol)
        self.save_state()

    def step(self) -> Dict[str, Any]:
        if not self.is_armed and self.broker.open_position is None:
            return {'action': 'AGENT_DISARMED', 'message': 'Cloud trading engine is PAUSED/DISARMED by operator.'}

        now_utc = datetime.now(timezone.utc)
        events = []
        price_info = self.feed.fetch_live_price()
        bid = price_info['bid']
        ask = price_info['ask']
        session_name = self.get_current_session(now_utc)

        # 1. EVALUATE 4-STAGE KINETIC OMS ON OPEN POSITION
        pos = self.broker.open_position
        if pos is not None:
            direction = pos['direction']
            ep = pos['entry_price']
            cur_price = bid if direction == 'BUY' else ask
            sl_dist = pos['sl_dist']
            current_r = ((cur_price - ep) / sl_dist) if direction == 'BUY' else ((ep - cur_price) / sl_dist)

            pos['peak_r'] = max(pos.get('peak_r', 0.0), current_r)
            peak_r = pos['peak_r']

            # Check Hard SL Touch
            sl_price = pos.get('current_sl', pos.get('initial_sl', pos.get('sl_price', 0.0)))
            hit_sl = (cur_price <= sl_price) if direction == 'BUY' else (cur_price >= sl_price)
            if hit_sl:
                trade = self.broker.close_order(sl_price, exit_reason='Stop Loss Hit')
                self.db.record_order_closed(trade)
                self.telegram.send_trade_alert('CLOSE', trade)
                events.append('SL HIT at ' + str(sl_price))
                self.save_state()
                return {'action': 'ORDER_CLOSED_SL', 'events': events, 'stats': self.broker.get_stats()}

            # Check Max TP (+2.7R)
            if current_r >= TP_MAX_R:
                trade = self.broker.close_order(cur_price, exit_reason='Max TP Hit (+2.7R)')
                self.db.record_order_closed(trade)
                self.telegram.send_trade_alert('CLOSE', trade)
                events.append('MAX TP HIT at ' + str(cur_price))
                self.save_state()
                return {'action': 'ORDER_CLOSED_TP', 'events': events, 'stats': self.broker.get_stats()}

            # Check Friday 20:00 UTC Close-out
            if now_utc.weekday() == 4 and now_utc.hour >= 20:
                trade = self.broker.close_order(cur_price, exit_reason='Friday 20:00 UTC Close-out')
                self.db.record_order_closed(trade)
                self.telegram.send_trade_alert('CLOSE', trade)
                events.append('FRIDAY FORCE CLOSEOUT EXECUTED')
                self.save_state()
                return {'action': 'ORDER_CLOSED_WEEKEND', 'events': events, 'stats': self.broker.get_stats()}

            # Check Hard Time Barrier (12 bars / 6 hours)
            open_ts = pos.get('open_timestamp', time.time())
            if (time.time() - open_ts) / 3600.0 >= 6.0:
                trade = self.broker.close_order(cur_price, exit_reason='Time Barrier (12 bars / 6h)')
                self.db.record_order_closed(trade)
                self.telegram.send_trade_alert('CLOSE', trade)
                events.append('TIME BARRIER EXPIRED')
                self.save_state()
                return {'action': 'ORDER_CLOSED_TIME', 'events': events, 'stats': self.broker.get_stats()}

            # Stage 3: Dynamic Trailing Stop (+1.5R+)
            if peak_r >= TRAIL_TRIGGER_R:
                trail_sl = (cur_price - (TRAIL_DIST_R * sl_dist)) if direction == 'BUY' else (cur_price + (TRAIL_DIST_R * sl_dist))
                cur_sl = pos.get('current_sl', pos.get('initial_sl', pos.get('sl_price', 0.0)))
                if (direction == 'BUY' and trail_sl > cur_sl) or (direction == 'SELL' and trail_sl < cur_sl):
                    pos['current_sl'] = round(trail_sl, 2)
                    events.append('Dynamic Trail: SL -> ' + str(pos['current_sl']))

            # Stage 2: Smart Ratchet (+1.2R -> Lock +0.5R)
            elif current_r >= RATCHET_TRIGGER_R and not pos.get('ratchet_active', False):
                ratchet_sl = (ep + (RATCHET_12_R * sl_dist)) if direction == 'BUY' else (ep - (RATCHET_12_R * sl_dist))
                pos['current_sl'] = round(ratchet_sl, 2)
                pos['ratchet_active'] = True
                events.append('Smart Ratchet: Locked SL at ' + str(pos['current_sl']) + ' (+0.5R)')

            # Stage 1: Micro-Breakeven
            elif current_r >= BE_TRIGGER_R and not pos.get('be_active', False):
                be_sl = (ep + BE_BUFFER_PRICE) if direction == 'BUY' else (ep - BE_BUFFER_PRICE)
                pos['current_sl'] = round(be_sl, 2)
                pos['be_active'] = True
                events.append('Micro-Breakeven: SL moved to ' + str(pos['current_sl']))

            self.save_state()
            return {'action': 'OMS_MONITORED', 'events': events, 'position': pos, 'current_r': round(current_r, 2)}

        # 2. CHECK NEW ENTRY OPPORTUNITY (IF NO OPEN POSITION)
        is_btc = "BTC" in self.symbol.upper()
        if not is_btc:
            if now_utc.weekday() == 4 and now_utc.hour >= 18:
                return {'action': 'WEEKEND_SHIELD_ACTIVE', 'message': 'No entries after Fri 18:00 UTC'}
            if now_utc.weekday() in (5, 6):
                return {'action': 'WEEKEND_MARKET_CLOSED', 'message': 'Forex markets closed on weekend'}

        if not is_btc:
            if session_name in ('OFF_SESSION', 'BLACKOUT_PRE_LONDON'):
                return {'action': 'STANDBY_SESSION', 'session': session_name}

            if self.last_session_traded == session_name:
                return {'action': 'SESSION_QUOTA_FILLED', 'session': session_name, 'message': 'Max 1 trade per session'}

        candles = self.feed.fetch_m30_candles(limit=64)
        if len(candles) >= 14:
            latest_bar = candles[-1]
            bar_time = latest_bar['time']
            if bar_time != self.last_evaluated_candle_time:
                self.last_evaluated_candle_time = bar_time

                closes = np.array([c['close'] for c in candles])
                highs = np.array([c['high'] for c in candles])
                lows = np.array([c['low'] for c in candles])

                tr1 = highs[1:] - lows[1:]
                tr2 = np.abs(highs[1:] - closes[:-1])
                tr3 = np.abs(lows[1:] - closes[:-1])
                tr = np.maximum(tr1, np.maximum(tr2, tr3))
                if is_btc:
                    atr14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else 800.0
                    sl_dist = round(max(400.0, min(3500.0, SL_ATR_MULT * atr14)), 2)
                else:
                    atr14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else 10.0
                    sl_dist = round(max(8.0, min(25.0, SL_ATR_MULT * atr14)), 2)

                fast_ma = np.mean(closes[-8:])
                slow_ma = np.mean(closes[-24:])
                diff = (fast_ma - slow_ma) / atr14

                signal = None
                if diff > 0.45: signal = 'BUY'
                elif diff < -0.45: signal = 'SELL'

                if signal:
                    order = self.broker.open_order(
                        direction=signal,
                        current_bid=bid,
                        current_ask=ask,
                        sl_dist=sl_dist,
                        timestamp=now_utc,
                        reason='Autonomous Cloud Signal (' + session_name + ')'
                    )
                    self.last_session_traded = session_name
                    self.db.record_order_opened(order)
                    self.telegram.send_trade_alert('OPEN', order)
                    events.append('OPENED ' + signal + ' 0.01 Lot at ' + str(order['entry_price']) + ' | SL: ' + str(order.get('current_sl', order.get('initial_sl', 0.0))))
                    self.save_state()
                    return {'action': 'ORDER_OPENED', 'order': order, 'events': events}

        self.save_state()
        return {'action': 'STANDBY_SCANNING', 'session': session_name, 'bid': bid, 'ask': ask}
