"""
FLOWDEV FRAME - Real-Time Paper Trading Broker Engine
Realistic simulated execution engine tracking live cash, floating equity,
lot volume, realistic spread, slippage, commissions, and order lifecycle.
"""

import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import pandas as pd

from src.frame.constants import (
    CONTRACT_SIZE, SPREAD_PIPS, SLIPPAGE_PIPS, COMMISSION_PER_LOT
)

class LivePaperBroker:
    def __init__(self, initial_capital: float = 500.0, lot_mode: str = "flat", max_lot: float = 2.0):
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.lot_mode = lot_mode  # "flat" or "dynamic"
        self.max_lot = float(max_lot)
        
        # Open position: only 1 concurrent position allowed by contract
        self.open_position: Optional[Dict[str, Any]] = None
        self.trade_history: List[Dict[str, Any]] = []
        
        # Real-time metrics
        self.peak_equity = float(initial_capital)
        self.lowest_equity = float(initial_capital)
        
    def reset(self, new_capital: Optional[float] = None):
        if new_capital is not None:
            self.initial_capital = float(new_capital)
        self.cash = self.initial_capital
        self.open_position = None
        self.trade_history.clear()
        self.peak_equity = self.initial_capital
        self.lowest_equity = self.initial_capital

    def calculate_lot(self) -> float:
        if self.lot_mode == "dynamic":
            raw_lot = (self.get_equity() / self.initial_capital) * 0.01
            return round(max(0.01, min(self.max_lot, raw_lot)), 2)
        return 0.01

    def calculate_friction(self, lot: float) -> float:
        spread_cost = SPREAD_PIPS * 0.10 * lot * CONTRACT_SIZE
        slippage_cost = SLIPPAGE_PIPS * 0.10 * lot * CONTRACT_SIZE * 2
        comm_cost = COMMISSION_PER_LOT * lot
        return round(spread_cost + slippage_cost + comm_cost, 3)

    def open_order(
        self,
        direction: str,
        current_bid: float,
        current_ask: float,
        sl_dist: float,
        timestamp: Optional[datetime] = None,
        reason: str = "Signal"
    ) -> Dict[str, Any]:
        if self.open_position is not None:
            raise RuntimeError("Cannot open order: a position is already active.")
        
        lot = self.calculate_lot()
        friction = self.calculate_friction(lot)
        
        # Execution price includes half slippage + actual spread
        if direction.upper() == "BUY":
            entry_price = round(current_ask + (SLIPPAGE_PIPS * 0.10), 2)
            sl_price = round(entry_price - sl_dist, 2)
            tp_price = round(entry_price + (2.7 * sl_dist), 2)
            be_trigger = round(entry_price + (0.75 * sl_dist), 2)
        else: # SELL
            entry_price = round(current_bid - (SLIPPAGE_PIPS * 0.10), 2)
            sl_price = round(entry_price + sl_dist, 2)
            tp_price = round(entry_price - (2.7 * sl_dist), 2)
            be_trigger = round(entry_price - (0.75 * sl_dist), 2)

        now = timestamp or datetime.now(timezone.utc)
        self.open_position = {
            "id": f"ORD-{int(time.time()*1000)%1000000}",
            "direction": direction.upper(),
            "lot": lot,
            "entry_price": entry_price,
            "current_sl": sl_price,
            "initial_sl": sl_price,
            "current_tp": tp_price,
            "sl_dist": sl_dist,
            "be_trigger_price": be_trigger,
            "be_activated": False,
            "ratchet_activated": False,
            "trail_activated": False,
            "stale_decay_activated": False,
            "peak_price": entry_price,
            "friction": friction,
            "bars_held": 1,
            "open_time": now.isoformat(),
            "open_timestamp": now,
            "reason": reason,
            "floating_pnl": -friction,
            "floating_r": 0.0,
        }
        return self.open_position

    def update_tick(self, current_bid: float, current_ask: float) -> Optional[Dict[str, Any]]:
        """
        Updates floating PnL and monitors price for active position.
        Returns closed trade dictionary if SL or TP is reached, else None.
        """
        if self.open_position is None:
            return None
        
        pos = self.open_position
        d = pos["direction"]
        ep = pos["entry_price"]
        lot = pos["lot"]
        sl_dist = pos["sl_dist"]
        friction = pos["friction"]

        if d == "BUY":
            price_for_pnl = current_bid
            price_for_sl = current_bid
            price_for_tp = current_bid
            # update peak
            if current_bid > pos["peak_price"]:
                pos["peak_price"] = current_bid
            
            raw_gain = (price_for_pnl - ep) * lot * CONTRACT_SIZE
            pos["floating_pnl"] = round(raw_gain - friction, 2)
            pos["floating_r"] = round((price_for_pnl - ep) / sl_dist, 2) if sl_dist > 0 else 0.0

            # 1. Take Profit
            if current_bid >= pos["current_tp"]:
                return self.close_order(pos["current_tp"], exit_reason="Take Profit (+2.7R)")
            
            # 2. Stop Loss
            if current_bid <= pos["current_sl"]:
                reason = "Protected Stop (BE/Ratchet)" if pos["be_activated"] else (
                    "Stale Decay Stop" if pos["stale_decay_activated"] else "Stop Loss"
                )
                return self.close_order(pos["current_sl"], exit_reason=reason)

        else: # SELL
            price_for_pnl = current_ask
            price_for_sl = current_ask
            price_for_tp = current_ask
            if current_ask < pos["peak_price"]:
                pos["peak_price"] = current_ask
            
            raw_gain = (ep - price_for_pnl) * lot * CONTRACT_SIZE
            pos["floating_pnl"] = round(raw_gain - friction, 2)
            pos["floating_r"] = round((ep - price_for_pnl) / sl_dist, 2) if sl_dist > 0 else 0.0

            # 1. Take Profit
            if current_ask <= pos["current_tp"]:
                return self.close_order(pos["current_tp"], exit_reason="Take Profit (+2.7R)")
            
            # 2. Stop Loss
            if current_ask >= pos["current_sl"]:
                reason = "Protected Stop (BE/Ratchet)" if pos["be_activated"] else (
                    "Stale Decay Stop" if pos["stale_decay_activated"] else "Stop Loss"
                )
                return self.close_order(pos["current_sl"], exit_reason=reason)

        # Track lowest/peak equity
        cur_eq = self.get_equity()
        if cur_eq > self.peak_equity:
            self.peak_equity = cur_eq
        if cur_eq < self.lowest_equity:
            self.lowest_equity = cur_eq

        return None

    def close_order(
        self,
        exit_price: float,
        exit_reason: str = "Manual Close",
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        if self.open_position is None:
            raise RuntimeError("No position is currently open.")
        
        pos = self.open_position
        d = pos["direction"]
        ep = pos["entry_price"]
        lot = pos["lot"]
        friction = pos["friction"]

        price_diff = (exit_price - ep) if d == "BUY" else (ep - exit_price)
        net_pnl = round((price_diff * lot * CONTRACT_SIZE) - friction, 2)

        self.cash = round(self.cash + net_pnl, 2)
        now = timestamp or datetime.now(timezone.utc)

        trade = {
            "id": pos["id"],
            "direction": d,
            "lot": lot,
            "entry_price": ep,
            "exit_price": round(exit_price, 2),
            "sl_dist": pos["sl_dist"],
            "net_pnl": net_pnl,
            "friction": friction,
            "balance": self.cash,
            "bars_held": pos["bars_held"],
            "open_time": pos["open_time"],
            "close_time": now.isoformat(),
            "close_timestamp": now,
            "exit_reason": exit_reason,
            "win": 1 if net_pnl > 0 else 0
        }

        self.trade_history.append(trade)
        self.open_position = None

        if self.cash > self.peak_equity:
            self.peak_equity = self.cash
        if self.cash < self.lowest_equity:
            self.lowest_equity = self.cash

        return trade

    def get_equity(self) -> float:
        if self.open_position is not None:
            return round(self.cash + self.open_position.get("floating_pnl", 0.0), 2)
        return round(self.cash, 2)

    def get_stats(self) -> Dict[str, Any]:
        equity = self.get_equity()
        n_trades = len(self.trade_history)
        wins = [t for t in self.trade_history if t["win"] == 1]
        losses = [t for t in self.trade_history if t["win"] == 0]
        wr = (len(wins) / n_trades * 100) if n_trades > 0 else 0.0
        
        tot_win = sum(t["net_pnl"] for t in wins)
        tot_loss = abs(sum(t["net_pnl"] for t in losses))
        pf = round(tot_win / tot_loss, 2) if tot_loss > 0 else (999.0 if tot_win > 0 else 0.0)
        
        net_profit = round(equity - self.initial_capital, 2)
        ret_pct = round((net_profit / self.initial_capital) * 100, 2)
        max_dd = round(((self.peak_equity - equity) / self.peak_equity * 100), 2) if self.peak_equity > 0 else 0.0
        
        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "equity": equity,
            "net_profit": net_profit,
            "return_pct": ret_pct,
            "total_trades": n_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(wr, 1),
            "profit_factor": pf,
            "max_drawdown": max_dd,
            "lowest_equity": self.lowest_equity,
            "has_open_position": (self.open_position is not None),
            "open_position": self.open_position
        }
