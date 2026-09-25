"""
FLOWDEV FRAME - Core Architecture Package
Flowdev Recurrent Algorithmic Model for Trade Execution (FRAME)
Emblem: The Cyber-Neural Peregrine Falcon
"""

__version__ = "1.0.0-PROD"
__author__ = "Flowdev / ALIFHAIKAL21"
__identity__ = "FRAME (Flowdev Recurrent Algorithmic Model for Trade Execution)"

from .constants import (
    INITIAL_EQUITY,
    FIXED_LOT,
    PAIR,
    TIMEFRAME,
    CONTRACT_SIZE,
    COMMISSION_PER_LOT,
    SPREAD_PIPS,
    SLIPPAGE_PIPS,
    TOTAL_FRICTION_USD,
    SL_ATR_MULT,
    TP_MAX_R,
    BE_TRIGGER_R,
    BE_BUFFER_PRICE,
    RATCHET_12_R,
    TRAIL_TRIGGER_R,
    TRAIL_DIST_R,
    STALE_DECAY_BARS,
    STALE_DECAY_SL_R,
    MAX_HOLD_BARS,
    TAU_BASE,
    UNCERTAINTY_MARGIN,
    SESSION_WINDOWS_UTC,
    WEEKEND_SHIELD_NO_ENTRY_HOUR_UTC,
    WEEKEND_SHIELD_FORCE_CLOSE_HOUR_UTC,
)
from .banner import print_frame_banner, get_frame_banner_text

__all__ = [
    "__version__",
    "__identity__",
    "INITIAL_EQUITY",
    "FIXED_LOT",
    "PAIR",
    "TIMEFRAME",
    "CONTRACT_SIZE",
    "COMMISSION_PER_LOT",
    "SPREAD_PIPS",
    "SLIPPAGE_PIPS",
    "TOTAL_FRICTION_USD",
    "SL_ATR_MULT",
    "TP_MAX_R",
    "BE_TRIGGER_R",
    "BE_BUFFER_PRICE",
    "RATCHET_12_R",
    "TRAIL_TRIGGER_R",
    "TRAIL_DIST_R",
    "STALE_DECAY_BARS",
    "STALE_DECAY_SL_R",
    "MAX_HOLD_BARS",
    "TAU_BASE",
    "UNCERTAINTY_MARGIN",
    "SESSION_WINDOWS_UTC",
    "WEEKEND_SHIELD_NO_ENTRY_HOUR_UTC",
    "WEEKEND_SHIELD_FORCE_CLOSE_HOUR_UTC",
    "print_frame_banner",
    "get_frame_banner_text",
]
