"""
FRAME Workstation: Background Computation Worker
Runs backtests in a separate QThread so the GUI remains 60fps responsive.
Supports flexible date ranges (Single Month, Multi-Month, Custom Range, Presets),
custom initial capital, and multi-mode position sizing (Flat 0.01 vs Dynamic Compounding).
"""

import sys, pathlib, json
import numpy as np
import pandas as pd
from typing import Dict, Any

try:
    from PySide6.QtCore import QThread, Signal
except ImportError:
    try:
        from PyQt6.QtCore import QThread, pyqtSignal as Signal
    except ImportError:
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
        class QThread:
            def __init__(self, parent=None): pass
            def start(self): self.run()
            def run(self): pass

project_root = pathlib.Path(r'c:\Ngoding\xau_deep_sniper')
local_root = pathlib.Path(r'c:\Ngoding\xau_deep_sniper')

from src.frame.constants import (
    INITIAL_EQUITY, FIXED_LOT, SPREAD_PIPS, SLIPPAGE_PIPS, COMMISSION_PER_LOT, CONTRACT_SIZE,
    TOTAL_FRICTION_USD, SL_ATR_MULT, TP_MAX_R, BE_TRIGGER_R, BE_BUFFER_PRICE, RATCHET_12_R,
    TRAIL_TRIGGER_R, TRAIL_DIST_R, STALE_DECAY_BARS, STALE_DECAY_R, TIME_BARRIER_BARS,
    TAU_BASE, UNCERTAINTY_MARGIN
)

