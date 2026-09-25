"""
XAU_DEEP_SNIPER - Feature Pipeline Orchestrator (TAHAP 2)
==========================================================
Menyatukan seluruh 9 channel fitur dan melakukan temporal split.

Pipeline:
1. Load clean parquet
2. Build Channel 1-4 (OHLC normalized)
3. Build Channel 5 (Volume Z-score)
4. Build Channel 6 (SMI)
5. Build Channel 7 (MA Ribbon)
6. Build Channel 8 (Liquidity Distance)
7. Build Channel 9 (FVG Status)
8. Temporal train/test split (80/20, purge + embargo)
9. Validasi & save
"""

import pandas as pd
import numpy as np
import pathlib
from typing import Tuple, Dict

from . import config
from . import feature_config as fcfg
from .features_core import build_core_features, validate_core_features, get_warmup_period
from .features_technical import build_technical_features
from .features_structural import build_structural_features
from .features_macro import build_macro_features
from .dst_harmonizer import add_session_labels


def build_all_features(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Membangun seluruh 9 channel fitur secara berurutan.
    
    Parameters
    ----------
    df : pd.DataFrame
        Clean DataFrame dari TAHAP 1 (dengan kolom OHLCV + flags).
    verbose : bool
        Print progress.
    
    Returns
    -------
    pd.DataFrame
        DataFrame dengan 9 channel fitur + kolom asli.
    """
    if verbose:
        print(f"[FEATURES] Building 9-channel feature set on {len(df)} bars...")
    
    # Channel 1-5: Core scale-free transforms
    if verbose:
        print(f"  [Ch 1-5] OHLC normalization + Volume Z-score...")
    df = build_core_features(df)
    
    # Channel 6-7: Technical indicators
    if verbose:
        print(f"  [Ch 6-7] SMI + MA Ribbon...")
    df = build_technical_features(df)
    
    # Channel 8-9: Structural features
    if verbose:
        print(f"  [Ch 8-9] Liquidity Distance + FVG Status...")
    df = build_structural_features(df)
    
    # Channel 12-14: H4 Macro Multi-Timeframe features (Strictly Causal)
    if verbose:
        print(f"  [Ch 12-14] H4 Macro Velocity + Market Structure + Momentum Expansion...")
    df = build_macro_features(df)
    
    # Session labels
    if "timestamp_utc" in df.columns and "session" not in df.columns:
        if verbose:
            print(f"  [Session] Adding dynamic DST-corrected session labels...")
        df["session"] = add_session_labels(df)
    
    if verbose:
        warmup = get_warmup_period()
        valid_bars = len(df) - warmup
        print(f"  [DONE] All channels built. Warmup={warmup} bars, Valid={valid_bars} bars.")
    
    return df


def temporal_split(
    df: pd.DataFrame,
    train_ratio: float = None,
    purge_bars: int = None,
    embargo_bars: int = None,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Temporal train/test split sesuai spec BAB 6.1:
    - In-sample: 4 tahun pertama (80%)
    - Out-of-sample: 1 tahun terakhir (20%)
    - Purge: 16 bars (8 jam) — menghapus data latih yang bertabrakan
      dengan horizon Triple Barrier
    - Embargo: 48 bars (24 jam) — jeda kosong setelah segmen latih
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan fitur (sudah di-trim warmup NaN).
    train_ratio : float
        Proporsi data untuk training.
    purge_bars, embargo_bars : int
        Purge dan embargo window sizes.
    verbose : bool
        Print split info.
    
    Returns
    -------
    (train_df, test_df)
        Tuple dari training dan testing DataFrames.
    """
    train_ratio = train_ratio or fcfg.TRAIN_RATIO
    purge_bars = purge_bars or fcfg.PURGE_BARS
    embargo_bars = embargo_bars or fcfg.EMBARGO_BARS
    
    n = len(df)
    split_idx = int(n * train_ratio)
    
    # Apply purge: hapus `purge_bars` terakhir dari training set
    train_end = split_idx - purge_bars
    
    # Apply embargo: hapus `embargo_bars` pertama dari test set
    test_start = split_idx + embargo_bars
    
    train_df = df.iloc[:train_end].copy()
    test_df = df.iloc[test_start:].copy()
    
    if verbose:
        train_start_date = train_df["timestamp_utc"].iloc[0]
        train_end_date = train_df["timestamp_utc"].iloc[-1]
        test_start_date = test_df["timestamp_utc"].iloc[0]
        test_end_date = test_df["timestamp_utc"].iloc[-1]
        
        purged = purge_bars
        embargoed = embargo_bars
        gap_total = purged + embargoed
        
        print(f"\n[SPLIT] Temporal Train/Test Split")
        print(f"  Total bars       : {n}")
        print(f"  Train            : {len(train_df)} bars ({train_start_date} -> {train_end_date})")
        print(f"  Test             : {len(test_df)} bars ({test_start_date} -> {test_end_date})")
        print(f"  Purge gap        : {purged} bars removed from train end")
        print(f"  Embargo gap      : {embargoed} bars removed from test start")
        print(f"  Total discarded  : {gap_total} bars in buffer zone")
        print(f"  Leakage check    : Train end {train_end_date} + {gap_total} bars << Test start {test_start_date}")
    
    return train_df, test_df


def trim_warmup_nans(df: pd.DataFrame) -> pd.DataFrame:
    """
    Menghapus baris awal yang masih NaN akibat warmup period.
    
    Returns
    -------
    pd.DataFrame
        DataFrame tanpa warmup NaN rows.
    """
    feature_cols = list(fcfg.FEATURE_CHANNELS.values())
    existing = [c for c in feature_cols if c in df.columns]
    
    if not existing:
        return df
    
    # Cari baris pertama yang semua fitur valid (non-NaN)
    first_valid = df[existing].dropna().index[0]
    return df.loc[first_valid:].reset_index(drop=True)


def get_feature_columns() -> list:
    """Mengembalikan list kolom fitur sesuai urutan channel."""
    return list(fcfg.FEATURE_CHANNELS.values())


def validate_all_features(df: pd.DataFrame, verbose: bool = True) -> Dict:
    """
    Validasi lengkap semua 9 channel fitur.
    
    Returns
    -------
    dict
        Laporan validasi per channel.
    """
    report = validate_core_features(df)
    
    # Validate all 12 feature channels
    warmup = get_warmup_period()
    for ch_idx, ch in fcfg.FEATURE_CHANNELS.items():
        if ch in report:
            continue
        if ch not in df.columns:
            report[ch] = {"status": "MISSING"}
            continue
        data = df[ch].iloc[warmup:].dropna()
        report[ch] = {
            "count": len(data),
            "mean": round(float(data.mean()), 4),
            "std": round(float(data.std()), 4),
            "min": round(float(data.min()), 4),
            "max": round(float(data.max()), 4),
            "inf_count": int(np.isinf(data).sum()),
            "status": "PASS" if not np.isinf(data).any() else "FAIL",
            "issues": ["INF_VALUES"] if np.isinf(data).any() else [],
        }
    
    if verbose:
        print("\n[VALIDATION] Feature Quality Report:")
        all_pass = True
        for ch, stats in report.items():
            status = stats.get("status", "?")
            icon = "PASS" if status == "PASS" else "FAIL"
            issues = stats.get("issues", [])
            detail = f" mean={stats.get('mean','?')}, std={stats.get('std','?')}" if "mean" in stats else ""
            print(f"  [{icon}] {ch:25s}{detail}")
            if status != "PASS":
                all_pass = False
        
        if all_pass:
            print("  >>> ALL CHANNELS VALIDATED SUCCESSFULLY")
        else:
            print("  >>> SOME CHANNELS FAILED VALIDATION")
    
    return report



def extract_feature_windows(
    df: pd.DataFrame,
    window_length: int = 64,
    channels: list = None,
) -> Tuple[np.ndarray, pd.Series]:
    """
    Ekstrak sliding window tensor (N, C, L) dari feature DataFrame untuk MOMENT-1-large.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame yang sudah memiliki kolom fitur (dan di-trim warmup NaN-nya).
    window_length : int
        Panjang sequence L (default 64 bar M30, spec BAB 3.2 & 5.1).
    channels : list, optional
        List kolom channel fitur. Default: 9 channel dari fcfg.FEATURE_CHANNELS.
        
    Returns
    -------
    (X, timestamps) : Tuple[np.ndarray, pd.Series]
        X: array float32 dengan shape (N, C, L)
           di mana N = jumlah window, C = jumlah channel, L = window_length.
        timestamps: Series timestamp UTC pada bar t (akhir setiap window).
    """
    from numpy.lib.stride_tricks import sliding_window_view
    
    channels = channels or get_feature_columns()
    missing = [c for c in channels if c not in df.columns]
    if missing:
        raise ValueError(f"Channel tidak ditemukan di DataFrame: {missing}")
    
    feature_matrix = df[channels].values.astype(np.float32)
    n_bars, n_channels = feature_matrix.shape
    
    if n_bars < window_length:
        raise ValueError(f"Jumlah bar ({n_bars}) < window_length ({window_length})")
    
    windows = sliding_window_view(feature_matrix, window_shape=window_length, axis=0)
    timestamps = df["timestamp_utc"].iloc[window_length - 1:].reset_index(drop=True)
    
    return np.ascontiguousarray(windows, dtype=np.float32), timestamps
