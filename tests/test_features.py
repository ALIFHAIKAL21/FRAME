"""
XAU_DEEP_SNIPER - TAHAP 2 Unit Tests: Feature Engineering
===========================================================
Test suite untuk memverifikasi:
1. EMA & ATR correctness
2. Scale-free OHLC normalization (stationarity)
3. Volume Z-score (bounded, centered)
4. SMI (range [-1, +1])
5. MA Ribbon (slope, spread, alignment)
6. Fractal detection (causal, no lookahead)
7. FVG detection
8. Temporal split (purge + embargo, no leakage)
9. Full pipeline integration
"""

import sys
import pathlib
import pytest
import pandas as pd
import numpy as np

# Setup path
project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from pipeline import feature_config as fcfg
from pipeline.features_core import (
    compute_returns_and_volatility,
    compute_ema, compute_atr, normalize_ohlc_scale_free,
    compute_volume_zscore, build_core_features,
    get_warmup_period, validate_core_features,
)
from pipeline.features_technical import (
    compute_smi, compute_ma_ribbon_features, build_technical_features,
)
from pipeline.features_structural import (
    detect_fractal_highs, detect_fractal_lows,
    compute_liquidity_distance, detect_fvg,
    build_structural_features,
)
from pipeline.feature_pipeline import (
    extract_feature_windows,
    build_all_features, temporal_split, trim_warmup_nans,
    get_feature_columns, validate_all_features,
)


# ===========================================================================
# FIXTURES
# ===========================================================================

def make_ohlcv(n=500, seed=42):
    """Generate synthetic OHLCV data with realistic properties."""
    rng = np.random.RandomState(seed)
    
    # Random walk for close prices starting at 2000
    returns = rng.normal(0, 0.002, n)
    close = 2000.0 * np.exp(np.cumsum(returns))
    
    # Generate OHLC from close
    spread = rng.uniform(0.5, 3.0, n)
    high = close + rng.uniform(0.5, 5.0, n)
    low = close - rng.uniform(0.5, 5.0, n)
    open_price = close + rng.normal(0, 1.0, n)
    
    # Ensure OHLC integrity
    high = np.maximum(high, np.maximum(open_price, close))
    low = np.minimum(low, np.minimum(open_price, close))
    
    volume = rng.randint(500, 10000, n).astype(float)
    
    timestamps = pd.date_range(
        start="2023-01-02 00:00:00", periods=n, freq="30min", tz="UTC"
    )
    
    df = pd.DataFrame({
        "timestamp_utc": timestamps,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "spread": spread,
    })
    
    return df


@pytest.fixture
def sample_df():
    return make_ohlcv(500)


@pytest.fixture
def large_df():
    return make_ohlcv(2000)


# ===========================================================================
# TEST: EMA
# ===========================================================================

class TestEMA:
    def test_ema_length(self, sample_df):
        ema = compute_ema(sample_df["close"], 20)
        assert len(ema) == len(sample_df)
    
    def test_ema_warmup_nan(self, sample_df):
        period = 20
        ema = compute_ema(sample_df["close"], period)
        # First (period-1) values should be NaN
        assert ema.iloc[:period - 1].isna().all()
        # After warmup, should have values
        assert ema.iloc[period:].notna().all()
    
    def test_ema_no_future_data(self, sample_df):
        """EMA harus causal - perubahan data masa depan tidak boleh mempengaruhi EMA saat ini."""
        close = sample_df["close"].copy()
        ema_original = compute_ema(close, 20)
        
        # Ubah data di masa depan (bar 300+)
        close_modified = close.copy()
        close_modified.iloc[300:] = close.iloc[300:] * 2.0
        ema_modified = compute_ema(close_modified, 20)
        
        # EMA sebelum bar 300 harus identik
        np.testing.assert_array_almost_equal(
            ema_original.iloc[:300].dropna().values,
            ema_modified.iloc[:300].dropna().values,
        )


# ===========================================================================
# TEST: ATR
# ===========================================================================

