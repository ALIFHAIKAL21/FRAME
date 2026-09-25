"""
FLOWDEV FRAME - System Constants & Frozen Contract
Flowdev Recurrent Algorithmic Model for Trade Execution

All parameters in this file are FROZEN per the user contract documented in log.md.
Do not modify without formal out-of-sample audit verification.
"""

from typing import List, Tuple

# ==============================================================================
# 1. CAPITAL & EXECUTION SPECIFICATIONS (FROZEN)
# ==============================================================================
PAIR: str = "XAUUSD"
TIMEFRAME: str = "M30"
INITIAL_EQUITY: float = 500.00         # Fixed $500.00 USD
FIXED_LOT: float = 0.01                # Fixed 0.01 lot flat (no martingale/compounding)
CONTRACT_SIZE: float = 100.0           # 1 lot = 100 oz (0.01 lot = 1 oz, $1/dollar)

# Broker Friction Parameters
SPREAD_PIPS: float = 0.75              # 0.75 pip = $0.075 per 0.01 lot
SLIPPAGE_PIPS: float = 0.30            # 0.30 pip 2-way = $0.030 per 0.01 lot
COMMISSION_PER_LOT: float = 3.50       # $3.50 per standard lot = $0.035 per 0.01 lot
TOTAL_FRICTION_USD: float = 0.17       # Total realistic roundturn friction

# ==============================================================================
# 2. MODEL INFERENCE & GATING THRESHOLDS (FROZEN)
# ==============================================================================
SEQUENCE_LENGTH: int = 64              # 64 M30 bars lookback (32 hours)
NUM_CHANNELS: int = 15                 # 15 normalized input features
TAU_BASE: float = 0.32                 # Base confidence threshold
UNCERTAINTY_MARGIN: float = 0.01       # p_best - p_hold >= 0.01

# ==============================================================================
# 3. 4-STAGE ORDER MANAGEMENT SYSTEM (OMS) RULES (FROZEN)
# ==============================================================================
SL_ATR_MULT: float = 1.5               # Initial Stop Loss = 1.5 * ATR(14)
TP_MAX_R: float = 2.7                  # Max Take Profit ceiling (+2.7R)

# Stage 1: Positive Breakeven (+0.75R Micro-Breakeven Acceleration)
BE_TRIGGER_R: float = 0.75             # Move SL to Entry + buffer at +0.75R
BE_BUFFER_PRICE: float = 0.25          # $0.25 buffer (net profit +$0.08 after friction)

# Stage 2: Tiered Smart Ratchet (+1.2R)
RATCHET_TRIGGER_R: float = 1.2         # Lock guaranteed net profit at +1.2R
RATCHET_12_R: float = 0.5              # Lock SL at +0.5R (+~$5.50 - $9.00 net)

# Stage 3: Dynamic Trailing Stop (+1.5R+)
TRAIL_TRIGGER_R: float = 1.5           # Activate trailing stop when peak >= +1.5R
TRAIL_DIST_R: float = 0.6              # Trail distance 0.6R behind peak price

# Stage 4: Fast Stale Decay Protection (Momentum Half-Life)
STALE_DECAY_BARS: int = 6              # After 6 bars (3 hours) without BE trigger
STALE_DECAY_SL_R: float = -0.45        # Tighten initial SL from -1.0R to -0.45R (cut loss by 55%)
STALE_DECAY_R: float = 0.45            # Positive distance scalar for SL calculation

# Hard Time Barrier
MAX_HOLD_BARS: int = 12                # Force market close after 12 bars (6 hours)
TIME_BARRIER_BARS: int = 12            # Alias for OMS backtest loop

# ==============================================================================
# 4. INSTITUTIONAL LIQUIDITY SESSIONS & WEEKEND SHIELD (FROZEN)
# ==============================================================================
# 5 Institutional windows (UTC). Exactly 1 trade permitted per window.
SESSION_WINDOWS_UTC: List[Tuple[str, float, float]] = [
    ("Asia Early",  1.0,  4.0),         # 01:00 - 04:00 UTC (08:00 - 11:00 WIB)
    ("Asia Late",   4.5,  7.0),         # 04:30 - 07:00 UTC (11:30 - 14:00 WIB)
    ("London Core", 8.5, 12.5),         # 08:30 - 12:30 UTC (15:30 - 19:30 WIB)
    ("NY Open",    13.0, 17.0),         # 13:00 - 17:00 UTC (20:00 - 00:00 WIB)
    ("NY Core",    17.5, 21.0),         # 17:30 - 21:00 UTC (00:30 - 04:00 WIB)
]

# Blackout gap between 07:00 - 08:30 UTC (transition before London open)
BLACKOUT_PRE_LONDON_START_UTC: float = 7.0
BLACKOUT_PRE_LONDON_END_UTC: float = 8.5

# Weekend Shield
WEEKEND_SHIELD_NO_ENTRY_HOUR_UTC: float = 18.0  # Friday >= 18:00 UTC no new orders
WEEKEND_SHIELD_FORCE_CLOSE_HOUR_UTC: float = 20.0 # Friday >= 20:00 UTC auto closeout
