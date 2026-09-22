"""
XAU_DEEP_SNIPER - Net-Cost Realistic Triple Barrier Labeling (TAHAP 3B)
========================================================================
Sesuai spesifikasi BAB 4:
- 4.1: Simulasi Barrier Realistis (Net of Fees & Spread)
  * Barrier Stop Loss (SL): Di luar struktur Swing High/Low atau batas Order Block
  * Barrier Take Profit (TP): Ditetapkan pada +1.0R atau +2.0R bersih setelah spread dan komisi
  * Barrier Waktu: Maksimal K = 16 bar M30 (8 jam)
- 4.2: Definisi Kelas Target Diskrit
  * a = 0: HOLD / CHOP (Kondisi pasar tidak memiliki edge, atau hasil bersih trade <= 0)
  * a = 1: BUY Valid dengan rasio +1.0R bersih
  * a = 2: BUY Valid dengan rasio +2.0R bersih
  * a = 3: SELL Valid dengan rasio +1.0R bersih
  * a = 4: SELL Valid dengan rasio +2.0R bersih

PRINSIP DESAIN:
- Strict path dependency: Jika TP dan SL disentuh dalam bar yang sama, diasumsikan
  kena SL terlebih dahulu (worst-case institutional execution assumption).
- Semua biaya riil (spread per bar + komisi institusional) dipotong dari PnL.
- Vektorisasi penuh dengan NumPy sliding_window_view (kecepatan mikro-detik).
"""

import pandas as pd
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from typing import Dict, Tuple, Optional

# =============================================================================
# DEFAULT PARAMETERS
# =============================================================================
TIME_BARRIER_BARS: int = 16         # K = 16 bar M30 = 8 jam
COMMISSION_PER_OZ: float = 0.035     # $3.50 per 100 oz standard lot = $0.035/oz
DEFAULT_SPREAD_PIPS: float = 0.75   # 0.75 pips = $0.075/oz jika kolom spread kosong
PIP_SIZE: float = 0.10              # 1 pip XAU/USD = $0.10

# Structural SL bounds (dalam kelipatan ATR)
SWING_LOOKBACK: int = 16            # Lookback untuk mencari Swing High/Low
SL_BUFFER_ATR_RATIO: float = 0.2    # Buffer di luar swing (0.2 * ATR)
MIN_R_ATR_RATIO: float = 1.0        # Minimal risiko = 1.0 * ATR
MAX_R_ATR_RATIO: float = 3.5        # Maksimal risiko = 3.5 * ATR

