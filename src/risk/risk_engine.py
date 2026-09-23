"""
XAU_DEEP_SNIPER - Unified Structural Risk Management Engine (TAHAP 5)
======================================================================
Mengintegrasikan seluruh gerbang pertahanan modal ke dalam satu engine terpadu:
1. Hard Deterministic News Blackout Gate (TAHAP 3)
2. Friday Close-Out Rule (BAB 8.4)
3. Weekly Drawdown Circuit Breaker (BAB 8.2)
4. Trade Concurrency Gate
5. Model Confidence Threshold Gate
6. Dynamic Fractional Position Sizer (BAB 8.1)
7. Trailing Breakeven Manager (+0.7R) (BAB 8.3)
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import pandas as pd
import numpy as np

from .position_sizer import DynamicPositionSizer, PositionSizeResult
from .circuit_breaker import WeeklyCircuitBreaker, CircuitBreakerStatus
from .trailing_breakeven import TrailingBreakevenManager, BreakevenResult
from .friday_closeout import FridayCloseoutRule, FridayRuleStatus
from .concurrency_gate import ConcurrencyGate, ConfidenceThresholdGate


class OrderAction(Enum):
    HOLD = 0
    BUY = 1
    SELL = 2


@dataclass
class ExecutionOrder:
    symbol: str
    action: OrderAction
    lot_size: float
    entry_price: float
    sl_price: float
    tp_1r_price: float
    tp_2r_price: float
    r_target: int               # 1 (1R) atau 2 (2R)
    timestamp_utc: pd.Timestamp
    risk_amount_usd: float
    confidence_score: float
    notes: str = ""


@dataclass
class TradeEvaluationResult:
    can_execute: bool
    order: Optional[ExecutionOrder]
    rejection_reasons: List[str]


class StructuralRiskEngine:
    """
    Mesin Pengendalian Risiko Struktural Terpadu.
    """

    def __init__(
        self,
        symbol: str = "XAUUSD",
        risk_fraction: float = 0.01,
        confidence_tau: float = 0.35,
        weekly_drawdown_limit: float = 0.05,
        news_blackout_gate = None, # Optional instance dari NewsBlackoutGate
    ):
        self.symbol = symbol
        self.position_sizer = DynamicPositionSizer(default_risk_fraction=risk_fraction)
        self.circuit_breaker = WeeklyCircuitBreaker(weekly_drawdown_limit=weekly_drawdown_limit)
        self.friday_rule = FridayCloseoutRule()
        self.concurrency_gate = ConcurrencyGate(max_concurrent_positions=1)
        self.confidence_gate = ConfidenceThresholdGate(default_tau=confidence_tau)
        self.breakeven_manager = TrailingBreakevenManager(be_trigger_r=0.7)
        self.news_blackout_gate = news_blackout_gate

    def evaluate_entry(
        self,
        timestamp_utc: pd.Timestamp,
        current_equity: float,
        model_probabilities: np.ndarray,
        entry_price: float,
        atr_value: float,
        current_positions: Optional[List[Dict[str, Any]]] = None,
        sl_atr_multiplier: float = 1.5,
    ) -> TradeEvaluationResult:
        """
        Evaluasi lengkap sinyal masuk melewati seluruh gerbang proteksi modal.
        """
        rejection_reasons = []
        positions = current_positions or []

        # 1. Update & Cek Weekly Circuit Breaker
        cb_status = self.circuit_breaker.update(current_equity, timestamp_utc)
        if not cb_status.can_trade:
            rejection_reasons.append(f"CIRCUIT_BREAKER: {cb_status.rejection_reason}")

        # 2. Cek Friday Close-Out Rule
        friday_status = self.friday_rule.check(timestamp_utc)
        if not friday_status.allow_new_entries:
            rejection_reasons.append(f"FRIDAY_RULE: {friday_status.reason}")

        # 3. Cek Hard News Blackout Gate jika dikonfigurasi
        if self.news_blackout_gate is not None:
            is_blackout = self.news_blackout_gate.is_blackout(timestamp_utc)
            if is_blackout:
                rejection_reasons.append("NEWS_BLACKOUT: Bar falls within High-Impact macro event blackout window (T +/- 30m)")

        # 4. Cek Confidence Threshold Gate
        is_confident, action_class, confidence, conf_reason = self.confidence_gate.evaluate_signal(model_probabilities)
        if not is_confident or action_class == 0:
            rejection_reasons.append(f"CONFIDENCE_GATE: {conf_reason}")
            return TradeEvaluationResult(can_execute=False, order=None, rejection_reasons=rejection_reasons)

        # Mapping action_class ke arah order
        # 1 = BUY 1R, 2 = BUY 2R, 3 = SELL 1R, 4 = SELL 2R
        if action_class in [1, 2]:
            order_action = OrderAction.BUY
            r_target = 1 if action_class == 1 else 2
        elif action_class in [3, 4]:
            order_action = OrderAction.SELL
            r_target = 1 if action_class == 3 else 2
        else:
            return TradeEvaluationResult(can_execute=False, order=None, rejection_reasons=["Invalid action class"])

        # 5. Cek Concurrency Gate
        can_open_conc, conc_reason = self.concurrency_gate.can_open(positions, order_action.name)
        if not can_open_conc:
            rejection_reasons.append(f"CONCURRENCY_GATE: {conc_reason}")

        # Hitung SL & TP
        sl_dist = self.position_sizer.calculate_sl_from_atr(atr_value, sl_atr_multiplier)
        if order_action == OrderAction.BUY:
            sl_price = round(entry_price - sl_dist, 2)
            tp_1r = round(entry_price + sl_dist, 2)
            tp_2r = round(entry_price + (2.0 * sl_dist), 2)
        else:
            sl_price = round(entry_price + sl_dist, 2)
            tp_1r = round(entry_price - sl_dist, 2)
            tp_2r = round(entry_price - (2.0 * sl_dist), 2)

        # 6. Hitung Dynamic Lot Sizing
        size_result = self.position_sizer.calculate_lot(current_equity, sl_dist)
        if not size_result.is_valid:
            rejection_reasons.append(f"POSITION_SIZER: {size_result.rejection_reason}")

        # Jika ada gerbang yang menolak, gagalkan eksekusi
        if len(rejection_reasons) > 0:
            return TradeEvaluationResult(can_execute=False, order=None, rejection_reasons=rejection_reasons)

        # Semua gerbang lolos -> Terbitkan order resmi
        order = ExecutionOrder(
            symbol=self.symbol,
            action=order_action,
            lot_size=size_result.lot_size,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_1r_price=tp_1r,
            tp_2r_price=tp_2r,
            r_target=r_target,
            timestamp_utc=timestamp_utc,
            risk_amount_usd=size_result.risk_amount_usd,
            confidence_score=confidence,
            notes=f"Class {action_class} ({order_action.name} {r_target}R), SL Dist=${sl_dist:.2f}",
        )

        return TradeEvaluationResult(can_execute=True, order=order, rejection_reasons=[])

    def evaluate_open_trade(
        self,
        action: str,
        entry_price: float,
        initial_sl: float,
        current_sl: float,
        bar_high: float,
        bar_low: float,
        timestamp_utc: pd.Timestamp,
    ) -> Dict[str, Any]:
        """
        Memantau posisi terbuka: memeriksa trailing breakeven (+0.7R) dan likuidasi Jumat 20:00 UTC.
        """
        # Cek Jumat likuidasi paksa
        friday_status = self.friday_rule.check(timestamp_utc)
        if friday_status.force_liquidate_all:
            return {
                "action": "FORCE_CLOSE",
                "reason": friday_status.reason,
                "modify_sl": False,
                "new_sl": current_sl,
            }

        # Cek Trailing Breakeven
        be_res = self.breakeven_manager.evaluate(
            action=action,
            entry_price=entry_price,
            initial_sl=initial_sl,
            current_sl=current_sl,
            bar_high=bar_high,
            bar_low=bar_low,
        )

        return {
            "action": "HOLD",
            "reason": be_res.reason,
            "modify_sl": be_res.should_modify_sl,
            "new_sl": be_res.new_sl_price,
            "is_breakeven_active": be_res.is_breakeven_active,
        }
