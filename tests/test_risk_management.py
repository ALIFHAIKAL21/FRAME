"""
XAU_DEEP_SNIPER - Structural Risk Management Unit Tests (TAHAP 5)
==================================================================
Memverifikasi kepatuhan matematis dan logis terhadap spesifikasi BAB 8:
- Dynamic lot sizing accuracy & bounds
- Weekly circuit breaker 5% cap & calendar week auto-reset
- Trailing breakeven trigger at +0.7R with spread/commission friction coverage
- Friday close-out rule (18:00 UTC freeze & 20:00 UTC liquidation)
- Trade concurrency & directional exposure gates
- Confidence threshold filtering (tau)
- Full end-to-end StructuralRiskEngine order generation
"""

import pytest
import pandas as pd
import numpy as np

from src.risk.position_sizer import DynamicPositionSizer
from src.risk.circuit_breaker import WeeklyCircuitBreaker
from src.risk.trailing_breakeven import TrailingBreakevenManager
from src.risk.friday_closeout import FridayCloseoutRule
from src.risk.concurrency_gate import ConcurrencyGate, ConfidenceThresholdGate
from src.risk.risk_engine import StructuralRiskEngine, OrderAction


class TestPositionSizer:
    def test_lot_size_mathematical_formula(self):
        # Equity = $10,000, Risk = 1.0% ($100), SL Distance = $10.00
        # Contract size = 100 oz -> Loss per lot = $1,000
        # Expected lot = $100 / $1,000 = 0.10 lot
        sizer = DynamicPositionSizer(default_risk_fraction=0.01, contract_size=100.0)
        res = sizer.calculate_lot(equity=10000.0, sl_distance_price=10.0)
        assert res.is_valid is True
        assert res.lot_size == 0.10
        assert res.risk_amount_usd == 100.0

    def test_lot_size_downward_rounding(self):
        # Equity = $10,000, Risk = 1% ($100), SL Distance = $15.00
        # Raw lot = 100 / 1500 = 0.06666... lot -> Floor to 0.06 lot
        sizer = DynamicPositionSizer(default_risk_fraction=0.01, contract_size=100.0)
        res = sizer.calculate_lot(equity=10000.0, sl_distance_price=15.0)
        assert res.is_valid is True
        assert res.lot_size == 0.06
        # Actual risk must never exceed $100 target
        assert res.risk_amount_usd == 90.0
        assert res.risk_amount_usd <= 100.0

    def test_risk_fraction_capped_at_maximum(self):
        sizer = DynamicPositionSizer(default_risk_fraction=0.01, max_risk_fraction=0.02)
        # Request 5% risk -> should be clamped to 2% ($200)
        res = sizer.calculate_lot(equity=10000.0, sl_distance_price=10.0, risk_fraction=0.05)
        assert res.is_valid is True
        assert res.lot_size == 0.20
        assert res.risk_amount_usd == 200.0

    def test_invalid_parameters_rejected(self):
        sizer = DynamicPositionSizer()
        assert sizer.calculate_lot(equity=0.0, sl_distance_price=10.0).is_valid is False
        assert sizer.calculate_lot(equity=-500.0, sl_distance_price=10.0).is_valid is False
        assert sizer.calculate_lot(equity=10000.0, sl_distance_price=0.0).is_valid is False
        assert sizer.calculate_lot(equity=10000.0, sl_distance_price=-5.0).is_valid is False