ACTION_CLASSES: Dict[int, str] = {
    0: "HOLD",
    1: "BUY_1R",
    2: "BUY_2R",
    3: "SELL_1R",
    4: "SELL_2R",
}


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 64,
) -> pd.Series:
    """Average True Range Wilder."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Gunakan min_periods=1 agar aman saat unit testing pada data pendek
    atr = tr.ewm(span=period, min_periods=1, adjust=False).mean()
    return atr.replace(0.0, np.nan).bfill().ffill().fillna(1.0)


def compute_structural_risk(
    df: pd.DataFrame,
    swing_lookback: int = SWING_LOOKBACK,
    buffer_ratio: float = SL_BUFFER_ATR_RATIO,
    min_r_ratio: float = MIN_R_ATR_RATIO,
    max_r_ratio: float = MAX_R_ATR_RATIO,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Menghitung jarak risiko Stop Loss (R) struktural untuk BUY dan SELL.
    
    Untuk BUY:
      SL_raw = rolling_min(Low, lookback) - buffer * ATR
      R_buy = Entry_buy - SL_raw
      Dibatasi ke [min_r_ratio * ATR, max_r_ratio * ATR]
      
    Untuk SELL:
      SL_raw = rolling_max(High, lookback) + buffer * ATR
      R_sell = SL_raw - Entry_sell
      Dibatasi ke [min_r_ratio * ATR, max_r_ratio * ATR]
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    atr = compute_atr(high, low, close, period=64).bfill().values
    
    # Recent swings
    recent_low = low.rolling(window=swing_lookback, min_periods=1).min().values
    recent_high = high.rolling(window=swing_lookback, min_periods=1).max().values
    
    c = close.values
    
    # R untuk BUY
    sl_buy_raw = recent_low - (buffer_ratio * atr)
    r_buy_raw = c - sl_buy_raw
    r_buy = np.clip(r_buy_raw, min_r_ratio * atr, max_r_ratio * atr)
    
    # R untuk SELL
    sl_sell_raw = recent_high + (buffer_ratio * atr)
    r_sell_raw = sl_sell_raw - c
    r_sell = np.clip(r_sell_raw, min_r_ratio * atr, max_r_ratio * atr)
    
    return r_buy, r_sell


def label_triple_barrier(
    df: pd.DataFrame,
    time_barrier: int = TIME_BARRIER_BARS,
    commission_per_oz: float = COMMISSION_PER_OZ,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Menghasilkan label aksi 5-kelas net-of-cost menggunakan simulasi Triple Barrier.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan kolom OHLC, spread (opsional), entry_eligible (opsional).
    time_barrier : int
        Jumlah bar maksimum lookahead K (default 16 bar M30).
    commission_per_oz : float
        Biaya komisi per oz (default $0.035).
    verbose : bool
        Print statistik pelabelan.
        
    Returns
    -------
    pd.DataFrame
        DataFrame asli dengan kolom tambahan:
        - action: int {0, 1, 2, 3, 4}
        - action_name: str {'HOLD', 'BUY_1R', 'BUY_2R', 'SELL_1R', 'SELL_2R'}
        - buy_class: int {0, 1, 2}
        - sell_class: int {0, 3, 4}
        - r_buy: float
        - r_sell: float
    """
    n = len(df)
    K = time_barrier
    
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    
    # Hitung spread per bar dalam satuan dollar per oz
    if "spread" in df.columns and df["spread"].notna().any():
        spread_usd = df["spread"].fillna(DEFAULT_SPREAD_PIPS).values * PIP_SIZE
    else:
        spread_usd = np.full(n, DEFAULT_SPREAD_PIPS * PIP_SIZE)
        
    friction_cost = spread_usd + commission_per_oz
    
    # Hitung jarak risiko R struktural
    r_buy, r_sell = compute_structural_risk(df)
    
    # Entry prices
    entry_buy = close + (0.5 * spread_usd)
    entry_sell = close - (0.5 * spread_usd)
    
    # Barriers untuk BUY
    sl_buy = entry_buy - r_buy
    tp1_buy = entry_buy + r_buy + friction_cost
    tp2_buy = entry_buy + (2.0 * r_buy) + friction_cost
    
    # Barriers untuk SELL
    sl_sell = entry_sell + r_sell
    tp1_sell = entry_sell - r_sell - friction_cost
    tp2_sell = entry_sell - (2.0 * r_sell) - friction_cost
    
    # Output arrays
    buy_class = np.zeros(n, dtype=np.int32)
    sell_class = np.zeros(n, dtype=np.int32)
    action = np.zeros(n, dtype=np.int32)
    
    # Kita hanya bisa mengevaluasi bar t di mana ada K bar di depannya: t <= n - K - 1
    eval_n = n - K
    if eval_n <= 0:
        raise ValueError(f"Jumlah bar ({n}) harus lebih besar dari time_barrier ({K})")
    
    # Bentuk sliding window untuk harga masa depan t+1 s.d. t+K
    # Shape: (eval_n, K)
    high_future = sliding_window_view(high[1:], window_shape=K)[:eval_n]
    low_future = sliding_window_view(low[1:], window_shape=K)[:eval_n]
    close_future = sliding_window_view(close[1:], window_shape=K)[:eval_n]
    
    # =========================================================================
    # SIMULASI BUY (a = 1 atau a = 2)
    # =========================================================================
    tp2_b = tp2_buy[:eval_n, None]
    tp1_b = tp1_buy[:eval_n, None]
    sl_b = sl_buy[:eval_n, None]
    
    hit_tp2_buy = high_future >= tp2_b
    hit_tp1_buy = high_future >= tp1_b
    hit_sl_buy = low_future <= sl_b
    
    has_tp2_buy = hit_tp2_buy.any(axis=1)
    has_tp1_buy = hit_tp1_buy.any(axis=1)
    has_sl_buy = hit_sl_buy.any(axis=1)
    
    idx_tp2_buy = np.where(has_tp2_buy, np.argmax(hit_tp2_buy, axis=1), K + 1)
    idx_tp1_buy = np.where(has_tp1_buy, np.argmax(hit_tp1_buy, axis=1), K + 1)
    idx_sl_buy = np.where(has_sl_buy, np.argmax(hit_sl_buy, axis=1), K + 1)
    
    # BUY 2R: TP2 disentuh strictly sebelum SL
    win_buy_2r = (idx_tp2_buy < idx_sl_buy) & has_tp2_buy
    
    # BUY 1R: TP1 disentuh strictly sebelum SL (dan bukan 2R)
    win_buy_1r = (idx_tp1_buy < idx_sl_buy) & has_tp1_buy & (~win_buy_2r)
    
    # Time barrier expiration check: jika tidak menyentuh TP ataupun SL dalam K bar,
    # evaluasi close pada bar t+K
    neither_buy = (~has_tp1_buy) & (~has_sl_buy)
    exit_pnl_buy = close_future[:, -1] - entry_buy[:eval_n] - friction_cost[:eval_n]
    time_win_buy_2r = neither_buy & (exit_pnl_buy >= 2.0 * r_buy[:eval_n])
    time_win_buy_1r = neither_buy & (exit_pnl_buy >= 1.0 * r_buy[:eval_n]) & (~time_win_buy_2r)
    
    final_buy_2r = win_buy_2r | time_win_buy_2r
    final_buy_1r = win_buy_1r | time_win_buy_1r
    
    buy_class[:eval_n] = np.where(final_buy_2r, 2, np.where(final_buy_1r, 1, 0))
    
    # =========================================================================
    # SIMULASI SELL (a = 3 atau a = 4)
    # =========================================================================
    tp2_s = tp2_sell[:eval_n, None]
    tp1_s = tp1_sell[:eval_n, None]
    sl_s = sl_sell[:eval_n, None]
    
    hit_tp2_sell = low_future <= tp2_s
    hit_tp1_sell = low_future <= tp1_s
    hit_sl_sell = high_future >= sl_s
    
    has_tp2_sell = hit_tp2_sell.any(axis=1)
    has_tp1_sell = hit_tp1_sell.any(axis=1)
    has_sl_sell = hit_sl_sell.any(axis=1)
    
    idx_tp2_sell = np.where(has_tp2_sell, np.argmax(hit_tp2_sell, axis=1), K + 1)
    idx_tp1_sell = np.where(has_tp1_sell, np.argmax(hit_tp1_sell, axis=1), K + 1)
    idx_sl_sell = np.where(has_sl_sell, np.argmax(hit_sl_sell, axis=1), K + 1)
    
    # SELL 2R: TP2 disentuh strictly sebelum SL
    win_sell_2r = (idx_tp2_sell < idx_sl_sell) & has_tp2_sell
    
    # SELL 1R: TP1 disentuh strictly sebelum SL (dan bukan 2R)
    win_sell_1r = (idx_tp1_sell < idx_sl_sell) & has_tp1_sell & (~win_sell_2r)
    
    # Time barrier expiration check
    neither_sell = (~has_tp1_sell) & (~has_sl_sell)
    exit_pnl_sell = entry_sell[:eval_n] - close_future[:, -1] - friction_cost[:eval_n]
    time_win_sell_2r = neither_sell & (exit_pnl_sell >= 2.0 * r_sell[:eval_n])
    time_win_sell_1r = neither_sell & (exit_pnl_sell >= 1.0 * r_sell[:eval_n]) & (~time_win_sell_2r)
    
    final_sell_2r = win_sell_2r | time_win_sell_2r
    final_sell_1r = win_sell_1r | time_win_sell_1r
    
    sell_class[:eval_n] = np.where(final_sell_2r, 4, np.where(final_sell_1r, 3, 0))
    
    # =========================================================================
    # RESOLUSI AKSI GABUNGAN (COMBINED ACTION ARBITRATION)
    # =========================================================================
    # Prioritas: 2R > 1R > HOLD. Jika BUY dan SELL keduanya menang, pilih yang rasio tertinggi;
    # Jika seimbang (misal keduanya 1R dalam chop), default ke HOLD (0).
    for i in range(eval_n):
        b = buy_class[i]
        s = sell_class[i]
        
        if b == 2 and s != 4:
            action[i] = 2
        elif s == 4 and b != 2:
            action[i] = 4
        elif b == 1 and s == 0:
            action[i] = 1
        elif s == 3 and b == 0:
            action[i] = 3
        else:
            action[i] = 0  # Konflik atau HOLD
            
    # Penegakan Hard Gate: Jika bar TIDAK eligible (blackout / quarantine / bad tick),
    # aksi HARUS 0 (Hard Zero Entry).
    if "entry_eligible" in df.columns:
        ineligible_mask = ~df["entry_eligible"].values
        action[ineligible_mask] = 0
        buy_class[ineligible_mask] = 0
        sell_class[ineligible_mask] = 0
        
    # K bar terakhir tidak memiliki evaluasi lengkap -> set action = 0
    action[eval_n:] = 0
    buy_class[eval_n:] = 0
    sell_class[eval_n:] = 0
    
    df_out = df.copy()
    df_out["action"] = action
    df_out["action_name"] = [ACTION_CLASSES[a] for a in action]
    df_out["buy_class"] = buy_class
    df_out["sell_class"] = sell_class
    df_out["r_buy"] = r_buy
    df_out["r_sell"] = r_sell
    df_out["friction_cost"] = friction_cost
    
    if verbose:
        print(f"[LABELING] Triple Barrier Net-Cost Simulation (K={K} bars):")
        total_valid = eval_n
        counts = pd.Series(action[:eval_n]).value_counts().sort_index()
        for c_idx in range(5):
            cnt = counts.get(c_idx, 0)
            pct = cnt / total_valid * 100
            name = ACTION_CLASSES[c_idx]
            print(f"  Class {c_idx} ({name:7s}): {cnt:,} bars ({pct:.2f}%)")
            
    return df_out
