"""
XAU_DEEP_SNIPER - Structural Market Features (TAHAP 2C)
========================================================
Channel 10: Order Block Zone (+1 Inside Demand, -1 Inside Supply, 0 Neutral)
Channel 11: Liquidity Sweeps (+1 SSL Sweep Bull, -1 BSL Sweep Bear, 0 Neutral)
Channel 12: Valuation & Regime (Premium/Discount in [-1, +1] & Sideways Dynamics)

Sesuai spesifikasi AGENT.MD:
- Pola Supply, Demand, Support, Resistance, Liquidity
- Pengenalan kondisi Sideways (Mean Reversion) vs Trending
"""

import pandas as pd
import numpy as np

from . import feature_config as fcfg
from .features_core import compute_atr


def detect_fractal_highs(high: pd.Series, window: int = None) -> pd.Series:
    """Mendeteksi Williams Fractal Highs (causal with confirm delay)."""
    window = window or fcfg.FRACTAL_WINDOW
    half = window // 2
    n = len(high)
    is_high = pd.Series(False, index=high.index)
    h_arr = high.values
    for i in range(half, n - half):
        val = h_arr[i]
        left_max = h_arr[i - half:i].max() if i > 0 else -float("inf")
        right_max = h_arr[i + 1:i + half + 1].max() if i + half < n else -float("inf")
        if val > left_max and val > right_max:
            is_high.iloc[i] = True
    return is_high


def detect_fractal_lows(low: pd.Series, window: int = None) -> pd.Series:
    """Mendeteksi Williams Fractal Lows (causal with confirm delay)."""
    window = window or fcfg.FRACTAL_WINDOW
    half = window // 2
    n = len(low)
    is_low = pd.Series(False, index=low.index)
    l_arr = low.values
    for i in range(half, n - half):
        val = l_arr[i]
        left_min = l_arr[i - half:i].min() if i > 0 else float("inf")
        right_min = l_arr[i + 1:i + half + 1].min() if i + half < n else float("inf")
        if val < left_min and val < right_min:
            is_low.iloc[i] = True
    return is_low


def compute_market_structure_channels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Kalkulasi kausal Supply/Demand Order Blocks, Liquidity Sweeps, dan Valuation Regime.
    """
    n = len(df)
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    open_p = df["open"].values
    
    eps = fcfg.EPSILON
    atr = compute_atr(df["high"], df["low"], df["close"], fcfg.ATR_NORMALIZE_PERIOD).values
    
    frac_highs = detect_fractal_highs(df["high"]).values
    frac_lows = detect_fractal_lows(df["low"]).values
    
    confirm_delay = 2  # bar delay for 5-bar fractal
    
    order_block_zone = np.zeros(n, dtype=np.float32)
    liquidity_sweep = np.zeros(n, dtype=np.float32)
    valuation_regime = np.zeros(n, dtype=np.float32)
    liquidity_dist = np.zeros(n, dtype=np.float32)
    
    last_swing_high = float("nan")
    last_swing_low = float("nan")
    
    # Active Demand and Supply zones: list of (low, high)
    demand_zones = []
    supply_zones = []
    
    for t in range(n):
        cur_atr = max(atr[t], eps)
        
        # Check newly confirmed swing high/low at t - confirm_delay
        check_idx = t - confirm_delay
        if check_idx >= 0:
            if frac_highs[check_idx]:
                last_swing_high = high[check_idx]
                # Supply Zone: candle at swing high
                s_low = min(open_p[check_idx], close[check_idx])
                s_high = high[check_idx]
                supply_zones.append((s_low, s_high, check_idx))
            if frac_lows[check_idx]:
                last_swing_low = low[check_idx]
                # Demand Zone: candle at swing low
                d_low = low[check_idx]
                d_high = max(open_p[check_idx], close[check_idx])
                demand_zones.append((d_low, d_high, check_idx))
        
        # Clean expired or mitigated zones (mitigated if price penetrates through)
        cur_c = close[t]
        cur_h = high[t]
        cur_l = low[t]
        
        valid_demand = []
        in_demand = False
        for (dl, dh, c_idx) in demand_zones[-10:]:  # track recent 10 zones
            if cur_c < dl - 0.5 * cur_atr:
                continue  # broken
            valid_demand.append((dl, dh, c_idx))
            if dl <= cur_c <= dh + 0.25 * cur_atr:
                in_demand = True
        demand_zones = valid_demand
        
        valid_supply = []
        in_supply = False
        for (sl, sh, c_idx) in supply_zones[-10:]:
            if cur_c > sh + 0.5 * cur_atr:
                continue  # broken
            valid_supply.append((sl, sh, c_idx))
            if sl - 0.25 * cur_atr <= cur_c <= sh:
                in_supply = True
        supply_zones = valid_supply
        
        # 1. Order Block Zone Channel
        if in_demand and not in_supply:
            order_block_zone[t] = 1.0
        elif in_supply and not in_demand:
            order_block_zone[t] = -1.0
        else:
            order_block_zone[t] = 0.0
            
        # 2. Liquidity Sweep Detection (SSL / BSL)
        # Bull sweep: low dipped below last_swing_low, but close closed back above
        if not np.isnan(last_swing_low) and cur_l < last_swing_low and cur_c > last_swing_low:
            liquidity_sweep[t] = 1.0
        # Bear sweep: high poked above last_swing_high, but close closed back below
        elif not np.isnan(last_swing_high) and cur_h > last_swing_high and cur_c < last_swing_high:
            liquidity_sweep[t] = -1.0
        else:
            liquidity_sweep[t] = 0.0
            
        # 3. Valuation & Premium/Discount Regime
        if not np.isnan(last_swing_high) and not np.isnan(last_swing_low) and last_swing_high > last_swing_low:
            pd_ratio = (cur_c - last_swing_low) / (last_swing_high - last_swing_low)
            # Map [0, 1] to [-1.0, 1.0]: Discount is negative, Premium is positive
            val_norm = (pd_ratio - 0.5) * 2.0
            valuation_regime[t] = np.clip(val_norm, -1.0, 1.0)
            
            # Liquidity distance
            dist_high = abs(cur_c - last_swing_high)
            dist_low = abs(cur_c - last_swing_low)
            if dist_high <= dist_low:
                liquidity_dist[t] = np.clip((cur_c - last_swing_high) / cur_atr, -5.0, 5.0)
            else:
                liquidity_dist[t] = np.clip((cur_c - last_swing_low) / cur_atr, -5.0, 5.0)
        else:
            valuation_regime[t] = 0.0
            liquidity_dist[t] = 0.0
            
    res = pd.DataFrame(index=df.index)
    res["order_block_zone"] = order_block_zone
    res["liquidity_sweep"] = liquidity_sweep
    res["valuation_regime"] = valuation_regime
    res["liquidity_distance"] = liquidity_dist
    res["fvg_status"] = order_block_zone  # Backward compatibility
    
    return res


def build_structural_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Membangun Channel 10-12 (structural market features).
    """
    df = df.copy()
    struct_df = compute_market_structure_channels(df)
    for col in struct_df.columns:
        df[col] = struct_df[col]
    return df