class TestWeeklyCircuitBreaker:
    def test_circuit_breaker_trips_at_5_percent(self):
        cb = WeeklyCircuitBreaker(weekly_drawdown_limit=0.05)
        t0 = pd.Timestamp("2026-03-02 08:00:00", tz="UTC") # Monday
        status = cb.update(10000.0, t0)
        assert status.can_trade is True
        assert status.is_tripped is False

        # Loss of 4% ($9,600) -> Still can trade
        t1 = pd.Timestamp("2026-03-03 10:00:00", tz="UTC")
        status1 = cb.update(9600.0, t1)
        assert status1.can_trade is True

        # Loss of 5.1% ($9,490) -> Tripped!
        t2 = pd.Timestamp("2026-03-04 14:00:00", tz="UTC")
        status2 = cb.update(9490.0, t2)
        assert status2.is_tripped is True
        assert status2.can_trade is False
        assert "Weekly circuit breaker triggered" in status2.rejection_reason

    def test_circuit_breaker_resets_on_new_week(self):
        cb = WeeklyCircuitBreaker(weekly_drawdown_limit=0.05)
        # Week 10
        t0 = pd.Timestamp("2026-03-02 08:00:00", tz="UTC")
        cb.update(10000.0, t0)
        # Tripped on Thursday
        t1 = pd.Timestamp("2026-03-05 14:00:00", tz="UTC")
        cb.update(9400.0, t1)
        can_trade, _ = cb.can_trade()
        assert can_trade is False

        # Next Monday (Week 11) -> Automatic reset!
        t_next_week = pd.Timestamp("2026-03-09 08:00:00", tz="UTC")
        status_reset = cb.update(9400.0, t_next_week)
        assert status_reset.can_trade is True
        assert status_reset.is_tripped is False
        assert status_reset.weekly_starting_equity == 9400.0

    def test_permanent_emergency_shutdown_at_50_percent(self):
        cb = WeeklyCircuitBreaker(absolute_drawdown_limit=0.50)
        t0 = pd.Timestamp("2026-03-02 08:00:00", tz="UTC")
        cb.update(10000.0, t0)
        # Drop 55%
        status = cb.update(4500.0, pd.Timestamp("2026-03-03 08:00:00", tz="UTC"))
        assert status.can_trade is False
        assert "Absolute safety limit reached" in status.rejection_reason


class TestTrailingBreakeven:
    def test_breakeven_triggers_at_plus_0_7r_buy(self):
        manager = TrailingBreakevenManager(be_trigger_r=0.7, default_spread_pip=0.75, commission_per_lot=3.50)
        # Entry = 2650.00, SL = 2640.00 -> R = 10.00. Trigger at +0.7R = 2657.00
        # Friction = $0.075 + $0.035 = $0.11
        # When high = 2656.00 (+0.6R) -> Not triggered
        res1 = manager.evaluate(action="BUY", entry_price=2650.0, initial_sl=2640.0, current_sl=2640.0, bar_high=2656.0, bar_low=2648.0)
        assert res1.is_breakeven_active is False
        assert res1.should_modify_sl is False

        # When high reaches 2657.50 (+0.75R) -> Triggered!
        res2 = manager.evaluate(action="BUY", entry_price=2650.0, initial_sl=2640.0, current_sl=2640.0, bar_high=2657.5, bar_low=2648.0)
        assert res2.is_breakeven_active is True
        assert res2.should_modify_sl is True
        assert res2.new_sl_price == 2650.11 # Entry + friction ($0.11)

    def test_breakeven_triggers_at_plus_0_7r_sell(self):
        manager = TrailingBreakevenManager(be_trigger_r=0.7)
        # Entry = 2650.00, SL = 2660.00 -> R = 10.00. Trigger at +0.7R (low <= 2643.00)
        res = manager.evaluate(action="SELL", entry_price=2650.0, initial_sl=2660.0, current_sl=2660.0, bar_high=2652.0, bar_low=2642.5)
        assert res.is_breakeven_active is True
        assert res.should_modify_sl is True
        assert res.new_sl_price == 2649.89 # Entry - friction ($0.11)


