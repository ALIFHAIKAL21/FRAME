"""
XAU_DEEP_SNIPER — Unit Tests: Data Cleaning
=============================================
Menguji deteksi flat candle, bad tick, weekend removal,
dan rollover quarantine menggunakan data sintetis terkontrol.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.pipeline.clean import (
    remove_weekend_bars,
    detect_flat_candles,
    detect_consecutive_flats,
    detect_bad_ticks,
    clamp_bad_ticks,
    run_full_cleaning_pipeline,
)
from src.pipeline import config


def make_bars(n=100, start_date="2023-06-02", include_weekends=False, seed=42):
    """Helper: generate DataFrame sintetis dengan OHLCV realistis."""
    np.random.seed(seed)
    start = pd.Timestamp(start_date + " 00:00:00", tz="UTC")
    timestamps = pd.date_range(start, periods=n * 2, freq="30min")

    if not include_weekends:
        timestamps = timestamps[timestamps.weekday < 5][:n]
    else:
        timestamps = timestamps[:n]

    n_actual = len(timestamps)
    base_price = 1950.0
    noise = np.cumsum(np.random.randn(n_actual) * 0.3)
    prices = base_price + noise

    df = pd.DataFrame({
        "timestamp_utc": timestamps,
        "open": np.round(prices, 2),
        "high": np.round(prices + np.abs(np.random.randn(n_actual)) * 3 + 0.5, 2),
        "low": np.round(prices - np.abs(np.random.randn(n_actual)) * 3 - 0.5, 2),
        "close": np.round(prices + np.random.randn(n_actual) * 0.5, 2),
        "volume": np.random.randint(200, 5000, n_actual),
        "spread": np.round(2.5 + np.random.rand(n_actual), 1),
    })
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"] = df[["open", "close", "low"]].min(axis=1)
    return df


class TestWeekendRemoval:
    """Test weekend bar removal."""

    def test_weekday_data_unchanged(self):
        """DataFrame tanpa weekend harus tetap utuh."""
        df = make_bars(50, include_weekends=False)
        cleaned, removed = remove_weekend_bars(df)
        assert removed == 0
        assert len(cleaned) == len(df)

    def test_weekend_bars_removed(self):
        """Weekend bars harus dihapus."""
        df = make_bars(200, include_weekends=True)
        original_len = len(df)
        cleaned, removed = remove_weekend_bars(df)
        assert removed > 0
        assert len(cleaned) == original_len - removed
        # Verifikasi tidak ada weekend di hasil
        assert cleaned["timestamp_utc"].dt.weekday.isin([5, 6]).sum() == 0

    def test_is_weekend_column_all_false_after_removal(self):
        """Setelah removal, kolom is_weekend harus semua False."""
        df = make_bars(200, include_weekends=True)
        cleaned, _ = remove_weekend_bars(df)
        assert "is_weekend" in cleaned.columns
        assert cleaned["is_weekend"].sum() == 0


class TestFlatCandleDetection:
    """Test flat candle detection."""

    def test_no_flat_in_normal_data(self):
        """Data normal tidak boleh ada flat candle."""
        df = make_bars(100)
        flags = detect_flat_candles(df)
        assert flags.sum() == 0  # Normal data tidak punya flat

    def test_inject_flat_candle(self):
        """Flat candle yang di-inject harus terdeteksi."""
        df = make_bars(100)
        # Inject flat candle: high == low, volume == 0
        idx = 50
        df.at[idx, "high"] = 1950.00
        df.at[idx, "low"] = 1950.00
        df.at[idx, "open"] = 1950.00
        df.at[idx, "close"] = 1950.00
        df.at[idx, "volume"] = 0

        flags = detect_flat_candles(df)
        assert flags.iloc[idx] is True or flags.iloc[idx] == True
        assert flags.sum() >= 1

    def test_flat_but_with_volume_not_flagged(self):
        """Bar dengan range kecil tapi volume > 0 tidak boleh di-flag."""
        df = make_bars(100)
        idx = 50
        df.at[idx, "high"] = 1950.005
        df.at[idx, "low"] = 1950.000
        df.at[idx, "volume"] = 500  # Volume ada

        flags = detect_flat_candles(df)
        assert flags.iloc[idx] == False


class TestConsecutiveFlats:
    """Test consecutive flat detection."""

    def test_short_run_detected(self):
        """Run pendek (< threshold) tetap terdeteksi jumlahnya."""
        flags = pd.Series([False, False, True, True, False, False])
        runs = detect_consecutive_flats(flags)
        assert runs.iloc[2] == 2
        assert runs.iloc[3] == 2

    def test_long_run_exceeds_threshold(self):
        """Run panjang >= threshold harus terdeteksi."""
        n_flat = config.FLAT_CONSECUTIVE_THRESHOLD + 2
        flags = pd.Series([False] * 5 + [True] * n_flat + [False] * 5)
        runs = detect_consecutive_flats(flags)
        assert runs.max() == n_flat
        assert (runs >= config.FLAT_CONSECUTIVE_THRESHOLD).sum() == n_flat


class TestBadTickDetection:
    """Test bad tick / spurious spike detection."""

    def test_no_bad_ticks_in_normal_data(self):
        """Data normal tidak boleh ada bad tick."""
        df = make_bars(100)
        flags = detect_bad_ticks(df)
        assert flags.sum() == 0

    def test_inject_spike_detected(self):
        """Spike besar dengan volume rendah harus terdeteksi."""
        df = make_bars(100)
        idx = 60
        # Inject spike: range sangat besar, volume sangat rendah
        df.at[idx, "high"] = df.at[idx, "close"] + 100  # $100 spike (absurd)
        df.at[idx, "low"] = df.at[idx, "close"] - 100
        df.at[idx, "volume"] = 1  # Volume minimal

        flags = detect_bad_ticks(df)
        assert flags.iloc[idx] == True

    def test_large_range_with_high_volume_not_flagged(self):
        """Range besar tapi volume tinggi = legitimate move, tidak di-flag."""
        df = make_bars(100)
        idx = 60
        df.at[idx, "high"] = df.at[idx, "close"] + 50
        df.at[idx, "low"] = df.at[idx, "close"] - 50
        df.at[idx, "volume"] = 50000  # Volume sangat tinggi

        flags = detect_bad_ticks(df)
        assert flags.iloc[idx] == False


class TestBadTickClamping:
    """Test bad tick clamping."""

    def test_clamping_reduces_extreme(self):
        """Clamping harus mengurangi nilai ekstrem."""
        df = make_bars(100)
        idx = 60
        original_high = df.at[idx, "high"]
        df.at[idx, "high"] = 5000.0  # Absurd spike
        df.at[idx, "volume"] = 1

        flags = detect_bad_ticks(df)
        if flags.iloc[idx]:
            clamped_df = clamp_bad_ticks(df, flags)
            assert clamped_df.at[idx, "high"] < 5000.0
            # High harus masih >= close setelah clamping
            assert clamped_df.at[idx, "high"] >= clamped_df.at[idx, "close"]

    def test_ohlc_integrity_after_clamp(self):
        """Setelah clamping, OHLC integrity harus terjaga."""
        df = make_bars(100)
        idx = 60
        df.at[idx, "high"] = 5000.0
        df.at[idx, "low"] = 100.0
        df.at[idx, "volume"] = 1

        flags = detect_bad_ticks(df)
        clamped_df = clamp_bad_ticks(df, flags)

        # Integrity: High >= Open, Close dan Low <= Open, Close
        assert clamped_df.at[idx, "high"] >= clamped_df.at[idx, "open"]
        assert clamped_df.at[idx, "high"] >= clamped_df.at[idx, "close"]
        assert clamped_df.at[idx, "low"] <= clamped_df.at[idx, "open"]
        assert clamped_df.at[idx, "low"] <= clamped_df.at[idx, "close"]


class TestFullCleaningPipeline:
    """Test end-to-end cleaning pipeline."""

    def test_pipeline_adds_all_flag_columns(self):
        """Pipeline harus menambahkan semua flag columns."""
        df = make_bars(100, include_weekends=True)
        cleaned = run_full_cleaning_pipeline(df)
        for col in config.FLAG_COLUMNS:
            assert col in cleaned.columns, f"Flag column {col} tidak ditemukan"

    def test_entry_eligible_logic(self):
        """entry_eligible harus False jika ada flag aktif."""
        df = make_bars(100)
        cleaned = run_full_cleaning_pipeline(df)
        # Cek: jika ada flag True, entry_eligible harus False
        for idx in cleaned.index:
            has_flag = (
                cleaned.at[idx, "is_rollover_quarantine"]
                or cleaned.at[idx, "is_flat_candle"]
                or cleaned.at[idx, "is_bad_tick"]
                or cleaned.at[idx, "is_news_blackout"]
            )
            if has_flag:
                assert cleaned.at[idx, "entry_eligible"] == False
            else:
                assert cleaned.at[idx, "entry_eligible"] == True

    def test_no_weekend_bars_in_output(self):
        """Output tidak boleh mengandung weekend bars."""
        df = make_bars(200, include_weekends=True)
        cleaned = run_full_cleaning_pipeline(df)
        assert cleaned["timestamp_utc"].dt.weekday.isin([5, 6]).sum() == 0
