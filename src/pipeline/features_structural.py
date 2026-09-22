"""
XAU_DEEP_SNIPER - Structural Market Features (TAHAP 2C)
========================================================
Channel 8: Jarak harga ke Liquidity Pool terdekat (Fractal Swing H/L)
Channel 9: Fair Value Gap (FVG) / Order Block status

Sesuai spec BAB 3.2:
- Channel 8: Jarak harga saat ini terhadap Liquidity Pool terdekat
  (Fractal Swing High/Low) dibagi ATR.
- Channel 9: Status FVG / Order Block yang belum termitigasi
  (unmitigated imbalance).

PRINSIP:
- Fractal detection: Williams Fractal (2 bar kiri, 2 bar kanan)
  CATATAN: fractals butuh 2 bar ke kanan, jadi fractal terakhir yang
  bisa dikonfirmasi = bar t-2. Ini BUKAN lookahead karena fractal
  di bar t memang belum terkonfirmasi di real-time.
- FVG detection: 3-bar pattern, fully causal
"""

import pandas as pd
import numpy as np

from . import feature_config as fcfg
from .features_core import compute_atr


def detect_fractal_highs(high: pd.Series, window: int = None) -> pd.Series:
    """
    Mendeteksi Williams Fractal Highs.
    
    Fractal High di bar i: high[i] > semua high dalam [i-n, i+n] kecuali i.
    Default n = 2 (5-bar pattern).
    
    CATATAN: Fractal di bar i baru terkonfirmasi setelah bar i+n selesai.
    Jadi pada real-time bar t, fractal terbaru yang valid = bar t-n.
    
    Parameters
    ----------
    high : pd.Series
        High prices.
    window : int
        Half-window size (default 2 untuk 5-bar fractal).
    
    Returns
    -------
    pd.Series
        Boolean, True = bar ini adalah fractal high (terkonfirmasi).
    """
    n = (window or fcfg.FRACTAL_WINDOW) // 2  # 5 // 2 = 2
    is_fractal = pd.Series(False, index=high.index, dtype=bool)
    
    for i in range(n, len(high) - n):
        center = high.iloc[i]
        left = high.iloc[i - n:i].max()
        right = high.iloc[i + 1:i + n + 1].max()
        if center > left and center > right:
            is_fractal.iloc[i] = True
    
    return is_fractal


def detect_fractal_lows(low: pd.Series, window: int = None) -> pd.Series:
    """
    Mendeteksi Williams Fractal Lows.
    
    Fractal Low di bar i: low[i] < semua low dalam [i-n, i+n] kecuali i.
    
    Returns
    -------
    pd.Series
        Boolean, True = bar ini adalah fractal low (terkonfirmasi).
    """
    n = (window or fcfg.FRACTAL_WINDOW) // 2
    is_fractal = pd.Series(False, index=low.index, dtype=bool)
    
    for i in range(n, len(low) - n):
        center = low.iloc[i]
        left = low.iloc[i - n:i].min()
        right = low.iloc[i + 1:i + n + 1].min()
        if center < left and center < right:
            is_fractal.iloc[i] = True
    
    return is_fractal


def compute_liquidity_distance(
    df: pd.DataFrame,
    fractal_highs: pd.Series,
    fractal_lows: pd.Series,
) -> pd.Series:
    """
    Channel 8: Jarak harga ke Liquidity Pool terdekat.
    
    Menghitung jarak close saat ini terhadap fractal swing terdekat
    (baik high maupun low), dinormalisasi ATR.
    
    Konvensi tanda:
    - Positif: harga di ATAS liquidity pool terdekat (potential sell-side sweep)
    - Negatif: harga di BAWAH liquidity pool terdekat (potential buy-side sweep)
    - Mendekati 0: harga berada dekat liquidity pool
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan OHLC.
    fractal_highs, fractal_lows : pd.Series
        Boolean series dari detect_fractal_highs/lows.
    
    Returns
    -------
    pd.Series
        Signed distance, normalized by ATR, clipped ke [-5, +5].
    """
    eps = fcfg.EPSILON
    lookback = fcfg.LIQUIDITY_LOOKBACK
    
    atr = compute_atr(df["high"], df["low"], df["close"], fcfg.ATR_NORMALIZE_PERIOD)
    atr_safe = atr.clip(lower=eps)
    
    close = df["close"]
    result = pd.Series(0.0, index=df.index)
    
    # Kumpulkan semua fractal levels
    fractal_high_prices = df["high"][fractal_highs]
    fractal_low_prices = df["low"][fractal_lows]
    
    # Konfirmasi delay: fractal di bar i dikonfirmasi di bar i+2
    confirm_delay = fcfg.FRACTAL_WINDOW // 2
    
    for t in range(len(df)):
        # Hanya gunakan fractals yang sudah terkonfirmasi (confirmed at t - confirm_delay)
        max_fractal_idx = t - confirm_delay
        if max_fractal_idx < 0:
            result.iloc[t] = 0.0
            continue
        
        # Lookback window
        min_idx = max(0, max_fractal_idx - lookback)
        
        # Fractal highs dan lows dalam window
        fh_mask = fractal_highs.iloc[min_idx:max_fractal_idx + 1]
        fl_mask = fractal_lows.iloc[min_idx:max_fractal_idx + 1]
        
        fh_prices = df["high"].iloc[min_idx:max_fractal_idx + 1][fh_mask]
        fl_prices = df["low"].iloc[min_idx:max_fractal_idx + 1][fl_mask]
        
        if len(fh_prices) == 0 and len(fl_prices) == 0:
            result.iloc[t] = 0.0
            continue
        
        current_close = close.iloc[t]
        current_atr = atr_safe.iloc[t]
        
        # Jarak ke fractal high terdekat
        min_dist_high = float("inf")
        if len(fh_prices) > 0:
            dists_high = (current_close - fh_prices).abs()
            min_dist_high = dists_high.min()
            nearest_high = fh_prices.iloc[dists_high.values.argmin()]
            sign_high = 1.0 if current_close > nearest_high else -1.0
        
        # Jarak ke fractal low terdekat
        min_dist_low = float("inf")
        if len(fl_prices) > 0:
            dists_low = (current_close - fl_prices).abs()
            min_dist_low = dists_low.min()
            nearest_low = fl_prices.iloc[dists_low.values.argmin()]
            sign_low = 1.0 if current_close > nearest_low else -1.0
        
        # Pilih yang terdekat
        if min_dist_high <= min_dist_low:
            result.iloc[t] = sign_high * min_dist_high / current_atr
        else:
            result.iloc[t] = sign_low * min_dist_low / current_atr
    
    return result.clip(-5.0, 5.0)


