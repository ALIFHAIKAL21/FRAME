"""
XAU_DEEP_SNIPER - Technical Indicator Features (TAHAP 2B)
==========================================================
Channel 6: Stochastic Momentum Index (SMI)
Channel 7: Moving Average Ribbon Slope & Differential

Sesuai spec BAB 3.2:

SMI = 100 * EMA(EMA(C - M)) / (0.5 * EMA(EMA(H - L)))
dimana M = 0.5 * (HH + LL) pada lookback period

MA Ribbon: Slope dan differential dari ribbon Fibonacci MA
(8, 13, 21, 34, 55) dinormalisasi terhadap ATR.

PRINSIP:
- Semua indikator CAUSAL (tanpa lookahead)
- Output dinormalisasi ke range terbatas untuk stabilitas model
"""

import pandas as pd
import numpy as np

from . import feature_config as fcfg
from .features_core import compute_ema, compute_atr


def compute_smi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = None,
    first_ema: int = None,
    second_ema: int = None,
) -> pd.Series:
    """
    Stochastic Momentum Index sesuai spec BAB 3.2 Channel 6.
    
    Formula:
        M = 0.5 * (HH_n + LL_n)
        D = Close - M
        HL = HH_n - LL_n
        SMI = 100 * EMA(EMA(D, k1), k2) / (0.5 * EMA(EMA(HL, k1), k2))
    
    Output di-clamp ke [-100, +100], lalu di-rescale ke [-1, +1].
    
    Parameters
    ----------
    high, low, close : pd.Series
        OHLC data.
    lookback : int
        Lookback period untuk highest-high / lowest-low.
    first_ema, second_ema : int
        EMA smoothing periods.
    
    Returns
    -------
    pd.Series
        SMI values dalam range [-1, +1].
    """
    lookback = lookback or fcfg.SMI_LOOKBACK
    first_ema = first_ema or fcfg.SMI_FIRST_EMA
    second_ema = second_ema or fcfg.SMI_SECOND_EMA
    eps = fcfg.EPSILON
    
    # Highest High dan Lowest Low pada lookback period
    hh = high.rolling(window=lookback, min_periods=lookback).max()
    ll = low.rolling(window=lookback, min_periods=lookback).min()
    
    # Midpoint M
    m = 0.5 * (hh + ll)
    
    # Deviation dari midpoint
    d = close - m
    
    # Range
    hl_range = hh - ll
    
    # Double EMA smoothing
    d_ema1 = d.ewm(span=first_ema, min_periods=first_ema, adjust=False).mean()
    d_ema2 = d_ema1.ewm(span=second_ema, min_periods=second_ema, adjust=False).mean()
    
    hl_ema1 = hl_range.ewm(span=first_ema, min_periods=first_ema, adjust=False).mean()
    hl_ema2 = hl_ema1.ewm(span=second_ema, min_periods=second_ema, adjust=False).mean()
    
    # SMI = 100 * d_smooth / (0.5 * hl_smooth)
    denominator = 0.5 * hl_ema2
    smi = 100.0 * d_ema2 / denominator.clip(lower=eps)
    
    # Clamp ke [-100, +100] lalu rescale ke [-1, +1]
    smi = smi.clip(-100.0, 100.0) / 100.0
    
    return smi


def compute_ma_ribbon_features(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    periods: list = None,
    slope_window: int = None,
) -> pd.DataFrame:
    """
    Moving Average Ribbon slope & differential sesuai spec BAB 3.2 Channel 7.
    
    Menghitung:
    1. EMA untuk setiap period di ribbon
    2. Slope (rate of change) dari EMA tercepat, dinormalisasi ATR
    3. Differential: spread antara EMA tercepat dan terlambat, dinormalisasi ATR
    4. Alignment score: berapa persen EMA yang "in order" (bullish/bearish alignment)
    
    Output: satu kolom komposit yang menggabungkan slope + alignment.
    
    Parameters
    ----------
    close : pd.Series
        Close price.
    high, low : pd.Series
        Untuk ATR normalization.
    periods : list
        EMA periods (default: Fibonacci [8, 13, 21, 34, 55]).
    slope_window : int
        Window untuk menghitung slope.
    
    Returns
    -------
    pd.DataFrame
        Kolom: ma_ribbon_slope, ma_ribbon_spread, ma_ribbon_alignment
    """
    periods = periods or fcfg.MA_RIBBON_PERIODS
    slope_window = slope_window or fcfg.MA_RIBBON_SLOPE_WINDOW
    eps = fcfg.EPSILON
    
    # Hitung ATR untuk normalisasi
    atr = compute_atr(high, low, close, fcfg.ATR_NORMALIZE_PERIOD)
    atr_safe = atr.clip(lower=eps)
    
    # Hitung semua EMA
    emas = {}
    for p in sorted(periods):
        emas[p] = compute_ema(close, p)
    
    sorted_periods = sorted(periods)
    fastest = sorted_periods[0]
    slowest = sorted_periods[-1]
    
    result = pd.DataFrame(index=close.index)
    
    # 1. Slope: rate of change dari EMA tercepat, normalized by ATR
    fastest_ema = emas[fastest]
    slope_raw = fastest_ema.diff(slope_window) / slope_window
    result["ma_ribbon_slope"] = (slope_raw / atr_safe).clip(-5.0, 5.0)
    
    # 2. Spread: jarak antara EMA tercepat dan terlambat, normalized by ATR
    spread_raw = emas[fastest] - emas[slowest]
    result["ma_ribbon_spread"] = (spread_raw / atr_safe).clip(-5.0, 5.0)
    
    # 3. Alignment: perfect bullish = +1, perfect bearish = -1, mixed = 0
    # Hitung berapa EMA yang "in order" (faster > slower)
    n_pairs = len(sorted_periods) - 1
    alignment = pd.Series(0.0, index=close.index)
    for i in range(n_pairs):
        faster_p = sorted_periods[i]
        slower_p = sorted_periods[i + 1]
        # +1 jika faster > slower (bullish), -1 jika sebaliknya
        alignment += np.where(emas[faster_p] > emas[slower_p], 1.0, -1.0)
    result["ma_ribbon_alignment"] = alignment / n_pairs  # Normalize ke [-1, +1]
    
    return result


def build_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Membangun Channel 6-7 (technical indicator features).
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan kolom OHLC.
    
    Returns
    -------
    pd.DataFrame
        DataFrame dengan kolom baru: smi, ma_ribbon_slope, 
        ma_ribbon_spread, ma_ribbon_alignment
    """
    df = df.copy()
    
    # Channel 6: SMI
    df["smi"] = compute_smi(df["high"], df["low"], df["close"])
    
    # Channel 7: MA Ribbon (3 sub-features, akan di-composite nanti)
    ribbon = compute_ma_ribbon_features(
        df["close"], df["high"], df["low"]
    )
    for col in ribbon.columns:
        df[col] = ribbon[col]
    
    return df