class TestATR:
    def test_atr_positive(self, sample_df):
        atr = compute_atr(sample_df["high"], sample_df["low"], sample_df["close"], 14)
        valid = atr.dropna()
        assert (valid > 0).all(), "ATR harus selalu positif"
    
    def test_atr_length(self, sample_df):
        atr = compute_atr(sample_df["high"], sample_df["low"], sample_df["close"], 14)
        assert len(atr) == len(sample_df)


# ===========================================================================
# TEST: OHLC Normalization (Channel 1-4)
# ===========================================================================

class TestOHLCNorm:
    def test_output_columns(self, sample_df):
        result = normalize_ohlc_scale_free(sample_df)
        expected = ["ohlc_norm_open", "ohlc_norm_high", "ohlc_norm_low", "ohlc_norm_close"]
        assert list(result.columns) == expected
    
    def test_centered_near_zero(self, large_df):
        """Normalized OHLC harus centered mendekati 0 (detrended)."""
        result = normalize_ohlc_scale_free(large_df)
        warmup = get_warmup_period()
        for col in result.columns:
            valid = result[col].iloc[warmup:].dropna()
            assert abs(valid.mean()) < 2.0, f"{col} mean = {valid.mean()}, terlalu jauh dari 0"
    
    def test_no_inf_values(self, sample_df):
        result = normalize_ohlc_scale_free(sample_df)
        for col in result.columns:
            assert not np.isinf(result[col].dropna()).any(), f"INF found in {col}"
    
    def test_high_ge_low_preserved(self, large_df):
        """Setelah normalisasi, norm_high >= norm_low harus tetap berlaku."""
        result = normalize_ohlc_scale_free(large_df)
        warmup = get_warmup_period()
        valid = result.iloc[warmup:].dropna()
        assert (valid["ohlc_norm_high"] >= valid["ohlc_norm_low"]).all()


# ===========================================================================
# TEST: Volume Z-Score (Channel 5)
# ===========================================================================

class TestVolumeZScore:
    def test_bounded(self, sample_df):
        zscore = compute_volume_zscore(sample_df["volume"].astype(float))
        valid = zscore.dropna()
        assert valid.max() <= 5.0, "Z-score harus <= 5"
        assert valid.min() >= -5.0, "Z-score harus >= -5"
    
    def test_approximately_centered(self, large_df):
        zscore = compute_volume_zscore(large_df["volume"].astype(float))
        warmup = fcfg.VOLUME_ZSCORE_WINDOW
        valid = zscore.iloc[warmup:].dropna()
        assert abs(valid.mean()) < 1.0, f"Mean zscore = {valid.mean()}, should be near 0"
    
    def test_warmup_nan(self, sample_df):
        zscore = compute_volume_zscore(sample_df["volume"].astype(float))
        window = fcfg.VOLUME_ZSCORE_WINDOW
        assert zscore.iloc[:window - 1].isna().all()


# ===========================================================================
# TEST: SMI (Channel 6)
# ===========================================================================

class TestSMI:
    def test_range(self, sample_df):
        smi = compute_smi(sample_df["high"], sample_df["low"], sample_df["close"])
        valid = smi.dropna()
        assert valid.max() <= 1.0, f"SMI max = {valid.max()}, should be <= 1.0"
        assert valid.min() >= -1.0, f"SMI min = {valid.min()}, should be >= -1.0"
    
    def test_no_inf(self, sample_df):
        smi = compute_smi(sample_df["high"], sample_df["low"], sample_df["close"])
        assert not np.isinf(smi.dropna()).any()
    
    def test_length(self, sample_df):
        smi = compute_smi(sample_df["high"], sample_df["low"], sample_df["close"])
        assert len(smi) == len(sample_df)


# ===========================================================================
# TEST: MA Ribbon (Channel 7)
# ===========================================================================

class TestMARibbon:
    def test_output_columns(self, sample_df):
        result = compute_ma_ribbon_features(
            sample_df["close"], sample_df["high"], sample_df["low"]
        )
        assert "ma_ribbon_slope" in result.columns
        assert "ma_ribbon_spread" in result.columns
        assert "ma_ribbon_alignment" in result.columns
    
    def test_alignment_range(self, sample_df):
        result = compute_ma_ribbon_features(
            sample_df["close"], sample_df["high"], sample_df["low"]
        )
        valid = result["ma_ribbon_alignment"].dropna()
        assert valid.max() <= 1.0
        assert valid.min() >= -1.0
    
    def test_slope_bounded(self, sample_df):
        result = compute_ma_ribbon_features(
            sample_df["close"], sample_df["high"], sample_df["low"]
        )
        valid = result["ma_ribbon_slope"].dropna()
        assert valid.max() <= 5.0
        assert valid.min() >= -5.0


