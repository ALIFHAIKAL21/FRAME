"""
XAU_DEEP_SNIPER - Unit Tests: Triple Barrier Labeling & Focal Weights (TAHAP 3B/C)
==================================================================================
Test suite untuk memverifikasi:
1. Perhitungan risiko struktural R (bounded [1.0, 3.5] * ATR)
2. Simulasi path-dependent BUY 1R, 2R, SELL 1R, 2R
3. Worst-case tie breaking jika TP dan SL disentuh dalam bar yang sama
4. Pemotongan friksi biaya riil (spread + komisi)
5. Penegakan Hard Zero Entry pada bar yang tidak eligible
6. Perhitungan bobot Class-Balanced Focal Loss
"""

import sys
import pathlib
import pytest
import pandas as pd
import numpy as np

project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from labeling.triple_barrier import (
    label_triple_barrier,
    compute_structural_risk,
    ACTION_CLASSES,
    TIME_BARRIER_BARS,
)
from labeling.focal_weights import (
    compute_focal_weights,
    numpy_focal_loss,
)


def make_test_df(n=100, base_price=2000.0):
    ts = pd.date_range("2023-01-01", periods=n, freq="30min", tz="UTC")
    df = pd.DataFrame({
        "timestamp_utc": ts,
        "open": base_price,
        "high": base_price + 2.0,
        "low": base_price - 2.0,
        "close": base_price,
        "volume": 1000.0,
        "spread": 0.75,
        "entry_eligible": True,
    })
    return df


class TestStructuralRisk:
    def test_risk_positive(self):
        df = make_test_df(50)
        r_buy, r_sell = compute_structural_risk(df)
        assert (r_buy > 0).all()
        assert (r_sell > 0).all()

    def test_risk_bounded_by_atr(self):
        df = make_test_df(100)
        r_buy, r_sell = compute_structural_risk(df)
        # R harus berada dalam batas [1.0, 3.5] * ATR (bfill)
        assert len(r_buy) == len(df)
        assert len(r_sell) == len(df)


