"""
XAU_DEEP_SNIPER — Data Cleaning Module
=======================================
Implementasi 4 algoritma deteksi anomali:
1. Weekend & Holiday Filter
2. Flat Candle Detection
3. Bad Tick / Spurious Spike Detection & Clamping
4. Aggregasi flag -> entry_eligible

Prinsip desain:
- TIDAK ADA bar yang dihapus dari dataset (kecuali weekend).
  Bar anomali di-flag dan di-clamp, tapi tetap dipertahankan untuk
  kontinuitas teknikal time-series.
- Weekend bars dihapus karena pasar memang tutup (bukan anomali,
  tapi data invalid by definition).
"""

import pandas as pd
import numpy as np
from typing import Tuple

from . import config
from .dst_harmonizer import flag_rollover_quarantine
from .news_blackout import flag_news_blackout, get_blackout_stats


def remove_weekend_bars(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Menghapus bar yang jatuh pada hari Sabtu dan Minggu.
    XAU/USD market tutup pada akhir pekan.

    Returns
    -------
    (DataFrame, int)
        DataFrame tanpa weekend bars, dan jumlah bar yang dihapus.
    """
    weekday = df["timestamp_utc"].dt.weekday
    is_weekend = weekday.isin(config.WEEKEND_DAYS)

    removed_count = is_weekend.sum()
    df_clean = df[~is_weekend].copy()
    df_clean["is_weekend"] = False  # Semua bar yang tersisa bukan weekend

    return df_clean, removed_count


def detect_flat_candles(df: pd.DataFrame) -> pd.Series:
    """
    Mendeteksi flat candles (pasar mati / data corruption).

    Definisi flat:
        |high - low| < FLAT_EPSILON DAN volume == 0

    Bar flat isolated (1-2 berturutan) ditandai 'thin_liquidity'.
    Bar flat berturutan > FLAT_CONSECUTIVE_THRESHOLD ditandai 'suspected_gap'.

    Returns
    -------
    pd.Series
        Boolean series, True = flat candle.
    """
    bar_range = (df["high"] - df["low"]).abs()
    is_flat = (bar_range < config.FLAT_EPSILON) & (df["volume"] == 0)
    return is_flat


def detect_consecutive_flats(is_flat: pd.Series) -> pd.Series:
    """
    Mendeteksi run berturutan dari flat candles.

    Returns
    -------
    pd.Series
        Integer series: panjang run flat berturutan untuk setiap bar flat.
        Bar non-flat mendapat nilai 0.
    """
    # Gunakan cumsum trick untuk grouping runs
    groups = (~is_flat).cumsum()
    run_lengths = is_flat.groupby(groups).transform("sum")
    return (run_lengths * is_flat).astype(int)


def detect_bad_ticks(df: pd.DataFrame) -> pd.Series:
    """
    Mendeteksi bad ticks / spurious spike berdasarkan rasio range terhadap ATR.

    Aturan:
        range_t > BAD_TICK_ATR_MULTIPLIER * ATR(BAD_TICK_ATR_PERIOD)
        DAN volume_t < median(volume, BAD_TICK_VOLUME_PERIOD)

    ATR dihitung dari bar-bar SEBELUMNYA saja (tanpa bar saat ini)
    untuk mencegah lookahead bias.

    Returns
    -------
    pd.Series
        Boolean series, True = suspected bad tick.
    """
    period = config.BAD_TICK_ATR_PERIOD
    multiplier = config.BAD_TICK_ATR_MULTIPLIER
    vol_period = config.BAD_TICK_VOLUME_PERIOD

    # True Range (TR) untuk ATR
    high_low = df["high"] - df["low"]
    high_prev_close = (df["high"] - df["close"].shift(1)).abs()
    low_prev_close = (df["low"] - df["close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)

    # ATR: rolling mean dari PREVIOUS bars (shift 1 untuk exclude current bar)
    atr = true_range.shift(1).rolling(window=period, min_periods=period).mean()

    # Current bar range
    bar_range = df["high"] - df["low"]

    # Volume median dari previous bars
    vol_median = df["volume"].shift(1).rolling(window=vol_period, min_periods=1).median()

    # Bad tick condition
    is_spike = bar_range > (multiplier * atr)
    is_low_volume = df["volume"] < vol_median
    is_bad_tick = is_spike & is_low_volume

    # Baris pertama tidak bisa dievaluasi (belum ada ATR)
    is_bad_tick.iloc[:period] = False

    return is_bad_tick


def clamp_bad_ticks(df: pd.DataFrame, is_bad_tick: pd.Series) -> pd.DataFrame:
    """
    Clamp high/low dari bar bad tick ke percentile 99.5% dari window terdekat.
    TIDAK menghapus bar — hanya mengkoreksi outlier extremes.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan kolom OHLC.
    is_bad_tick : pd.Series
        Boolean mask dari detect_bad_ticks().

    Returns
    -------
    pd.DataFrame
        DataFrame dengan high/low yang sudah di-clamp untuk bad ticks.
    """
    df = df.copy()
    window = config.BAD_TICK_CLAMP_WINDOW
    pct = config.BAD_TICK_CLAMP_PERCENTILE

    for idx in df[is_bad_tick].index:
        # Ambil window sekitar bar ini (exclude bar itu sendiri)
        start = max(0, idx - window)
        end = min(len(df), idx + window)
        neighborhood = df.iloc[start:end]
        neighborhood = neighborhood.drop(idx, errors="ignore")

        if len(neighborhood) < 5:
            continue  # Tidak cukup data untuk clamping yang reliable

        high_cap = neighborhood["high"].quantile(pct)
        low_floor = neighborhood["low"].quantile(1 - pct)

        df.at[idx, "high"] = min(df.at[idx, "high"], high_cap)
        df.at[idx, "low"] = max(df.at[idx, "low"], low_floor)

        # Pastikan OHLC integrity setelah clamping
        df.at[idx, "open"] = np.clip(df.at[idx, "open"], df.at[idx, "low"], df.at[idx, "high"])
        df.at[idx, "close"] = np.clip(df.at[idx, "close"], df.at[idx, "low"], df.at[idx, "high"])

    return df


def run_full_cleaning_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Menjalankan seluruh pipeline cleaning secara berurutan.

    Urutan operasi:
    1. Hapus weekend bars
    2. Flag rollover quarantine (DST-aware)
    3. Deteksi flat candles
    4. Deteksi dan clamp bad ticks
    5. Hitung entry_eligible (semua flag False)
    6. Placeholder news_blackout (False, akan diisi di TAHAP 2/3)

    Returns
    -------
    pd.DataFrame
        DataFrame bersih dengan semua flag columns ditambahkan.
    """
    # Step 1: Hapus weekend
    df, weekend_removed = remove_weekend_bars(df)
    print(f"[CLEAN] Weekend bars dihapus: {weekend_removed}")

    # Step 2: Flag rollover quarantine
    df["is_rollover_quarantine"] = flag_rollover_quarantine(df)
    rollover_count = df["is_rollover_quarantine"].sum()
    print(f"[CLEAN] Rollover quarantine bars: {rollover_count}")

    # Step 3: Flat candle detection
    df["is_flat_candle"] = detect_flat_candles(df)
    flat_count = df["is_flat_candle"].sum()
    consecutive = detect_consecutive_flats(df["is_flat_candle"])
    suspected_gaps = (consecutive >= config.FLAT_CONSECUTIVE_THRESHOLD).sum()
    print(f"[CLEAN] Flat candles: {flat_count} ({suspected_gaps} suspected data gaps)")

    # Step 4: Bad tick detection & clamping
    df["is_bad_tick"] = detect_bad_ticks(df)
    bad_tick_count = df["is_bad_tick"].sum()
    if bad_tick_count > 0:
        df = clamp_bad_ticks(df, df["is_bad_tick"])
    print(f"[CLEAN] Bad ticks detected & clamped: {bad_tick_count}")

    # Step 5: News blackout — flag ±30 menit sekitar NFP, CPI, FOMC, PPI, GDP
    try:
        df["is_news_blackout"] = flag_news_blackout(df)
        stats = get_blackout_stats(df)
        print(f"[CLEAN] News blackout bars: {stats['blackout_bars']} ({stats['blackout_pct']}%)")
    except FileNotFoundError as e:
        print(f"[CLEAN] WARNING: {e}")
        print("[CLEAN] News blackout dinonaktifkan — semua bar eligible.")
        df["is_news_blackout"] = False

    # Step 6: Hitung entry_eligible
    # Entry eligible = TIDAK ada flag anomali aktif
    df["entry_eligible"] = ~(
        df["is_rollover_quarantine"]
        | df["is_flat_candle"]
        | df["is_bad_tick"]
        | df["is_news_blackout"]
    )
    eligible_count = df["entry_eligible"].sum()
    total = len(df)
    pct = (eligible_count / total * 100) if total > 0 else 0
    print(f"[CLEAN] Entry eligible: {eligible_count}/{total} ({pct:.1f}%)")

    # Reset index
    df = df.reset_index(drop=True)

    return df
