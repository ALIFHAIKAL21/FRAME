"""
XAU_DEEP_SNIPER - Feature Engineering Configuration (TAHAP 2)
==============================================================
Semua hyperparameter, window lengths, dan channel definitions
untuk fitur scale-free didefinisikan di sini.
"""

from typing import Dict, List

# =============================================================================
# 1. STATIONARITY TRANSFORM PARAMETERS
# =============================================================================

# EMA period untuk price detrending (sesuai spec BAB 3.1)
EMA_DETREND_PERIOD: int = 64

# ATR period untuk normalisasi (sesuai spec BAB 3.1)
ATR_NORMALIZE_PERIOD: int = 64

# Volume z-score rolling window (sesuai spec BAB 3.1)
VOLUME_ZSCORE_WINDOW: int = 128

# Epsilon kecil untuk menghindari division by zero
EPSILON: float = 1e-8

# =============================================================================
# 2. SMI (STOCHASTIC MOMENTUM INDEX) PARAMETERS (sesuai spec BAB 3.2)
# =============================================================================
SMI_LOOKBACK: int = 14       # Period lookback untuk highest-high / lowest-low
SMI_FIRST_EMA: int = 3       # First EMA smoothing period
SMI_SECOND_EMA: int = 3      # Second EMA smoothing period
SMI_SIGNAL_EMA: int = 3      # Signal line EMA (opsional, untuk diferensial)

# =============================================================================
# 3. MOVING AVERAGE RIBBON PARAMETERS (sesuai spec BAB 3.2 Channel 7)
# =============================================================================
MA_RIBBON_PERIODS: List[int] = [8, 13, 21, 34, 55]  # Fibonacci-based
MA_RIBBON_SLOPE_WINDOW: int = 5  # Window untuk menghitung slope

# =============================================================================
# 4. LIQUIDITY POOL (FRACTAL SWING) PARAMETERS (spec BAB 3.2 Channel 8)
# =============================================================================
FRACTAL_WINDOW: int = 5  # Williams Fractal: 5-bar pattern (2 kiri, 2 kanan)
LIQUIDITY_LOOKBACK: int = 64  # Jumlah bar lookback untuk fractal swing terdekat

# =============================================================================
# 5. FVG / ORDER BLOCK PARAMETERS (spec BAB 3.2 Channel 9)
# =============================================================================
FVG_MIN_GAP_ATR_RATIO: float = 0.3  # Minimum gap size relatif terhadap ATR
FVG_EXPIRY_BARS: int = 96  # FVG dianggap expired setelah N bar jika belum mitigated
OB_LOOKBACK: int = 64  # Lookback untuk mendeteksi order blocks

# =============================================================================
# 6. INPUT WINDOW FOR MOMENT-1-LARGE
# =============================================================================
# Spec BAB 3.2: L = 64 bar M30 (t-63 hingga t)
# Namun MOMENT-1-large native window = 512 timesteps
# Kita gunakan 64 bar sebagai feature window, tapi padding ke 512 jika perlu
FEATURE_WINDOW: int = 64       # Lookback untuk feature calculation
MODEL_INPUT_LENGTH: int = 512  # MOMENT-1-large native sequence length

# =============================================================================
# 7. CHANNEL DEFINITIONS (spec BAB 3.2)
# =============================================================================
FEATURE_CHANNELS: Dict[int, str] = {
    0: "ohlc_norm_open",      # Channel 1: Open normalized (EMA/ATR)
    1: "ohlc_norm_high",      # Channel 2: High normalized
    2: "ohlc_norm_low",       # Channel 3: Low normalized
    3: "ohlc_norm_close",     # Channel 4: Close normalized
    4: "volume_zscore",       # Channel 5: Volume dynamic Z-score
    5: "smi",                 # Channel 6: Stochastic Momentum Index
    6: "ma_ribbon_slope",     # Channel 7: MA Ribbon slope/differential
    7: "liquidity_distance",  # Channel 8: Distance to nearest liquidity pool
    8: "fvg_status",          # Channel 9: FVG/Order Block status
}

NUM_CHANNELS: int = len(FEATURE_CHANNELS)  # = 9

# =============================================================================
# 8. TEMPORAL SPLIT PARAMETERS (spec BAB 6.1)
# =============================================================================
# In-sample: 4 tahun pertama (80%), Out-of-sample: 1 tahun terakhir (20%)
TRAIN_RATIO: float = 0.80
PURGE_BARS: int = 16   # Triple barrier horizon (16 bar M30 = 8 jam)
EMBARGO_BARS: int = 48  # 48 bar = 24 jam, memutus korelasi serial
WALK_FORWARD_FOLDS: int = 5