class TestFridayCloseout:
    def test_friday_hours(self):
        rule = FridayCloseoutRule(entry_freeze_hour_utc=18, liquidation_hour_utc=20)
        # Friday 14:00 UTC -> Normal
        t_norm = pd.Timestamp("2026-03-06 14:00:00", tz="UTC")
        res_norm = rule.check(t_norm)
        assert res_norm.allow_new_entries is True
        assert res_norm.force_liquidate_all is False

        # Friday 18:30 UTC -> Freeze entries
        t_freeze = pd.Timestamp("2026-03-06 18:30:00", tz="UTC")
        res_freeze = rule.check(t_freeze)
        assert res_freeze.allow_new_entries is False
        assert res_freeze.force_liquidate_all is False

        # Friday 20:30 UTC -> Force liquidate
        t_liq = pd.Timestamp("2026-03-06 20:30:00", tz="UTC")
        res_liq = rule.check(t_liq)
        assert res_liq.allow_new_entries is False
        assert res_liq.force_liquidate_all is True


class TestConcurrencyAndConfidence:
    def test_concurrency_gate(self):
        gate = ConcurrencyGate(max_concurrent_positions=1)
        # No positions -> can open
        ok, _ = gate.can_open([], "BUY")
        assert ok is True

        # 1 open BUY position -> cannot open another
        ok2, _ = gate.can_open([{"action": "BUY"}], "BUY")
        assert ok2 is False

        # Hedging conflict
        ok3, _ = gate.can_open([{"action": "BUY"}], "SELL")
        assert ok3 is False

    def test_confidence_gate(self):
        gate = ConfidenceThresholdGate(default_tau=0.35)
        # Model output with max prob = 0.42 for BUY_2R (class 2)
        probs = np.array([0.20, 0.15, 0.42, 0.13, 0.10])
        ok, action_cls, conf, _ = gate.evaluate_signal(probs)
        assert ok is True
        assert action_cls == 2
        assert conf == 0.42

        # Weak signal: max action prob = 0.28 < 0.35
        weak_probs = np.array([0.30, 0.15, 0.28, 0.14, 0.13])
        ok_weak, _, _, _ = gate.evaluate_signal(weak_probs)
        assert ok_weak is False


class TestStructuralRiskEngineEndToEnd:
    def test_clean_order_generation(self):
        engine = StructuralRiskEngine(risk_fraction=0.01, confidence_tau=0.35)
        t = pd.Timestamp("2026-03-03 10:00:00", tz="UTC") # Tuesday normal
        probs = np.array([0.15, 0.10, 0.45, 0.15, 0.15]) # Strong BUY_2R
        eval_res = engine.evaluate_entry(
            timestamp_utc=t,
            current_equity=10000.0,
            model_probabilities=probs,
            entry_price=2650.0,
            atr_value=8.0,
            current_positions=[],
        )
        assert eval_res.can_execute is True
        assert eval_res.order is not None
        order = eval_res.order
        assert order.action == OrderAction.BUY
        assert order.r_target == 2
        assert order.sl_price == 2638.0 # 2650 - (8.0 * 1.5) = 2638.0
        assert order.tp_2r_price == 2674.0 # 2650 + (2.0 * 12.0) = 2674.0
        assert order.lot_size > 0

    def test_order_blocked_when_circuit_breaker_active(self):
        engine = StructuralRiskEngine()
        # Trigger weekly breaker with >5% loss
        engine.circuit_breaker.update(10000.0, pd.Timestamp("2026-03-02 08:00:00", tz="UTC"))
        engine.circuit_breaker.update(9400.0, pd.Timestamp("2026-03-03 08:00:00", tz="UTC"))

        probs = np.array([0.10, 0.10, 0.50, 0.15, 0.15])
        eval_res = engine.evaluate_entry(
            timestamp_utc=pd.Timestamp("2026-03-03 09:00:00", tz="UTC"),
            current_equity=9400.0,
            model_probabilities=probs,
            entry_price=2650.0,
            atr_value=8.0,
        )
        assert eval_res.can_execute is False
        assert any("CIRCUIT_BREAKER" in r for r in eval_res.rejection_reasons)
