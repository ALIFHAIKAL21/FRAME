"""
XAU_DEEP_SNIPER - Technical Indicator Features (TAHAP 2B)
==========================================================
Channel 6: Moving Average Cross (SMA 9 x SMA 21 Spread / ATR)
Channel 7: Stochastic Momentum Index (SMI 10, 3, 3, 10)
Channel 8: SMI Signal & Histogram Differential
Channel 9: SMI Overbought (+40) / Oversold (-40) Reversal Triggers

Sesuai spesifikasi AGENT.MD:
- Indikator khusus 1: MA Cross (SMA 9 x SMA 21)
- Indikator khusus 2: SMI (Stochastic Momentum Index) TradingView default (10, 3, 3, 10)

PRINSIP:
- Semua indikator CAUSAL (tanpa lookahead)
- Output dinormalisasi ke range terbatas untuk stabilitas model
"""

import pandas as pd
import numpy as np

from . import feature_config as fcfg
from .features_core import compute_ema, compute_atr


def compute_tradingview_smi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 10,
    first_ema: int = 3,
    second_ema: int = 3,
    signal_ema: int = 10,
) -> pd.DataFrame:
    """
    Stochastic Momentum Index (SMI) TradingView default (10, 3, 3, 10).
    
    Formula:
        M = 0.5 * (HH_n + LL_n)
        D = Close - M
        HL = HH_n - LL_n
        SMI = 100 * EMA(EMA(D, 3), 3) / (0.5 * EMA(EMA(HL, 3), 3))
        Signal = EMA(SMI, 10)
        Hist = SMI - Signal
    
    Returns
    -------
    pd.DataFrame
        Kolom: smi_val (rescaled [-1, 1]), smi_signal_hist (rescaled [-1, 1]),
        smi_reversal_zone (+1 OS bull reversal, -1 OB bear reversal, 0 neutral)
    """
    eps = fcfg.EPSILON
    
    # Highest High dan Lowest Low pada lookback period
    hh = high.rolling(window=lookback, min_periods=lookback).max()
    ll = low.rolling(window=lookback, min_periods=lookback).min()
    
    # Midpoint M
    m = 0.5 * (hh + ll)
    d = close - m
    hl_range = hh - ll
    
    # Double EMA smoothing
    d_ema1 = d.ewm(span=first_ema, min_periods=first_ema, adjust=False).mean()
    d_ema2 = d_ema1.ewm(span=second_ema, min_periods=second_ema, adjust=False).mean()
    
    hl_ema1 = hl_range.ewm(span=first_ema, min_periods=first_ema, adjust=False).mean()
    hl_ema2 = hl_ema1.ewm(span=second_ema, min_periods=second_ema, adjust=False).mean()
    
    denominator = 0.5 * hl_ema2
    smi_raw = 100.0 * d_ema2 / denominator.clip(lower=eps)
    smi_raw = smi_raw.clip(-100.0, 100.0)
    
    # Signal Line (10-period EMA of SMI)
    smi_signal = smi_raw.ewm(span=signal_ema, min_periods=signal_ema, adjust=False).mean()
    smi_hist = smi_raw - smi_signal
    
    # Reversal Triggers:
    # Bull reversal: previous bar was in Oversold (< -40) and current bar crosses back above -40 or signal
    prev_smi = smi_raw.shift(1)
    os_reversal_bull = (prev_smi < -40.0) & (smi_raw > prev_smi)
    ob_reversal_bear = (prev_smi > 40.0) & (smi_raw < prev_smi)
    
    reversal_zone = pd.Series(0.0, index=close.index)
    reversal_zone[os_reversal_bull] = 1.0
    reversal_zone[ob_reversal_bear] = -1.0
    
    result = pd.DataFrame(index=close.index)
    # Rescale to [-1, 1] for neural network
    result["smi_val"] = smi_raw / 100.0
    result["smi_signal_hist"] = (smi_hist / 50.0).clip(-1.0, 1.0)
    result["smi_reversal_zone"] = reversal_zone
    
    # Backward compatibility column 'smi'
    result["smi"] = result["smi_val"]
    
    return result


def compute_sma_cross_features(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    fast_period: int = 9,
    slow_period: int = 21,
) -> pd.DataFrame:
    """
    Moving Average Cross (SMA 9 x SMA 21) sesuai AGENT.MD.
    
    Returns
    -------
    pd.DataFrame
        Kolom: sma_cross_spread (normalized by ATR), sma_trend
    """
    eps = fcfg.EPSILON
    atr = compute_atr(high, low, close, fcfg.ATR_NORMALIZE_PERIOD).clip(lower=eps)
    
    sma_fast = close.rolling(window=fast_period, min_periods=fast_period).mean()
    sma_slow = close.rolling(window=slow_period, min_periods=slow_period).mean()
    
    spread = sma_fast - sma_slow
    norm_spread = (spread / atr).clip(-3.0, 3.0)
    
    result = pd.DataFrame(index=close.index)
    result["sma_cross_spread"] = norm_spread
    result["ma_ribbon_slope"] = norm_spread  # Backward compatibility
    
    return result


def build_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Membangun Channel 6-9 (technical indicator features).
    """
    df = df.copy()
    
    # Channels 7-9: SMI components
    smi_df = compute_tradingview_smi(df["high"], df["low"], df["close"])
    for col in smi_df.columns:
        df[col] = smi_df[col]
        
    # Channel 6: SMA 9x21 Cross Spread
    sma_df = compute_sma_cross_features(df["close"], df["high"], df["low"])
    for col in sma_df.columns:
        df[col] = sma_df[col]
        
    return df
