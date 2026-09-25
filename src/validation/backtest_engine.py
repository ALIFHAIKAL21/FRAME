"""
XAU_DEEP_SNIPER - Realistic Bar-by-Bar Event-Driven Backtest Engine (BAB 9.2 & Tahap 6)
========================================================================================
Simulasi event-driven M30 yang mengintegrasikan seluruh gerbang proteksi modal TAHAP 5
(StructuralRiskEngine) dengan biaya friksi realistis, Twin-Order Asymmetric Payoff,
London Open Sweep Quarantine, Structural Order Block Alignment, dan Trailing Stop.

Fitur:
- Bar-by-bar sequential processing (zero lookahead bias)
- Full risk gate integration: News Blackout, Friday Rule, Circuit Breaker,
  Concurrency, High-Conviction Gate (Tau=0.34), Max Daily Entries Cap (10)
- London Open Sweep Quarantine (07:00–08:30 UTC)
- HTF Structural Gate (Supply/Demand Order Blocks & MA Ribbon Slope)
- Asymmetric Twin-Order Partial Take Profit: 40% lot @ TP1 (+1.0R), 60% lot @ TP2 (+2.5R)
- Widened Trailing Breakeven (+1.0R trigger) & Dynamic Trailing Stop
- Realistic institutional friction: spread 0.75 pip + commission $3.50/lot + adverse slippage 0.3 pip (2-way)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
import math


@dataclass
class TradeRecord:
    """Record satu trade yang sudah ditutup."""
    trade_id: int
    direction: str           # "BUY" atau "SELL"
    entry_bar_idx: int
    exit_bar_idx: int
    entry_timestamp: pd.Timestamp
    exit_timestamp: pd.Timestamp
    entry_price: float
    exit_price: float
    sl_price: float
    tp_price: float
    lot_size: float
    r_target: float
    confidence: float
    pnl_gross: float         # Sebelum biaya
    friction_cost: float     # Total spread + commission + slippage
    pnl_net: float           # Setelah biaya
    r_multiple: float        # PnL / risk_amount (net-of-cost R)
    exit_reason: str         # "TP1_HIT", "TP2_HIT", "BE_HIT", "SL_HIT", "FRIDAY_CLOSE", "TIME_BARRIER"
    was_breakeven_moved: bool
    bars_held: int
    tp1_hit: bool = False
    tp2_hit: bool = False


@dataclass
class BacktestResult:
    """Hasil komprehensif dari backtest."""
    trades: List[TradeRecord]
    equity_curve: np.ndarray
    timestamps: List[pd.Timestamp]
    initial_equity: float
    final_equity: float

    # Summary metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    total_friction: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit_factor: float = 0.0
    avg_r_multiple: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    expectancy_r: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_usd: float = 0.0
    max_consecutive_losses: int = 0
    avg_bars_held: float = 0.0

    # Twin TP metrics
    tp1_hits: int = 0
    tp2_hits: int = 0

    # Non-HOLD precision metrics
    total_non_hold_signals: int = 0
    non_hold_precision: float = 0.0

    # Weekly drawdown tracking
    weekly_drawdowns: Dict[str, float] = field(default_factory=dict)
    circuit_breaker_trips: int = 0


class RealisticBacktestEngine:
    """
    Mesin backtest event-driven realistis tingkat institusional untuk XAU/USD M30.
    """

    def __init__(
        self,
        initial_equity: float = 10_000.0,
        risk_fraction: float = 0.01,
        confidence_tau: float = 0.34,
        sl_atr_multiplier: float = 1.5,
        spread_pip: float = 0.75,
        commission_per_lot: float = 3.50,
        slippage_pip: float = 0.3,
        time_barrier_bars: int = 16,
        contract_size: float = 100.0,
        use_partial_tp: bool = True,
        pos_a_pct: float = 0.40,
        pos_b_pct: float = 0.60,
        tp1_r_ratio: float = 1.0,
        tp2_r_ratio: float = 2.5,
        be_trigger_r: float = 1.0,
        trail_after_r: float = 1.5,
        trail_distance_r: float = 0.8,
        max_daily_entries: int = 10,
        quarantine_london_open: bool = True,
        use_structural_filter: bool = True,
    ):
        self.initial_equity = initial_equity
        self.risk_fraction = risk_fraction
        self.confidence_tau = confidence_tau
        self.sl_atr_multiplier = sl_atr_multiplier
        self.spread_pip = spread_pip
        self.commission_per_lot = commission_per_lot
        self.slippage_pip = slippage_pip
        self.time_barrier_bars = time_barrier_bars
        self.contract_size = contract_size
        self.use_partial_tp = use_partial_tp
        self.pos_a_pct = pos_a_pct
        self.pos_b_pct = pos_b_pct
        self.tp1_r_ratio = tp1_r_ratio
        self.tp2_r_ratio = tp2_r_ratio
        self.be_trigger_r = be_trigger_r
        self.trail_after_r = trail_after_r
        self.trail_distance_r = trail_distance_r
        self.max_daily_entries = max_daily_entries
        self.quarantine_london_open = quarantine_london_open
        self.use_structural_filter = use_structural_filter

        # Derived
        self.spread_price = spread_pip * 0.10
        self.slippage_price = slippage_pip * 0.10

    def _calculate_lot_size(
        self,
        equity: float,
        sl_distance: float,
    ) -> Tuple[float, float]:
        """Menghitung lot size dan risk amount."""
        if equity <= 0 or sl_distance <= 0:
            return 0.0, 0.0

        target_risk = equity * self.risk_fraction
        loss_per_lot = sl_distance * self.contract_size
        raw_lot = target_risk / loss_per_lot

        lot = math.floor(raw_lot / 0.01) * 0.01
        lot = max(0.02, min(lot, 50.0))

        actual_risk = lot * loss_per_lot
        return round(lot, 2), round(actual_risk, 2)

    def _friction_per_trade(self, lot_size: float) -> float:
        """Total biaya friksi untuk satu trade (spread + slippage + commission)."""
        spread_cost = self.spread_price * lot_size * self.contract_size
        slippage_cost = self.slippage_price * lot_size * self.contract_size * 2
        commission_cost = self.commission_per_lot * lot_size
        return round(spread_cost + slippage_cost + commission_cost, 2)

    def run(
        self,
        df: pd.DataFrame,
        predictions: np.ndarray,
        atr_values: np.ndarray,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> BacktestResult:
        """
        Menjalankan backtest bar-by-bar pada DataFrame test.
        """
        n_bars = len(df)
        seq_offset = 63

        equity = self.initial_equity
        equity_curve = [equity]
        timestamps_list = []
        trades: List[TradeRecord] = []
        trade_counter = 0

        open_position = None

        current_trade_date = None
        daily_entries_count = 0

        # Circuit breaker state
        weekly_starting_equity = equity
        all_time_peak = equity
        current_week_id = None
        is_weekly_tripped = False
        is_permanent_stopped = False
        circuit_breaker_trips = 0
        weekly_drawdowns: Dict[str, float] = {}

        start_ts = pd.Timestamp(start_date, tz='UTC') if start_date else None
        end_ts = pd.Timestamp(end_date, tz='UTC') if end_date else None

        for bar_idx in range(n_bars):
            row = df.iloc[bar_idx]
            ts = row["timestamp_utc"]
            bar_open = row["open"]
            bar_high = row["high"]
            bar_low = row["low"]
            bar_close = row["close"]
            is_blackout = bool(row.get("is_news_blackout", False))
            is_eligible = bool(row.get("entry_eligible", True))

            in_date_range = True
            if start_ts and ts < start_ts:
                in_date_range = False
            if end_ts and ts > end_ts:
                in_date_range = False

            # Daily entry cap counter reset
            bar_date = ts.date() if hasattr(ts, 'date') else pd.Timestamp(ts).date()
            if bar_date != current_trade_date:
                current_trade_date = bar_date
                daily_entries_count = 0

            # Circuit breaker update
            if hasattr(ts, 'isocalendar'):
                iso = ts.isocalendar()
                week_id = f"{iso[0]}-W{iso[1]:02d}"
            else:
                iso = pd.Timestamp(ts).isocalendar()
                week_id = f"{iso[0]}-W{iso[1]:02d}"

            if current_week_id is None:
                current_week_id = week_id
                weekly_starting_equity = equity
            elif week_id != current_week_id:
                wdd = (equity - weekly_starting_equity) / weekly_starting_equity if weekly_starting_equity > 0 else 0
                weekly_drawdowns[current_week_id] = round(wdd, 4)
                current_week_id = week_id
                weekly_starting_equity = equity
                if not is_permanent_stopped:
                    is_weekly_tripped = False

            if equity > all_time_peak:
                all_time_peak = equity

            if all_time_peak > 0:
                peak_dd = (equity - all_time_peak) / all_time_peak
                if peak_dd <= -0.50:
                    is_permanent_stopped = True

            if weekly_starting_equity > 0 and not is_permanent_stopped:
                weekly_dd = (equity - weekly_starting_equity) / weekly_starting_equity
                if weekly_dd <= -0.05 and not is_weekly_tripped:
                    is_weekly_tripped = True
                    circuit_breaker_trips += 1

            can_trade = (not is_weekly_tripped) and (not is_permanent_stopped)

            # === MANAGE OPEN POSITION ===
            if open_position is not None:
                bars_held = bar_idx - open_position["entry_bar_idx"]
                d = open_position["direction"]
                ep = open_position["entry_price"]
                sl_dist = open_position["sl_dist"]
                lot_a = open_position["lot_a"]
                lot_b = open_position["lot_b"]

                dow = ts.dayofweek if hasattr(ts, 'dayofweek') else pd.Timestamp(ts).dayofweek
                hour = ts.hour if hasattr(ts, 'hour') else pd.Timestamp(ts).hour

                is_friday_close = (dow == 4 and hour >= 20) or dow in [5, 6]
                is_time_barrier = (bars_held >= self.time_barrier_bars)

                if is_friday_close or is_time_barrier:
                    exit_reason = "FRIDAY_CLOSE" if is_friday_close else "TIME_BARRIER"
                    exit_price = bar_close

                    if open_position["pos_a_open"]:
                        pnl_a_g = (exit_price - ep) * lot_a * self.contract_size if d == "BUY" else (ep - exit_price) * lot_a * self.contract_size
                        f_a = self._friction_per_trade(lot_a)
                        open_position["pnl_net_accum"] += (pnl_a_g - f_a)
                        open_position["pos_a_open"] = False

                    if open_position["pos_b_open"]:
                        pnl_b_g = (exit_price - ep) * lot_b * self.contract_size if d == "BUY" else (ep - exit_price) * lot_b * self.contract_size
                        f_b = self._friction_per_trade(lot_b)
                        open_position["pnl_net_accum"] += (pnl_b_g - f_b)
                        open_position["pos_b_open"] = False

                    total_net = round(open_position["pnl_net_accum"], 2)
                    r_mult = round(total_net / open_position["risk_amount"], 3) if open_position["risk_amount"] > 0 else 0.0

                    trade_rec = TradeRecord(
                        trade_id=trade_counter,
                        direction=d,
                        entry_bar_idx=open_position["entry_bar_idx"],
                        exit_bar_idx=bar_idx,
                        entry_timestamp=open_position["entry_timestamp"],
                        exit_timestamp=ts,
                        entry_price=ep,
                        exit_price=exit_price,
                        sl_price=open_position["initial_sl"],
                        tp_price=open_position["tp2_price"],
                        lot_size=open_position["total_lot"],
                        r_target=self.tp2_r_ratio,
                        confidence=open_position["confidence"],
                        pnl_gross=round(total_net + self._friction_per_trade(open_position["total_lot"]), 2),
                        friction_cost=self._friction_per_trade(open_position["total_lot"]),
                        pnl_net=total_net,
                        r_multiple=r_mult,
                        exit_reason=exit_reason,
                        was_breakeven_moved=open_position["tp1_hit"],
                        bars_held=bars_held,
                        tp1_hit=open_position["tp1_hit"],
                        tp2_hit=open_position["tp2_hit"],
                    )
                    trades.append(trade_rec)
                    trade_counter += 1
                    equity += total_net
                    open_position = None

                else:
                    if d == "BUY":
                        # Check initial SL for both before BE
                        if not open_position["tp1_hit"] and bar_low <= open_position["cur_sl_a"]:
                            pnl_g = (open_position["cur_sl_a"] - ep) * open_position["total_lot"] * self.contract_size
                            fric = self._friction_per_trade(open_position["total_lot"])
                            pnl_net = round(pnl_g - fric, 2)
                            r_mult = round(pnl_net / open_position["risk_amount"], 3)

                            trades.append(TradeRecord(
                                trade_id=trade_counter,
                                direction=d,
                                entry_bar_idx=open_position["entry_bar_idx"],
                                exit_bar_idx=bar_idx,
                                entry_timestamp=open_position["entry_timestamp"],
                                exit_timestamp=ts,
                                entry_price=ep,
                                exit_price=open_position["cur_sl_a"],
                                sl_price=open_position["initial_sl"],
                                tp_price=open_position["tp2_price"],
                                lot_size=open_position["total_lot"],
                                r_target=self.tp2_r_ratio,
                                confidence=open_position["confidence"],
                                pnl_gross=round(pnl_g, 2),
                                friction_cost=fric,
                                pnl_net=pnl_net,
                                r_multiple=r_mult,
                                exit_reason="SL_HIT",
                                was_breakeven_moved=False,
                                bars_held=bars_held,
                                tp1_hit=False,
                                tp2_hit=False,
                            ))
                            trade_counter += 1
                            equity += pnl_net
                            open_position = None

                        else:
                            # Check TP1 (+1.0R) hit for Pos A
                            if open_position["pos_a_open"] and bar_high >= open_position["tp1_price"]:
                                pnl_a_g = (open_position["tp1_price"] - ep) * lot_a * self.contract_size
                                f_a = self._friction_per_trade(lot_a)
                                open_position["pnl_net_accum"] += (pnl_a_g - f_a)
                                open_position["pos_a_open"] = False
                                open_position["tp1_hit"] = True

                                # Move Pos B SL to Breakeven (entry + friction)
                                f_price = self.spread_price + (self.commission_per_lot / self.contract_size)
                                new_sl_b = round(ep + f_price, 2)
                                open_position["cur_sl_b"] = max(open_position["cur_sl_b"], new_sl_b)

                            # Check Pos B
                            if open_position["pos_b_open"]:
                                if bar_high >= open_position["tp2_price"]:
                                    pnl_b_g = (open_position["tp2_price"] - ep) * lot_b * self.contract_size
                                    f_b = self._friction_per_trade(lot_b)
                                    open_position["pnl_net_accum"] += (pnl_b_g - f_b)
                                    open_position["pos_b_open"] = False
                                    open_position["tp2_hit"] = True

                                    total_net = round(open_position["pnl_net_accum"], 2)
                                    r_mult = round(total_net / open_position["risk_amount"], 3)
                                    trades.append(TradeRecord(
                                        trade_id=trade_counter,
                                        direction=d,
                                        entry_bar_idx=open_position["entry_bar_idx"],
                                        exit_bar_idx=bar_idx,
                                        entry_timestamp=open_position["entry_timestamp"],
                                        exit_timestamp=ts,
                                        entry_price=ep,
                                        exit_price=open_position["tp2_price"],
                                        sl_price=open_position["initial_sl"],
                                        tp_price=open_position["tp2_price"],
                                        lot_size=open_position["total_lot"],
                                        r_target=self.tp2_r_ratio,
                                        confidence=open_position["confidence"],
                                        pnl_gross=round(total_net + self._friction_per_trade(open_position["total_lot"]), 2),
                                        friction_cost=self._friction_per_trade(open_position["total_lot"]),
                                        pnl_net=total_net,
                                        r_multiple=r_mult,
                                        exit_reason="TP2_HIT",
                                        was_breakeven_moved=True,
                                        bars_held=bars_held,
                                        tp1_hit=True,
                                        tp2_hit=True,
                                    ))
                                    trade_counter += 1
                                    equity += total_net
                                    open_position = None

                                elif bar_low <= open_position["cur_sl_b"]:
                                    exit_r = "BE_HIT" if open_position["tp1_hit"] else "SL_HIT"
                                    pnl_b_g = (open_position["cur_sl_b"] - ep) * lot_b * self.contract_size
                                    f_b = self._friction_per_trade(lot_b)
                                    open_position["pnl_net_accum"] += (pnl_b_g - f_b)
                                    open_position["pos_b_open"] = False

                                    total_net = round(open_position["pnl_net_accum"], 2)
                                    r_mult = round(total_net / open_position["risk_amount"], 3)
                                    trades.append(TradeRecord(
                                        trade_id=trade_counter,
                                        direction=d,
                                        entry_bar_idx=open_position["entry_bar_idx"],
                                        exit_bar_idx=bar_idx,
                                        entry_timestamp=open_position["entry_timestamp"],
                                        exit_timestamp=ts,
                                        entry_price=ep,
                                        exit_price=open_position["cur_sl_b"],
                                        sl_price=open_position["initial_sl"],
                                        tp_price=open_position["tp2_price"],
                                        lot_size=open_position["total_lot"],
                                        r_target=self.tp2_r_ratio,
                                        confidence=open_position["confidence"],
                                        pnl_gross=round(total_net + self._friction_per_trade(open_position["total_lot"]), 2),
                                        friction_cost=self._friction_per_trade(open_position["total_lot"]),
                                        pnl_net=total_net,
                                        r_multiple=r_mult,
                                        exit_reason=exit_r,
                                        was_breakeven_moved=open_position["tp1_hit"],
                                        bars_held=bars_held,
                                        tp1_hit=open_position["tp1_hit"],
                                        tp2_hit=False,
                                    ))
                                    trade_counter += 1
                                    equity += total_net
                                    open_position = None

                                elif open_position["tp1_hit"]:
                                    r_gain = (bar_high - ep) / sl_dist
                                    if r_gain >= self.trail_after_r:
                                        trail_sl = round(ep + (self.trail_distance_r * sl_dist), 2)
                                        open_position["cur_sl_b"] = max(open_position["cur_sl_b"], trail_sl)

                    elif d == "SELL":
                        if not open_position["tp1_hit"] and bar_high >= open_position["cur_sl_a"]:
                            pnl_g = (ep - open_position["cur_sl_a"]) * open_position["total_lot"] * self.contract_size
                            fric = self._friction_per_trade(open_position["total_lot"])
                            pnl_net = round(pnl_g - fric, 2)
                            r_mult = round(pnl_net / open_position["risk_amount"], 3)

                            trades.append(TradeRecord(
                                trade_id=trade_counter,
                                direction=d,
                                entry_bar_idx=open_position["entry_bar_idx"],
                                exit_bar_idx=bar_idx,
                                entry_timestamp=open_position["entry_timestamp"],
                                exit_timestamp=ts,
                                entry_price=ep,
                                exit_price=open_position["cur_sl_a"],
                                sl_price=open_position["initial_sl"],
                                tp_price=open_position["tp2_price"],
                                lot_size=open_position["total_lot"],
                                r_target=self.tp2_r_ratio,
                                confidence=open_position["confidence"],
                                pnl_gross=round(pnl_g, 2),
                                friction_cost=fric,
                                pnl_net=pnl_net,
                                r_multiple=r_mult,
                                exit_reason="SL_HIT",
                                was_breakeven_moved=False,
                                bars_held=bars_held,
                                tp1_hit=False,
                                tp2_hit=False,
                            ))
                            trade_counter += 1
                            equity += pnl_net
                            open_position = None

                        else:
                            if open_position["pos_a_open"] and bar_low <= open_position["tp1_price"]:
                                pnl_a_g = (ep - open_position["tp1_price"]) * lot_a * self.contract_size
                                f_a = self._friction_per_trade(lot_a)
                                open_position["pnl_net_accum"] += (pnl_a_g - f_a)
                                open_position["pos_a_open"] = False
                                open_position["tp1_hit"] = True

                                f_price = self.spread_price + (self.commission_per_lot / self.contract_size)
                                new_sl_b = round(ep - f_price, 2)
                                open_position["cur_sl_b"] = min(open_position["cur_sl_b"], new_sl_b)

                            if open_position["pos_b_open"]:
                                if bar_low <= open_position["tp2_price"]:
                                    pnl_b_g = (ep - open_position["tp2_price"]) * lot_b * self.contract_size
                                    f_b = self._friction_per_trade(lot_b)
                                    open_position["pnl_net_accum"] += (pnl_b_g - f_b)
                                    open_position["pos_b_open"] = False
                                    open_position["tp2_hit"] = True

                                    total_net = round(open_position["pnl_net_accum"], 2)
                                    r_mult = round(total_net / open_position["risk_amount"], 3)
                                    trades.append(TradeRecord(
                                        trade_id=trade_counter,
                                        direction=d,
                                        entry_bar_idx=open_position["entry_bar_idx"],
                                        exit_bar_idx=bar_idx,
                                        entry_timestamp=open_position["entry_timestamp"],
                                        exit_timestamp=ts,
                                        entry_price=ep,
                                        exit_price=open_position["tp2_price"],
                                        sl_price=open_position["initial_sl"],
                                        tp_price=open_position["tp2_price"],
                                        lot_size=open_position["total_lot"],
                                        r_target=self.tp2_r_ratio,
                                        confidence=open_position["confidence"],
                                        pnl_gross=round(total_net + self._friction_per_trade(open_position["total_lot"]), 2),
                                        friction_cost=self._friction_per_trade(open_position["total_lot"]),
                                        pnl_net=total_net,
                                        r_multiple=r_mult,
                                        exit_reason="TP2_HIT",
                                        was_breakeven_moved=True,
                                        bars_held=bars_held,
                                        tp1_hit=True,
                                        tp2_hit=True,
                                    ))
                                    trade_counter += 1
                                    equity += total_net
                                    open_position = None

                                elif bar_high >= open_position["cur_sl_b"]:
                                    exit_r = "BE_HIT" if open_position["tp1_hit"] else "SL_HIT"
                                    pnl_b_g = (ep - open_position["cur_sl_b"]) * lot_b * self.contract_size
                                    f_b = self._friction_per_trade(lot_b)
                                    open_position["pnl_net_accum"] += (pnl_b_g - f_b)
                                    open_position["pos_b_open"] = False

                                    total_net = round(open_position["pnl_net_accum"], 2)
                                    r_mult = round(total_net / open_position["risk_amount"], 3)
                                    trades.append(TradeRecord(
                                        trade_id=trade_counter,
                                        direction=d,
                                        entry_bar_idx=open_position["entry_bar_idx"],
                                        exit_bar_idx=bar_idx,
                                        entry_timestamp=open_position["entry_timestamp"],
                                        exit_timestamp=ts,
                                        entry_price=ep,
                                        exit_price=open_position["cur_sl_b"],
                                        sl_price=open_position["initial_sl"],
                                        tp_price=open_position["tp2_price"],
                                        lot_size=open_position["total_lot"],
                                        r_target=self.tp2_r_ratio,
                                        confidence=open_position["confidence"],
                                        pnl_gross=round(total_net + self._friction_per_trade(open_position["total_lot"]), 2),
                                        friction_cost=self._friction_per_trade(open_position["total_lot"]),
                                        pnl_net=total_net,
                                        r_multiple=r_mult,
                                        exit_reason=exit_r,
                                        was_breakeven_moved=open_position["tp1_hit"],
                                        bars_held=bars_held,
                                        tp1_hit=open_position["tp1_hit"],
                                        tp2_hit=False,
                                    ))
                                    trade_counter += 1
                                    equity += total_net
                                    open_position = None

                                elif open_position["tp1_hit"]:
                                    r_gain = (ep - bar_low) / sl_dist
                                    if r_gain >= self.trail_after_r:
                                        trail_sl = round(ep - (self.trail_distance_r * sl_dist), 2)
                                        open_position["cur_sl_b"] = min(open_position["cur_sl_b"], trail_sl)

            if in_date_range:
                equity_curve.append(equity)
                timestamps_list.append(ts)

            # === EVALUATE NEW ENTRY ===
            pred_idx = bar_idx - seq_offset
            if (
                in_date_range
                and pred_idx >= 0
                and pred_idx < len(predictions)
                and open_position is None
                and can_trade
                and daily_entries_count < self.max_daily_entries
                and is_eligible
                and not is_blackout
                and not is_permanent_stopped
            ):
                dow = ts.dayofweek if hasattr(ts, 'dayofweek') else pd.Timestamp(ts).dayofweek
                hour = ts.hour if hasattr(ts, 'hour') else pd.Timestamp(ts).hour
                minute = ts.minute if hasattr(ts, 'minute') else pd.Timestamp(ts).minute

                friday_freeze = (dow == 4 and hour >= 18) or dow in [5, 6]

                # London Open Sweep Quarantine (07:00 to 08:30 UTC)
                london_quarantine = self.quarantine_london_open and (hour == 7 or (hour == 8 and minute < 30))

                if not friday_freeze and not london_quarantine:
                    probs = predictions[pred_idx]
                    trade_probs = probs[1:]
                    max_class_idx = int(np.argmax(trade_probs))
                    action_class = max_class_idx + 1
                    confidence = float(trade_probs[max_class_idx])
                    p_hold = float(probs[0])

                    if confidence >= self.confidence_tau and confidence > p_hold:
                        direction = "BUY" if action_class in [1, 2] else "SELL"

                        # Structural Gate (Supply & Demand Order Blocks + Trend Slope)
                        structural_ok = True
                        if self.use_structural_filter:
                            ob_zone = float(row.get("order_block_zone", 0.0))
                            ma_slope = float(row.get("ma_ribbon_slope", 0.0))

                            # Don't BUY directly inside Supply Zone (-1) or crashing downtrend
                            if direction == "BUY" and (ob_zone < 0 or ma_slope < -0.3):
                                structural_ok = False
                            # Don't SELL directly inside Demand Zone (+1) or soaring uptrend
                            if direction == "SELL" and (ob_zone > 0 or ma_slope > 0.3):
                                structural_ok = False

                        if structural_ok:
                            atr_val = float(atr_values[bar_idx]) if bar_idx < len(atr_values) else 5.0
                            sl_distance = round(atr_val * self.sl_atr_multiplier, 2)

                            if sl_distance > 0:
                                lot_size, risk_amount = self._calculate_lot_size(equity, sl_distance)
                                lot_a = round(lot_size * self.pos_a_pct, 2)
                                lot_a = max(0.01, lot_a)
                                lot_b = round(lot_size - lot_a, 2)
                                lot_b = max(0.01, lot_b)

                                if lot_size >= 0.02 and risk_amount > 0:
                                    if direction == "BUY":
                                        ep = round(bar_close + self.slippage_price, 2)
                                        sl_price = round(ep - sl_distance, 2)
                                        tp1_p = round(ep + (self.tp1_r_ratio * sl_distance), 2)
                                        tp2_p = round(ep + (self.tp2_r_ratio * sl_distance), 2)
                                    else:
                                        ep = round(bar_close - self.slippage_price, 2)
                                        sl_price = round(ep + sl_distance, 2)
                                        tp1_p = round(ep - (self.tp1_r_ratio * sl_distance), 2)
                                        tp2_p = round(ep - (self.tp2_r_ratio * sl_distance), 2)

                                    open_position = {
                                        "direction": direction,
                                        "entry_bar_idx": bar_idx,
                                        "entry_timestamp": ts,
                                        "entry_price": ep,
                                        "sl_dist": sl_distance,
                                        "initial_sl": sl_price,
                                        "cur_sl_a": sl_price,
                                        "cur_sl_b": sl_price,
                                        "tp1_price": tp1_p,
                                        "tp2_price": tp2_p,
                                        "total_lot": lot_size,
                                        "lot_a": lot_a,
                                        "lot_b": lot_b,
                                        "risk_amount": risk_amount,
                                        "confidence": confidence,
                                        "pos_a_open": True,
                                        "pos_b_open": True,
                                        "tp1_hit": False,
                                        "tp2_hit": False,
                                        "pnl_net_accum": 0.0,
                                    }
                                    daily_entries_count += 1

        result = self._compute_metrics(trades, np.array(equity_curve), timestamps_list,
                                        weekly_drawdowns, circuit_breaker_trips)
        return result

    def _compute_metrics(
        self,
        trades: List[TradeRecord],
        equity_curve: np.ndarray,
        timestamps: List[pd.Timestamp],
        weekly_drawdowns: Dict[str, float],
        circuit_breaker_trips: int,
    ) -> BacktestResult:
        n_trades = len(trades)
        if n_trades == 0:
            return BacktestResult(
                trades=trades,
                equity_curve=equity_curve,
                timestamps=timestamps,
                initial_equity=self.initial_equity,
                final_equity=float(equity_curve[-1]) if len(equity_curve) > 0 else self.initial_equity,
                total_trades=0,
                weekly_drawdowns=weekly_drawdowns,
                circuit_breaker_trips=circuit_breaker_trips,
            )

        pnl_nets = np.array([t.pnl_net for t in trades])
        r_mults = np.array([t.r_multiple for t in trades])

        winners = pnl_nets > 0
        losers = pnl_nets < 0
        be = pnl_nets == 0

        winning_trades = int(np.sum(winners))
        losing_trades = int(np.sum(losers))
        breakeven_trades = int(np.sum(be))
        win_rate = winning_trades / n_trades if n_trades > 0 else 0.0

        gross_pnl = float(np.sum([t.pnl_gross for t in trades]))
        net_pnl = float(np.sum(pnl_nets))
        total_friction = float(np.sum([t.friction_cost for t in trades]))

        gross_profit = float(np.sum(pnl_nets[winners])) if np.any(winners) else 0.0
        gross_loss = abs(float(np.sum(pnl_nets[losers]))) if np.any(losers) else 0.0
        net_profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0

        avg_r = float(np.mean(r_mults)) if n_trades > 0 else 0.0
        avg_win_r = float(np.mean(r_mults[winners])) if np.any(winners) else 0.0
        avg_loss_r = float(np.mean(r_mults[losers])) if np.any(losers) else 0.0
        expectancy_r = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r

        bars_held = [t.bars_held for t in trades]
        avg_bars = float(np.mean(bars_held)) if bars_held else 0.0

        tp1_hits = sum(1 for t in trades if t.tp1_hit)
        tp2_hits = sum(1 for t in trades if t.tp2_hit)

        max_consec_loss = 0
        current_streak = 0
        for pnl in pnl_nets:
            if pnl < 0:
                current_streak += 1
                max_consec_loss = max(max_consec_loss, current_streak)
            else:
                current_streak = 0

        if n_trades >= 2:
            trade_returns = pnl_nets / self.initial_equity
            mean_ret = float(np.mean(trade_returns))
            std_ret = float(np.std(trade_returns, ddof=1))
            days_span = 252
            trades_per_year = n_trades
            sharpe = (mean_ret / std_ret * np.sqrt(trades_per_year)) if std_ret > 0 else 0.0
            downside = trade_returns[trade_returns < 0]
            sortino = (mean_ret / float(np.std(downside, ddof=1)) * np.sqrt(trades_per_year)) if len(downside) > 1 and float(np.std(downside, ddof=1)) > 0 else sharpe
        else:
            sharpe = 0.0
            sortino = 0.0

        peak = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - peak) / peak
        max_dd_pct = float(np.min(drawdown))
        max_dd_usd = float(np.min(equity_curve - peak))

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            timestamps=timestamps,
            initial_equity=self.initial_equity,
            final_equity=float(equity_curve[-1]),
            total_trades=n_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            breakeven_trades=breakeven_trades,
            win_rate=round(win_rate, 4),
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            total_friction=round(total_friction, 2),
            gross_profit=round(gross_profit, 2),
            gross_loss=round(gross_loss, 2),
            net_profit_factor=round(net_profit_factor, 4),
            avg_r_multiple=round(avg_r, 4),
            avg_win_r=round(avg_win_r, 4),
            avg_loss_r=round(avg_loss_r, 4),
            expectancy_r=round(expectancy_r, 4),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            max_drawdown_pct=round(max_dd_pct, 4),
            max_drawdown_usd=round(max_dd_usd, 2),
            max_consecutive_losses=max_consec_loss,
            avg_bars_held=round(avg_bars, 1),
            tp1_hits=tp1_hits,
            tp2_hits=tp2_hits,
            total_non_hold_signals=n_trades,
            non_hold_precision=round(win_rate, 4),
            weekly_drawdowns=weekly_drawdowns,
            circuit_breaker_trips=circuit_breaker_trips,
        )