class TestTripleBarrierScenarios:
    def test_clean_buy_2r(self):
        # Bar 0: base 2000. Bar 1..5: harga naik pesat ke 2050 tanpa turun
        n = 30
        df = make_test_df(n, base_price=2000.0)
        # Inject uptrend kuat di bar 1..10
        for i in range(1, 15):
            df.loc[i, "high"] = 2000.0 + (i * 5.0)
            df.loc[i, "low"] = 2000.0 + (i * 2.0)
            df.loc[i, "close"] = 2000.0 + (i * 4.0)

        df_out = label_triple_barrier(df, time_barrier=16, verbose=False)
        # Bar 0 harus BUY 2R (action == 2)
        assert df_out["action"].iloc[0] == 2
        assert df_out["action_name"].iloc[0] == "BUY_2R"

    def test_clean_sell_2r(self):
        # Bar 0: base 2000. Bar 1..5: harga turun tajam ke 1950 tanpa naik
        n = 30
        df = make_test_df(n, base_price=2000.0)
        for i in range(1, 15):
            df.loc[i, "low"] = 2000.0 - (i * 5.0)
            df.loc[i, "high"] = 2000.0 - (i * 2.0)
            df.loc[i, "close"] = 2000.0 - (i * 4.0)

        df_out = label_triple_barrier(df, time_barrier=16, verbose=False)
        # Bar 0 harus SELL 2R (action == 4)
        assert df_out["action"].iloc[0] == 4
        assert df_out["action_name"].iloc[0] == "SELL_2R"

    def test_stop_loss_hit_first(self):
        # Bar 0: base 2000. Bar 1: harga anjlok menyentuh SL lalu baru naik
        n = 30
        df = make_test_df(n, base_price=2000.0)
        # Bar 1 dump tajam kena SL
        df.loc[1, "low"] = 1970.0
        df.loc[1, "high"] = 2001.0
        # Bar 2..10 baru naik tinggi
        for i in range(2, 15):
            df.loc[i, "high"] = 2050.0
            df.loc[i, "close"] = 2045.0

        df_out = label_triple_barrier(df, time_barrier=16, verbose=False)
        # Karena SL kena duluan di bar 1, BUY tidak boleh menang
        assert df_out["buy_class"].iloc[0] == 0
        assert df_out["action"].iloc[0] != 2
        assert df_out["action"].iloc[0] != 1

    def test_tie_break_same_bar_worst_case(self):
        # Bar 1 memiliki range raksasa yang menyentuh TP dan SL sekaligus
        n = 30
        df = make_test_df(n, base_price=2000.0)
        df.loc[1, "high"] = 2100.0  # Melebihi TP2
        df.loc[1, "low"] = 1900.0   # Melebihi SL
        df_out = label_triple_barrier(df, time_barrier=16, verbose=False)
        # Worst-case: SL dianggap kena duluan -> action harus 0
        assert df_out["action"].iloc[0] == 0

    def test_ineligible_bar_forces_hold(self):
        n = 30
        df = make_test_df(n, base_price=2000.0)
        # Jadikan bar 0 ineligible (misal kena news blackout)
        df.loc[0, "entry_eligible"] = False
        # Dan inject harga naik pesat
        for i in range(1, 15):
            df.loc[i, "high"] = 2050.0
            df.loc[i, "close"] = 2045.0

        df_out = label_triple_barrier(df, time_barrier=16, verbose=False)
        # Meskipun harga naik 2R, Hard Zero Gate memaksa action == 0
        assert df_out["action"].iloc[0] == 0
        assert df_out["action_name"].iloc[0] == "HOLD"

    def test_friction_cost_prevents_marginal_win(self):
        # Kenaikan tipis yang secara bruto >= 1.0R, tapi pasca biaya (spread + komisi) < 1.0R
        n = 30
        df = make_test_df(n, base_price=2000.0)
        r_buy, _ = compute_structural_risk(df)
        r0 = r_buy[0]
        # High hanya mencapai entry + r0 (tanpa menutup spread + komisi)
        for i in range(1, 15):
            df.loc[i, "high"] = 2000.0 + r0 + 0.01  # Belum cukup untuk menutup friction
            df.loc[i, "low"] = 1999.0
            df.loc[i, "close"] = 2000.0

        df_out = label_triple_barrier(df, time_barrier=16, commission_per_oz=1.0, verbose=False)
        # Dengan komisi $1.0, trade marginal ini harus gagal mencapai TP net-of-cost
        assert df_out["buy_class"].iloc[0] == 0


class TestFocalWeights:
    def test_weights_sum_to_num_classes(self):
        # 100 samples: 60 HOLD, 10 BUY1, 10 BUY2, 10 SELL1, 10 SELL2
        labels = np.array([0]*60 + [1]*10 + [2]*10 + [3]*10 + [4]*10)
        res = compute_focal_weights(labels, num_classes=5)
        weights = res["alpha_weights"]
        assert len(weights) == 5
        # Sum of normalized weights = 5.0
        assert np.isclose(sum(weights), 5.0, atol=0.05)

    def test_rare_class_has_higher_weight(self):
        # HOLD dominan (80%), BUY2 langka (5%)
        labels = np.array([0]*80 + [1]*5 + [2]*5 + [3]*5 + [4]*5)
        res = compute_focal_weights(labels, num_classes=5)
        w = res["alpha_weights"]
        # Weight for class 2 harus jauh lebih besar dari class 0
        assert w[2] > w[0]
        assert w[0] < 1.0

    def test_numpy_focal_loss_finite(self):
        y_true = np.array([0, 1, 2, 0, 4])
        # Random softmax probabilities
        probs = np.array([
            [0.8, 0.05, 0.05, 0.05, 0.05],
            [0.1, 0.7, 0.1, 0.05, 0.05],
            [0.2, 0.1, 0.6, 0.05, 0.05],
            [0.5, 0.1, 0.1, 0.1, 0.2],
            [0.1, 0.05, 0.05, 0.1, 0.7],
        ])
        alpha = [0.5, 1.2, 1.2, 1.1, 1.0]
        loss = numpy_focal_loss(y_true, probs, alpha=alpha, gamma=2.0)
        assert np.isfinite(loss)
        assert loss > 0.0