def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mendeteksi Fair Value Gaps (FVG) — 3-bar imbalance pattern.
    
    Bullish FVG: bar[i-2].high < bar[i].low (gap up, unfilled)
    Bearish FVG: bar[i-2].low > bar[i].high (gap down, unfilled)
    
    Returns
    -------
    pd.DataFrame
        Kolom: fvg_bullish_active, fvg_bearish_active, fvg_top, fvg_bottom
        untuk setiap FVG yang masih belum termitigasi di bar t.
    """
    n = len(df)
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    
    # Track active (unmitigated) FVGs
    # Setiap FVG: (top, bottom, bar_created, direction)
    active_fvgs = []
    
    # Output: signed FVG status per bar
    fvg_status = np.zeros(n, dtype=np.float64)
    
    expiry = fcfg.FVG_EXPIRY_BARS
    atr = compute_atr(
        df["high"], df["low"], df["close"], fcfg.ATR_NORMALIZE_PERIOD
    ).values
    min_gap_ratio = fcfg.FVG_MIN_GAP_ATR_RATIO
    eps = fcfg.EPSILON
    
    for t in range(2, n):
        current_atr = max(atr[t], eps)
        
        # Deteksi FVG baru pada bar t (menggunakan bar t-2, t-1, t)
        # Bullish FVG: gap antara high[t-2] dan low[t]
        bull_gap = low[t] - high[t - 2]
        if bull_gap > min_gap_ratio * current_atr:
            active_fvgs.append({
                "top": low[t],
                "bottom": high[t - 2],
                "created": t,
                "direction": 1,  # bullish
            })
        
        # Bearish FVG: gap antara low[t-2] dan high[t]
        bear_gap = low[t - 2] - high[t]
        if bear_gap > min_gap_ratio * current_atr:
            active_fvgs.append({
                "top": low[t - 2],
                "bottom": high[t],
                "created": t,
                "direction": -1,  # bearish
            })
        
        # Mitigasi check: hapus FVG yang sudah terisi atau expired
        still_active = []
        for fvg in active_fvgs:
            age = t - fvg["created"]
            if age > expiry:
                continue  # Expired
            
            # Mitigasi: harga menembus zona FVG
            if fvg["direction"] == 1:  # Bullish
                # Mitigated jika harga turun ke bawah bottom FVG
                if low[t] <= fvg["bottom"]:
                    continue
            else:  # Bearish
                # Mitigated jika harga naik ke atas top FVG
                if high[t] >= fvg["top"]:
                    continue
            
            still_active.append(fvg)
        
        active_fvgs = still_active
        
        # Hitung FVG status: jarak ke FVG terdekat / ATR
        if len(active_fvgs) > 0:
            nearest_dist = float("inf")
            nearest_dir = 0
            current_close = close[t]
            
            for fvg in active_fvgs:
                mid = 0.5 * (fvg["top"] + fvg["bottom"])
                dist = abs(current_close - mid)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_dir = fvg["direction"]
            
            # Signed: positif = bullish FVG terdekat, negatif = bearish
            fvg_status[t] = nearest_dir * (1.0 - min(nearest_dist / current_atr, 3.0) / 3.0)
        else:
            fvg_status[t] = 0.0
    
    return pd.Series(fvg_status, index=df.index, name="fvg_status")


def build_structural_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Membangun Channel 8-9 (structural market features).
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan OHLC.
    
    Returns
    -------
    pd.DataFrame
        DataFrame dengan kolom baru: liquidity_distance, fvg_status
    """
    df = df.copy()
    
    # Detect fractals
    frac_highs = detect_fractal_highs(df["high"])
    frac_lows = detect_fractal_lows(df["low"])
    
    # Channel 8: Liquidity distance
    df["liquidity_distance"] = compute_liquidity_distance(df, frac_highs, frac_lows)
    
    # Channel 9: FVG status
    df["fvg_status"] = detect_fvg(df)
    
    return df