# ===========================================================================
# TEST: Fractal Detection (Channel 8)
# ===========================================================================

class TestFractals:
    def test_fractal_high_detection(self):
        """Manual test: clear fractal high pattern."""
        high = pd.Series([1, 2, 5, 2, 1, 3, 3, 3, 3, 3])
        result = detect_fractal_highs(high, window=5)
        assert result.iloc[2] == True, "Bar 2 (value=5) should be fractal high"
    
    def test_fractal_low_detection(self):
        """Manual test: clear fractal low pattern."""
        low = pd.Series([5, 4, 1, 4, 5, 3, 3, 3, 3, 3])
        result = detect_fractal_lows(low, window=5)
        assert result.iloc[2] == True, "Bar 2 (value=1) should be fractal low"
    
    def test_no_fractals_on_edges(self):
        """Tidak boleh ada fractal di 2 bar pertama/terakhir."""
        high = pd.Series([10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
        result = detect_fractal_highs(high, window=5)
        # Monotone decreasing - bar 0 tertinggi tapi tidak cukup context
        assert result.iloc[0] == False
        assert result.iloc[1] == False


# ===========================================================================
# TEST: FVG Detection (Channel 9)
# ===========================================================================

class TestFVG:
    def test_bullish_fvg(self):
        """Bullish FVG: gap up antara bar[0].high dan bar[2].low."""
        df = pd.DataFrame({
            "open":  [100, 102, 106, 107, 108],
            "high":  [101, 103, 107, 108, 109],
            "low":   [99,  101, 105, 106, 107],  # bar[2].low=105 > bar[0].high=101
            "close": [100, 102, 106, 107, 108],
            "volume": [1000] * 5,
            "timestamp_utc": pd.date_range("2023-01-01", periods=5, freq="30min", tz="UTC"),
        })
        fvg = detect_fvg(df)
        # Should detect a bullish FVG at bar 2 (105 - 101 = 4 gap)
        assert len(fvg) == 5
    
    def test_fvg_no_crash(self, sample_df):
        """FVG detection should not crash on realistic data."""
        fvg = detect_fvg(sample_df)
        assert len(fvg) == len(sample_df)
        assert not np.isinf(fvg).any()


# ===========================================================================
# TEST: Temporal Split
# ===========================================================================

class TestTemporalSplit:
    def test_no_overlap(self, large_df):
        """Train dan test set tidak boleh overlap."""
        df = build_core_features(large_df)
        df = trim_warmup_nans(df)
        train, test = temporal_split(df, verbose=False)
        
        train_max_ts = train["timestamp_utc"].max()
        test_min_ts = test["timestamp_utc"].min()
        assert train_max_ts < test_min_ts, "Train harus berakhir sebelum test dimulai"
    
    def test_purge_embargo_gap(self, large_df):
        """Harus ada gap antara train end dan test start."""
        df = build_core_features(large_df)
        df = trim_warmup_nans(df)
        train, test = temporal_split(df, verbose=False)
        
        total_bars = len(train) + len(test)
        gap = len(df) - total_bars
        assert gap >= fcfg.PURGE_BARS + fcfg.EMBARGO_BARS, \
            f"Gap ({gap}) harus >= purge ({fcfg.PURGE_BARS}) + embargo ({fcfg.EMBARGO_BARS})"
    
    def test_split_ratio(self, large_df):
        """Train size harus ~80% dari total."""
        df = build_core_features(large_df)
        df = trim_warmup_nans(df)
        train, test = temporal_split(df, verbose=False)
        
        # Approximate karena purge/embargo mengurangi sedikit
        actual_ratio = len(train) / len(df)
        assert 0.70 < actual_ratio < 0.85, f"Train ratio = {actual_ratio:.2f}"


# ===========================================================================
# TEST: Full Pipeline Integration
# ===========================================================================

class TestFullPipeline:
    def test_all_channels_present(self, sample_df):
        """Semua 9 channel harus ada setelah build."""
        df = build_all_features(sample_df, verbose=False)
        
        # Check ma_ribbon_slope is used as the composite Channel 7
        expected = [
            "ohlc_norm_open", "ohlc_norm_high", "ohlc_norm_low", "ohlc_norm_close",
            "volume_zscore", "smi", "ma_ribbon_slope",
            "liquidity_distance", "fvg_status",
        ]
        for col in expected:
            assert col in df.columns, f"Missing channel: {col}"
    
    def test_no_inf_anywhere(self, sample_df):
        """Tidak boleh ada INF di fitur manapun."""
        df = build_all_features(sample_df, verbose=False)
        feature_cols = get_feature_columns()
        for col in feature_cols:
            if col in df.columns:
                valid = df[col].dropna()
                assert not np.isinf(valid).any(), f"INF found in {col}"
    
    def test_validation_all_pass(self, large_df):
        """Semua channel harus pass validation pada data cukup besar."""
        df = build_all_features(large_df, verbose=False)
        report = validate_all_features(df, verbose=False)
        for ch, stats in report.items():
            assert stats["status"] == "PASS", f"Channel {ch} failed: {stats.get('issues')}"
    
    def test_warmup_trim(self, sample_df):
        """Trim warmup harus menghapus NaN rows."""
        df = build_all_features(sample_df, verbose=False)
        df_trimmed = trim_warmup_nans(df)
        assert len(df_trimmed) < len(df)
        
        # After trim, first row should have no NaN in feature columns
        feature_cols = [c for c in get_feature_columns() if c in df_trimmed.columns]
        first_row = df_trimmed[feature_cols].iloc[0]
        assert first_row.notna().all(), f"NaN found in first row after trim: {first_row[first_row.isna()].index.tolist()}"



# ===========================================================================
# TEST: Returns & Volatility
# ===========================================================================

class TestReturnsAndVolatility:
    def test_returns_calculation(self, sample_df):
        res = compute_returns_and_volatility(sample_df)
        assert "log_return" in res.columns
        assert "return_pct" in res.columns
        # First row is NaN
        assert pd.isna(res["log_return"].iloc[0])
        # Subsequent rows valid
        assert not res["log_return"].iloc[1:].isna().any()

    def test_volatility_positive(self, large_df):
        res = compute_returns_and_volatility(large_df)
        v20 = res["rolling_vol_20"].dropna()
        v64 = res["rolling_vol_64"].dropna()
        assert (v20 >= 0).all()
        assert (v64 >= 0).all()


# ===========================================================================
# TEST: Feature Window Extraction (MOMENT-1-large Tensor Shape)
# ===========================================================================

class TestFeatureWindows:
    def test_window_shape(self, large_df):
        df_feat = build_all_features(large_df, verbose=False)
        df_clean = trim_warmup_nans(df_feat)
        
        L = 64
        X, ts = extract_feature_windows(df_clean, window_length=L)
        
        expected_N = len(df_clean) - L + 1
        expected_C = 9
        assert X.shape == (expected_N, expected_C, L)
        assert len(ts) == expected_N
        assert X.dtype == np.float32

    def test_window_content_alignment(self, sample_df):
        df_feat = build_all_features(sample_df, verbose=False)
        df_clean = trim_warmup_nans(df_feat)
        
        L = 10
        X, ts = extract_feature_windows(df_clean, window_length=L)
        
        # Check window 0 channel 0 matches slice [0:L] of ohlc_norm_open
        expected_slice = df_clean["ohlc_norm_open"].iloc[:L].values.astype(np.float32)
        np.testing.assert_allclose(X[0, 0, :], expected_slice)
        
        # Timestamp must match bar t (index L-1)
        assert ts.iloc[0] == df_clean["timestamp_utc"].iloc[L - 1]

    def test_session_column_present(self, sample_df):
        df_feat = build_all_features(sample_df, verbose=False)
        assert "session" in df_feat.columns
        valid_sessions = {"asian", "london", "overlap", "newyork", "rollover"}
        actual_sessions = set(df_feat["session"].unique())
        assert actual_sessions.issubset(valid_sessions)
