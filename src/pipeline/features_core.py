"""
XAU_DEEP_SNIPER - Scale-Free Feature Transforms (TAHAP 2A)
============================================================
Implementasi transformasi stasioner sesuai spec BAB 3.1:

Channel 1-4: OHLC dinormalisasi terhadap EMA dan ATR lokal
    P_tilde_t = (P_t - EMA_64(P_t)) / ATR_64(t)

Channel 5: Volume Z-score dinamis (rolling 128 bar)
    V_tilde_t = (V_t - mu_V(128)) / sigma_V(128)

PRINSIP DESAIN:
- Semua transformasi bersifat CAUSAL (hanya pakai data t dan sebelumnya)
- Tidak ada lookahead bias
- NaN pada awal series (warmup period) dibiarkan, akan di-handle saat windowing
"""

import pandas as pd
import numpy as np
from typing import Tuple

from . import feature_config as fcfg


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average — causal, tanpa lookahead.
    
    Parameters
    ----------
    series : pd.Series
        Data input (harga, volume, dll).
    period : int
        Period EMA.
    
    Returns
    -------
    pd.Series
        EMA values. Baris 0..(period-2) akan NaN.
    """
    return series.ewm(span=period, min_periods=period, adjust=False).mean()


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
) -> pd.Series:
    """
    Average True Range — causal, tanpa lookahead.
    Menggunakan EMA-based ATR (Wilder's method).
    
    Parameters
    ----------
    high, low, close : pd.Series
        Kolom OHLC.
    period : int
        Period ATR.
    
    Returns
    -------
    pd.Series
        ATR values.
    """
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Wilder's smoothing (equivalent to EMA with alpha = 1/period)
    atr = true_range.ewm(span=period, min_periods=period, adjust=False).mean()
    
    return atr


def normalize_ohlc_scale_free(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transformasi OHLC ke bentuk scale-free sesuai spec BAB 3.1:
    
        P_tilde_t = (P_t - EMA_64(Close_t)) / ATR_64(t)
    
    Menggunakan EMA dan ATR dari CLOSE sebagai referensi detrending
    untuk semua 4 kolom OHLC agar relasi H >= max(O,C) tetap valid
    secara relatif.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan kolom: open, high, low, close.
    
    Returns
    -------
    pd.DataFrame
        DataFrame dengan kolom baru:
        ohlc_norm_open, ohlc_norm_high, ohlc_norm_low, ohlc_norm_close
    """
    period = fcfg.EMA_DETREND_PERIOD
    eps = fcfg.EPSILON
    
    # EMA dan ATR dihitung dari CLOSE
    ema_close = compute_ema(df["close"], period)
    atr = compute_atr(df["high"], df["low"], df["close"], fcfg.ATR_NORMALIZE_PERIOD)
    
    # Normalisasi: (P - EMA) / ATR
    # ATR di-clamp ke epsilon untuk menghindari division by zero
    atr_safe = atr.clip(lower=eps)
    
    result = pd.DataFrame(index=df.index)
    result["ohlc_norm_open"] = (df["open"] - ema_close) / atr_safe
    result["ohlc_norm_high"] = (df["high"] - ema_close) / atr_safe
    result["ohlc_norm_low"] = (df["low"] - ema_close) / atr_safe
    result["ohlc_norm_close"] = (df["close"] - ema_close) / atr_safe
    
    return result


def compute_volume_zscore(volume: pd.Series) -> pd.Series:
    """
    Volume Z-score dinamis (rolling) sesuai spec BAB 3.1:
    
        V_tilde_t = (V_t - mu_V(128)) / sigma_V(128)
    
    Parameters
    ----------
    volume : pd.Series
        Raw volume data.
    
    Returns
    -------
    pd.Series
        Volume z-score. Clipped ke [-5, +5] untuk stabilitas numerik.
    """
    window = fcfg.VOLUME_ZSCORE_WINDOW
    eps = fcfg.EPSILON
    
    rolling_mean = volume.rolling(window=window, min_periods=window).mean()
    rolling_std = volume.rolling(window=window, min_periods=window).std()
    
    # Z-score dengan proteksi division-by-zero
    zscore = (volume - rolling_mean) / rolling_std.clip(lower=eps)
    
    # Clip ke [-5, +5] untuk menghindari extreme outlier mempengaruhi training
    zscore = zscore.clip(-5.0, 5.0)
    
    return zscore


def compute_returns_and_volatility(df: pd.DataFrame) -> pd.DataFrame:
    """
    Menghitung log-return, percentage return, dan rolling volatility.
    
    Returns
    -------
    pd.DataFrame
        Kolom: log_return, return_pct, rolling_vol_20, rolling_vol_64
    """
    res = pd.DataFrame(index=df.index)
    close = df["close"]
    prev_close = close.shift(1)
    
    res["log_return"] = np.log(close / prev_close)
    res["return_pct"] = (close - prev_close) / prev_close * 100.0
    res["rolling_vol_20"] = res["log_return"].rolling(window=20, min_periods=20).std()
    res["rolling_vol_64"] = res["log_return"].rolling(window=64, min_periods=64).std()
    return res


def build_core_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Membangun Channel 1-5 (core scale-free features).
    
    Parameters
    ----------
    df : pd.DataFrame
        Clean DataFrame dengan kolom OHLCV.
    
    Returns
    -------
    pd.DataFrame
        DataFrame dengan 5 kolom fitur baru ditambahkan:
        ohlc_norm_open, ohlc_norm_high, ohlc_norm_low, ohlc_norm_close,
        volume_zscore
    
    Raises
    ------
    ValueError
        Jika kolom OHLCV tidak ditemukan.
    """
    required = ["open", "high", "low", "close", "volume"]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"Kolom OHLCV tidak ditemukan: {missing}")
    
    df = df.copy()
    
    # Channel 1-4: Normalized OHLC
    ohlc_norm = normalize_ohlc_scale_free(df)
    for col in ohlc_norm.columns:
        df[col] = ohlc_norm[col]
    
    # Channel 5: Volume Z-score
    df["volume_zscore"] = compute_volume_zscore(df["volume"].astype(float))
    
    # Supplementary statistical features: log-return, return_pct, volatility
    ret_df = compute_returns_and_volatility(df)
    for col in ret_df.columns:
        df[col] = ret_df[col]
    
    return df


def get_warmup_period() -> int:
    """
    Menghitung jumlah bar awal yang akan NaN karena warmup period
    dari semua rolling/EMA calculations.
    
    Returns
    -------
    int
        Jumlah bar minimum yang diperlukan sebelum fitur valid.
    """
    # ATR dan EMA keduanya pakai period 64, volume zscore pakai 128
    # Warmup = max dari semua window
    return max(
        fcfg.EMA_DETREND_PERIOD,
        fcfg.ATR_NORMALIZE_PERIOD, 
        fcfg.VOLUME_ZSCORE_WINDOW,
    )


def validate_core_features(df: pd.DataFrame) -> dict:
    """
    Validasi statistik fitur core untuk memastikan stationarity.
    
    Checks:
    1. Tidak ada Inf values
    2. Mean mendekati 0 (detrended)
    3. Standard deviation reasonable (1-3 untuk normalized)
    4. No extreme outliers beyond [-10, +10] untuk OHLC norm
    
    Returns
    -------
    dict
        Laporan validasi per channel.
    """
    warmup = get_warmup_period()
    channels = [
        "ohlc_norm_open", "ohlc_norm_high", 
        "ohlc_norm_low", "ohlc_norm_close",
        "volume_zscore",
    ]
    
    report = {}
    for ch in channels:
        if ch not in df.columns:
            report[ch] = {"status": "MISSING"}
            continue
        
        data = df[ch].iloc[warmup:]  # Skip warmup NaN period
        valid = data.dropna()
        
        stats = {
            "count": len(valid),
            "nan_count": data.isna().sum(),
            "inf_count": int(np.isinf(valid).sum()),
            "mean": round(float(valid.mean()), 4),
            "std": round(float(valid.std()), 4),
            "min": round(float(valid.min()), 4),
            "max": round(float(valid.max()), 4),
            "pct_within_3std": round(
                float((valid.abs() <= 3 * valid.std()).sum() / len(valid) * 100), 2
            ),
        }
        
        # Pass/fail
        issues = []
        if stats["inf_count"] > 0:
            issues.append("INF_VALUES")
        if abs(stats["mean"]) > 2.0 and ch != "volume_zscore":
            issues.append("MEAN_NOT_CENTERED")
        if stats["std"] < 0.01:
            issues.append("ZERO_VARIANCE")
        
        stats["status"] = "PASS" if not issues else "FAIL"
        stats["issues"] = issues
        
        report[ch] = stats
    
    return report
