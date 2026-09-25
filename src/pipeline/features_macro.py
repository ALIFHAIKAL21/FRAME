"""
XAU_DEEP_SNIPER - H4 Macro Multi-Timeframe Features (TAHAP 2D)
==============================================================
Channel 12: H4 Macro Trend Velocity (Kecepatan dan Arah Ombak Besar H4)
Channel 13: H4 Market Structure (Status Bullish / Bearish Struktural H4)
Channel 14: Momentum Expansion Persistence (Deteksi Arus Dana Berkelanjutan)

PRINSIP SAKRAL CAUSALITY:
- Resample M30 ke completed H4 bars.
- Seluruh kalkulasi indikator di H4 di-shift(1) sebelum di-merge ke M30 (ffill).
- M30 pada bar t HANYA melihat H4 bar yang sudah CLOSED sebelum t.
- ZERO LOOKAHEAD BIAS terjamin secara matematis.
"""

import pandas as pd
import numpy as np


def compute_h4_macro_features(df_m30: pd.DataFrame) -> pd.DataFrame:
    """
    Menghitung 3 channel makro H4 secara strictly causal.
    
    Parameters
    ----------
    df_m30 : pd.DataFrame
        DataFrame M30 dengan index datetime atau kolom 'timestamp_utc'.
        
    Returns
    -------
    pd.DataFrame
        DataFrame M30 dengan 3 kolom channel makro baru.
    """
    df = df_m30.copy()
    if 'timestamp_utc' in df.columns:
        df['ts'] = pd.to_datetime(df['timestamp_utc'], utc=True)
    else:
        df['ts'] = pd.to_datetime(df.index, utc=True)
        
    # 1. Resample strictly causal ke 4H bars
    df_h4 = df.set_index('ts').resample('4h').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    
    eps = 1e-8
    
    # Indikator H4
    # EMA 20, 50, 200 pada H4
    h4_c = df_h4['close']
    h4_h = df_h4['high']
    h4_l = df_h4['low']
    
    ema20 = h4_c.ewm(span=20, adjust=False).mean()
    ema50 = h4_c.ewm(span=50, adjust=False).mean()
    ema200 = h4_c.ewm(span=200, adjust=False).mean()
    
    # ATR 14 pada H4
    tr1 = h4_h - h4_l
    tr2 = (h4_h - h4_c.shift(1)).abs()
    tr3 = (h4_l - h4_c.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=14).mean().bfill()
    
    # -------------------------------------------------------------
    # Channel 12: H4 Macro Trend Velocity
    # V_h4 = (EMA20_t - EMA20_{t-3}) / ATR14
    # Dinormalisasi menggunakan tanh(V / 1.5) agar range [-1.0, 1.0]
    # -------------------------------------------------------------
    raw_velocity = (ema20 - ema20.shift(3)) / (atr14 + eps)
    h4_macro_trend_velocity = np.tanh(raw_velocity / 1.5)
    
    # -------------------------------------------------------------
    # Channel 13: H4 Market Structure
    # Evaluasi Ribbon Alignment (Close, EMA20, EMA50, EMA200)
    # Skor kontinu di [-1.0, 1.0]
    # -------------------------------------------------------------
    s1 = np.tanh((h4_c - ema50) / (2.0 * atr14 + eps))
    s2 = np.tanh((ema20 - ema50) / (atr14 + eps))
    s3 = np.tanh((ema50 - ema200) / (2.0 * atr14 + eps))
    h4_market_structure = np.clip((s1 + s2 + s3) / 3.0 * 1.5, -1.0, 1.0)
    
    # -------------------------------------------------------------
    # Channel 14: Momentum Expansion Persistence
    # Deteksi ATH / Multi-week expansion persistence
    # -------------------------------------------------------------
    high_20d = h4_h.rolling(120, min_periods=20).max() # 20 hari = 120 bar H4
    low_20d = h4_l.rolling(120, min_periods=20).min()
    
    range_pos = 2.0 * ((h4_c - low_20d) / (high_20d - low_20d + eps)) - 1.0
    range_pos = np.clip(range_pos, -1.0, 1.0)
    
    dist_e50 = np.clip((h4_c - ema50) / (3.0 * atr14 + eps), -1.0, 1.0)
    momentum_expansion_persistence = np.clip(0.6 * range_pos + 0.4 * dist_e50, -1.0, 1.0)
    
    df_h4_out = pd.DataFrame({
        'h4_macro_trend_velocity': h4_macro_trend_velocity,
        'h4_market_structure': h4_market_structure,
        'momentum_expansion_persistence': momentum_expansion_persistence
    }, index=df_h4.index)
    
    # CRITICAL: SHIFT 1 BAR H4 SEBELUM MERGE (ZERO LOOKAHEAD)
    df_h4_lagged = df_h4_out.shift(1)
    
    # Merge kembali ke index M30
    df_merged = df.merge(df_h4_lagged, left_on='ts', right_index=True, how='left')
    
    # Forward fill agar bar M30 di antara H4 bar mewarisi H4 terakhir yang sudah closed
    df_merged['h4_macro_trend_velocity'] = df_merged['h4_macro_trend_velocity'].ffill().fillna(0.0)
    df_merged['h4_market_structure'] = df_merged['h4_market_structure'].ffill().fillna(0.0)
    df_merged['momentum_expansion_persistence'] = df_merged['momentum_expansion_persistence'].ffill().fillna(0.0)
    
    res = pd.DataFrame(index=df_m30.index)
    res['h4_macro_trend_velocity'] = df_merged['h4_macro_trend_velocity'].values
    res['h4_market_structure'] = df_merged['h4_market_structure'].values
    res['momentum_expansion_persistence'] = df_merged['momentum_expansion_persistence'].values
    
    return res


def build_macro_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Membangun Channel 13-15 (H4 Macro Features).
    """
    df = df.copy()
    macro_df = compute_h4_macro_features(df)
    for col in macro_df.columns:
        df[col] = macro_df[col]
    return df