class BacktestWorker(QThread):
    progress = Signal(int, str)
    log_message = Signal(str)
    finished_backtest = Signal(dict)
    error_occurred = Signal(str)

    def __init__(
        self,
        mode: str = "2026",
        start_date: str = "",
        end_date: str = "",
        capital: float = 500.0,
        lot: float = 0.01,
        sizing_mode: str = "flat",  # "flat", "dynamic", "dual"
        max_lot: float = 2.0,
    ):
        super().__init__()
        self.mode = mode
        self.start_date = start_date
        self.end_date = end_date
        self.capital = float(capital)
        self.lot = float(lot)
        self.sizing_mode = sizing_mode
        self.max_lot = float(max_lot)
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            date_info = f"{self.start_date} to {self.end_date}" if (self.start_date and self.end_date) else self.mode
            self.log_message.emit(
                f"[ENGINE] Starting FRAME Backtest Worker | Scope: {date_info} | "
                f"Capital: ${self.capital:,.2f} | Sizing: {self.sizing_mode.upper()} (Cap: {self.max_lot:.2f}L)"
            )
            self.progress.emit(10, "Loading 15-channel dataset...")

            df_path = project_root / "data" / "processed" / "xauusd_m30_labeled_15ch.parquet"
            preds_path = project_root / "checkpoints" / "predictions_15ch.npy"

            if not df_path.exists():
                raise FileNotFoundError(f"Missing dataset at {df_path}")
            if not preds_path.exists():
                raise FileNotFoundError(f"Missing predictions at {preds_path}")

            df = pd.read_parquet(df_path)
            df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc'], utc=True)
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean().round(2)
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean().round(2)
            preds = np.load(preds_path)

            self.progress.emit(30, "Computing causal ATR(14)...")
            high, low, close = df["high"].values, df["low"].values, df["close"].values
            tr = np.zeros(len(df))
            tr[0] = high[0] - low[0]
            for i in range(1, len(df)):
                tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
            period = 14
            atr = np.zeros(len(df))
            atr[:period] = np.mean(tr[:period])
            multiplier = 2.0 / (period + 1)
            for i in range(period, len(df)):
                atr[i] = tr[i] * multiplier + atr[i - 1] * (1 - multiplier)

            opens = df['open'].values
            highs = df['high'].values
            lows = df['low'].values
            closes = df['close'].values
            ts_arr = df['timestamp_utc'].values.astype('datetime64[s]')
            dt_series = df['timestamp_utc'].dt
            dows = dt_series.dayofweek.values
            hours = dt_series.hour.values
            minutes = dt_series.minute.values
            day_ints = dt_series.strftime('%Y%m%d').astype(int).values

            # ---------------------------------------------------------
            # Flexible Date Range Resolution
            # ---------------------------------------------------------
            if self.start_date and self.end_date:
                import calendar
                s_str = self.start_date if len(self.start_date) == 10 else f"{self.start_date}-01"
                if len(self.end_date) == 7:
                    y, m = map(int, self.end_date.split('-'))
                    last_d = calendar.monthrange(y, m)[1]
                    e_str = f"{self.end_date}-{last_d:02d}"
                else:
                    e_str = self.end_date
                st_dt = np.datetime64(f"{s_str}T00:00:00")
                en_dt = np.datetime64(f"{e_str}T23:59:59")
            elif "2026" in self.mode and "Multi" not in self.mode:
                st_dt = np.datetime64('2026-01-01T00:00:00')
                en_dt = np.datetime64('2026-08-31T23:59:59')
            elif "2025" in self.mode:
                st_dt = np.datetime64('2025-01-01T00:00:00')
                en_dt = np.datetime64('2025-12-31T23:59:59')
            elif "2024" in self.mode:
                st_dt = np.datetime64('2024-01-01T00:00:00')
                en_dt = np.datetime64('2024-12-31T23:59:59')
            elif "2023" in self.mode:
                st_dt = np.datetime64('2023-01-01T00:00:00')
                en_dt = np.datetime64('2023-12-31T23:59:59')
            elif "2022" in self.mode:
                st_dt = np.datetime64('2022-01-01T00:00:00')
                en_dt = np.datetime64('2022-12-31T23:59:59')
            elif "Multi-Year" in self.mode:
                st_dt = np.datetime64('2021-10-01T00:00:00')
                en_dt = np.datetime64('2026-08-31T23:59:59')
            else:
                st_dt = np.datetime64('2026-01-01T00:00:00')
                en_dt = np.datetime64('2026-08-31T23:59:59')

            mask = (ts_arr >= st_dt) & (ts_arr <= en_dt)
            indices = np.where(mask)[0]
            if len(indices) == 0:
                raise ValueError(f"No candlestick bars found within date range {st_dt} to {en_dt}")

            unique_days = np.unique(day_ints[indices])
            day_to_indices = {}
            for idx in indices:
                d = day_ints[idx]
                if d not in day_to_indices:
                    day_to_indices[d] = []
                day_to_indices[d].append(idx)

            session_defs = [
                (1*60, 4*60, "Asia Early (01:00-04:00)"),
                (4*60 + 30, 7*60, "Asia Late (04:30-07:00)"),
                (8*60 + 30, 12*60 + 30, "London Core (08:30-12:30)"),
                (13*60, 17*60, "NY Open (13:00-17:00)"),
                (17*60 + 30, 21*60, "NY Core (17:30-21:00)")
            ]

            seq_offset = 63

            # Dual-Mode Equities
            is_dual = (self.sizing_mode == "dual")
            is_dynamic = (self.sizing_mode in ["dynamic", "dual"])

            eq_flat = self.capital
            eq_dyn = self.capital
            curve_flat = [eq_flat]
            curve_dyn = [eq_dyn]
            equity_ts = [ts_arr[indices[0]]]
            trades = []

            self.progress.emit(50, "Executing OMS Simulation...")
            total_days = len(unique_days)

            for day_idx_num, d_int in enumerate(unique_days):
                if self.is_cancelled:
                    self.log_message.emit("[ENGINE] Run cancelled by user.")
                    return

                if day_idx_num % 15 == 0:
                    pct = int(50 + (day_idx_num / total_days) * 42)
                    self.progress.emit(pct, f"Simulating day {day_idx_num+1}/{total_days}...")

                day_idxs = day_to_indices[d_int]
                dow = dows[day_idxs[0]]
                if dow in [5, 6]:
                    continue

                for w_st, w_en, s_name in session_defs:
                    best_idx = None
                    best_conf = -1.0
                    best_act = None

                    for b_idx in day_idxs:
                        h = hours[b_idx]
                        m = minutes[b_idx]
                        if h == 7 or (h == 8 and m < 30):
                            continue
                        if dow == 4 and h >= 18:
                            continue

                        t_val = h * 60 + m
                        if w_st <= t_val <= w_en:
                            p_idx = b_idx - seq_offset
                            if 0 <= p_idx < len(preds):
                                probs = preds[p_idx]
                                p_hold = float(probs[0])
                                t_probs = probs[1:]
                                max_i = int(np.argmax(t_probs))
                                conf = float(t_probs[max_i])
                                margin = conf - p_hold

                                if conf > best_conf and conf >= TAU_BASE and margin >= UNCERTAINTY_MARGIN:
                                    best_conf = conf
                                    best_idx = b_idx
                                    best_act = max_i + 1

                    if best_idx is not None:
                        d = "BUY" if best_act in [1, 2] else "SELL"
                        atr_val = float(atr[best_idx]) if best_idx < len(atr) else 5.0
                        sl_dist = round(atr_val * SL_ATR_MULT, 2)
                        b_close = closes[best_idx]
                        ts = ts_arr[best_idx]

                        ep = round(b_close + (SLIPPAGE_PIPS * 0.10), 2) if d == "BUY" else round(b_close - (SLIPPAGE_PIPS * 0.10), 2)
                        sl_p = round(ep - sl_dist, 2) if d == "BUY" else round(ep + sl_dist, 2)
                        tp_max_p = round(ep + (TP_MAX_R * sl_dist), 2) if d == "BUY" else round(ep - (TP_MAX_R * sl_dist), 2)
                        be_trigger_p = round(ep + (BE_TRIGGER_R * sl_dist), 2) if d == "BUY" else round(ep - (BE_TRIGGER_R * sl_dist), 2)

                        cur_sl = sl_p
                        be_activated = False
                        exit_reason = None
                        exit_price = None
                        exit_ts = ts
                        bars_held = 1

                        for f_idx in range(best_idx + 1, min(best_idx + 16, len(df))):
                            f_high = highs[f_idx]
                            f_low = lows[f_idx]
                            f_close = closes[f_idx]
                            f_dow = dows[f_idx]
                            f_hour = hours[f_idx]
                            f_ts = ts_arr[f_idx]
                            bars_held = f_idx - best_idx
                            exit_ts = f_ts

                            is_fri = (f_dow == 4 and f_hour >= 20) or f_dow in [5, 6]
                            is_tb = (f_idx - best_idx >= TIME_BARRIER_BARS)

                            if is_fri or is_tb:
                                exit_price = f_close
                                exit_reason = "Friday Closeout" if is_fri else f"Time Barrier ({TIME_BARRIER_BARS//2}h)"
                                break

                            if STALE_DECAY_BARS > 0 and bars_held >= STALE_DECAY_BARS and not be_activated:
                                decay_sl = round(ep - (STALE_DECAY_R * sl_dist), 2) if d == "BUY" else round(ep + (STALE_DECAY_R * sl_dist), 2)
                                if d == "BUY":
                                    cur_sl = max(cur_sl, decay_sl)
                                else:
                                    cur_sl = min(cur_sl, decay_sl)

                            if d == "BUY":
                                if f_low <= cur_sl:
                                    exit_price = cur_sl
                                    exit_reason = "Protected Stop" if be_activated else "Stop Loss"
                                    break
                                elif f_high >= tp_max_p:
                                    exit_price = tp_max_p
                                    exit_reason = f"Max TP (+{TP_MAX_R}R)"
                                    break
                                else:
                                    if not be_activated and f_high >= be_trigger_p:
                                        be_activated = True
                                        cur_sl = max(cur_sl, round(ep + BE_BUFFER_PRICE, 2))
                                    r_gain = (f_high - ep) / sl_dist
                                    if RATCHET_12_R > 0 and r_gain >= 1.2:
                                        cur_sl = max(cur_sl, round(ep + (RATCHET_12_R * sl_dist), 2))
                                    if r_gain >= TRAIL_TRIGGER_R:
                                        cur_sl = max(cur_sl, round(f_high - (TRAIL_DIST_R * sl_dist), 2))
                            else: # SELL
                                if f_high >= cur_sl:
                                    exit_price = cur_sl
                                    exit_reason = "Protected Stop" if be_activated else "Stop Loss"
                                    break
                                elif f_low <= tp_max_p:
                                    exit_price = tp_max_p
                                    exit_reason = f"Max TP (+{TP_MAX_R}R)"
                                    break
                                else:
                                    if not be_activated and f_low <= be_trigger_p:
                                        be_activated = True
                                        cur_sl = min(cur_sl, round(ep - BE_BUFFER_PRICE, 2))
                                    r_gain = (ep - f_low) / sl_dist
                                    if RATCHET_12_R > 0 and r_gain >= 1.2:
                                        cur_sl = min(cur_sl, round(ep - (RATCHET_12_R * sl_dist), 2))
                                    if r_gain >= TRAIL_TRIGGER_R:
                                        cur_sl = min(cur_sl, round(f_low + (TRAIL_DIST_R * sl_dist), 2))

                        if exit_price is None:
                            exit_price = closes[min(best_idx + 15, len(df)-1)]
                            exit_reason = "Time Barrier (6h)"

                        price_diff = (exit_price - ep) if d == "BUY" else (ep - exit_price)

                        # -------------------------------------------------
                        # 1. Flat 0.01 Calculation
                        # -------------------------------------------------
                        lot_flat = 0.01
                        fric_flat = round(
                            (SPREAD_PIPS * 0.10 * lot_flat * CONTRACT_SIZE) +
                            (SLIPPAGE_PIPS * 0.10 * lot_flat * CONTRACT_SIZE * 2) +
                            (COMMISSION_PER_LOT * lot_flat), 3
                        )
                        pnl_flat = round((price_diff * lot_flat * CONTRACT_SIZE) - fric_flat, 2)
                        eq_flat += pnl_flat
                        curve_flat.append(round(eq_flat, 2))

                        # -------------------------------------------------
                        # 2. Dynamic Compounding (Scale with Equity)
                        # -------------------------------------------------
                        if is_dynamic:
                            raw_lot = (eq_dyn / self.capital) * 0.01
                            lot_dyn = round(max(0.01, min(self.max_lot, raw_lot)), 2)
                            fric_dyn = round(
                                (SPREAD_PIPS * 0.10 * lot_dyn * CONTRACT_SIZE) +
                                (SLIPPAGE_PIPS * 0.10 * lot_dyn * CONTRACT_SIZE * 2) +
                                (COMMISSION_PER_LOT * lot_dyn), 3
                            )
                            pnl_dyn = round((price_diff * lot_dyn * CONTRACT_SIZE) - fric_dyn, 2)
                            eq_dyn += pnl_dyn
                            curve_dyn.append(round(eq_dyn, 2))
                        else:
                            lot_dyn = lot_flat
                            pnl_dyn = pnl_flat
                            eq_dyn = eq_flat

                        # Select primary values
                        active_lot = lot_dyn if self.sizing_mode in ["dynamic", "dual"] else lot_flat
                        active_pnl = pnl_dyn if self.sizing_mode in ["dynamic", "dual"] else pnl_flat
                        active_eq = eq_dyn if self.sizing_mode in ["dynamic", "dual"] else eq_flat

                        trades.append({
                            'time': str(ts),
                            'month': str(ts)[:7],
                            'dir': d,
                            'entry': ep,
                            'exit': exit_price,
                            'exit_time': str(exit_ts),
                            'bars_held': int(bars_held),
                            'conf': float(round(float(best_conf) * 100, 1)),
                            'sl_dist': float(sl_dist),
                            'lot': float(active_lot),
                            'pnl': float(active_pnl),
                            'equity': float(round(active_eq, 2)),
                            'win': 1 if active_pnl > 0 else 0,
                            'session': s_name,
                            'exit_reason': exit_reason or 'Time Barrier',
                            # Extras for dual inspection
                            'lot_flat': float(lot_flat),
                            'pnl_flat': float(pnl_flat),
                            'equity_flat': float(round(eq_flat, 2)),
                            'lot_dyn': float(lot_dyn),
                            'pnl_dyn': float(pnl_dyn),
                            'equity_dyn': float(round(eq_dyn, 2)),
                        })
                        equity_ts.append(ts)

            # ---------------------------------------------------------
            # Compute Performance Metrics
            # ---------------------------------------------------------
            self.progress.emit(95, "Compiling metrics & monthly breakdown...")
            n_trades = len(trades)
            if n_trades == 0:
                raise ValueError("No trades executed within the selected period.")

            primary_curve = curve_dyn if self.sizing_mode in ["dynamic", "dual"] else curve_flat
            wins = [t for t in trades if t['win'] == 1]
            losses = [t for t in trades if t['win'] == 0]
            wr = (len(wins) / n_trades * 100) if n_trades > 0 else 0.0

            net_pnl = primary_curve[-1] - self.capital
            ret_pct = (net_pnl / self.capital) * 100

            tot_profit = sum(t['pnl'] for t in wins)
            tot_loss = abs(sum(t['pnl'] for t in losses))
            pf = tot_profit / tot_loss if tot_loss > 0 else 999.0

            peaks = np.maximum.accumulate(primary_curve)
            dds = (peaks - primary_curve) / peaks * 100
            max_dd = float(np.max(dds))
            min_eq = float(np.min(primary_curve))

            # Flat stats
            peaks_flat = np.maximum.accumulate(curve_flat)
            dds_flat = (peaks_flat - curve_flat) / peaks_flat * 100
            max_dd_flat = float(np.max(dds_flat))

            # Dyn stats
            peaks_dyn = np.maximum.accumulate(curve_dyn)
            dds_dyn = (peaks_dyn - curve_dyn) / peaks_dyn * 100
            max_dd_dyn = float(np.max(dds_dyn))

            peak_lot = float(max(t['lot'] for t in trades))

            # Monthly breakdown based on primary PnL
            tdf = pd.DataFrame(trades)
            monthly = []
            for m, grp in tdf.groupby('month'):
                m_w = len(grp[grp['win'] == 1])
                m_pnl = grp['pnl'].sum()
                m_wr = (m_w / len(grp)) * 100
                monthly.append({
                    'month': m,
                    'trades': int(len(grp)),
                    'wins': int(m_w),
                    'losses': int(len(grp) - m_w),
                    'win_rate': round(float(m_wr), 1),
                    'pnl': round(float(m_pnl), 2),
                    'balance': round(float(grp.iloc[-1]['equity']), 2)
                })

            result = {
                'mode': self.mode,
                'sizing_mode': self.sizing_mode,
                'initial_capital': self.capital,
                'lot_size': self.lot,
                'peak_lot': peak_lot,
                'max_lot_cap': self.max_lot,
                'final_equity': round(primary_curve[-1], 2),
                'net_pnl': round(net_pnl, 2),
                'return_pct': round(ret_pct, 2),
                'total_trades': n_trades,
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': round(wr, 2),
                'profit_factor': round(pf, 2),
                'max_drawdown': round(max_dd, 2),
                'min_equity': round(min_eq, 2),
                'equity_curve': primary_curve,
                'equity_dates': [str(t) for t in equity_ts],
                'trades': trades,
                'monthly': monthly,
                'df_candles': df[['timestamp_utc', 'open', 'high', 'low', 'close', 'volume', 'ema50', 'ema200']],
                # Dual Mode Comparison
                'dual_mode': is_dual,
                'equity_curve_flat': curve_flat if is_dual else None,
                'equity_curve_dyn': curve_dyn if is_dual else None,
                'final_equity_flat': round(curve_flat[-1], 2) if is_dual else None,
                'net_pnl_flat': round(curve_flat[-1] - self.capital, 2) if is_dual else None,
                'ret_pct_flat': round(((curve_flat[-1] - self.capital)/self.capital)*100, 1) if is_dual else None,
                'max_dd_flat': round(max_dd_flat, 2) if is_dual else None,
                'final_equity_dyn': round(curve_dyn[-1], 2) if is_dual else None,
                'net_pnl_dyn': round(curve_dyn[-1] - self.capital, 2) if is_dual else None,
                'ret_pct_dyn': round(((curve_dyn[-1] - self.capital)/self.capital)*100, 1) if is_dual else None,
                'max_dd_dyn': round(max_dd_dyn, 2) if is_dual else None,
            }

            self.log_message.emit(
                f"[SUCCESS] Audit Completed: {n_trades} trades | Sizing: {self.sizing_mode.upper()} | "
                f"Net: ${net_pnl:+,.2f} ({ret_pct:+,.1f}%) | WR: {wr:.1f}% | DD: {max_dd:.1f}% | Peak Lot: {peak_lot:.2f}L"
            )
            self.last_results = result
            self.progress.emit(100, "Done")
            self.finished_backtest.emit(result)

        except Exception as e:
            self.log_message.emit(f"[ERROR] Exception in BacktestWorker: {str(e)}")
            self.error_occurred.emit(str(e))
