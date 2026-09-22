"""
XAU_DEEP_SNIPER — Pipeline Configuration & Constants
=====================================================
Semua konstanta, skema kolom, parameter validasi, dan tabel DST
didefinisikan di satu tempat untuk menghindari magic numbers tersebar.
"""

from typing import Dict, List, Tuple

# =============================================================================
# 1. RAW DATA SCHEMA
# =============================================================================
RAW_COLUMNS: List[str] = [
    "timestamp_utc",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "spread",
]

RAW_COLUMNS_REQUIRED: List[str] = [
    "timestamp_utc",
    "open",
    "high",
    "low",
    "close",
    "volume",
]

# Kolom spread bersifat opsional; jika tidak tersedia, akan diisi
# dengan model spread sintetis berdasarkan sesi waktu.
SPREAD_OPTIONAL: bool = True

# =============================================================================
# 2. ANOMALY DETECTION THRESHOLDS
# =============================================================================

# Flat candle: |high - low| < FLAT_EPSILON dan volume == 0
FLAT_EPSILON: float = 0.01  # $0.01 untuk XAU/USD

# Consecutive flat bars threshold untuk flag sebagai suspected data gap
FLAT_CONSECUTIVE_THRESHOLD: int = 5

# Bad tick: range > BAD_TICK_ATR_MULTIPLIER * ATR(BAD_TICK_ATR_PERIOD)
BAD_TICK_ATR_MULTIPLIER: float = 5.0
BAD_TICK_ATR_PERIOD: int = 14

# Percentile untuk clamping bad tick high/low
BAD_TICK_CLAMP_PERCENTILE: float = 0.995  # 99.5th percentile
BAD_TICK_CLAMP_WINDOW: int = 50  # Window bar untuk kalkulasi percentile

# Volume threshold: bad tick hanya jika volume < median volume
BAD_TICK_VOLUME_PERIOD: int = 14

# =============================================================================
# 3. TIMEFRAME & TRADING CALENDAR
# =============================================================================

TIMEFRAME_MINUTES: int = 30
BARS_PER_DAY_EXPECTED: int = 48  # 24 jam * 2 bar/jam
BARS_PER_DAY_MIN_VALID: int = 40  # Di bawah ini = incomplete trading day

# Weekend: XAU/USD market tutup Sabtu-Minggu
WEEKEND_DAYS: List[int] = [5, 6]  # Saturday=5, Sunday=6 (datetime.weekday())

# Hari libur bursa utama (bulan, hari) — bar di tanggal ini di-flag
MARKET_HOLIDAYS: List[Tuple[int, int]] = [
    (12, 25),  # Christmas Day
    (1, 1),    # New Year's Day
]

# =============================================================================
# 4. DST TRANSITION RULES (US & UK)
# =============================================================================
# US DST: Minggu ke-2 Maret (Spring Forward), Minggu ke-1 November (Fall Back)
# UK DST: Minggu terakhir Maret (Spring Forward), Minggu terakhir Oktober (Fall Back)
#
# Dampak pada rollover hour:
#   - Saat US DST aktif: rollover = 21:00 UTC
#   - Saat US DST tidak aktif: rollover = 22:00 UTC
#
# Perhitungan DST dilakukan secara dinamis di dst_harmonizer.py
# menggunakan pytz/zoneinfo, BUKAN tabel statis.

ROLLOVER_HOUR_DST_ACTIVE: int = 21    # UTC, saat US DST aktif
ROLLOVER_HOUR_DST_INACTIVE: int = 22  # UTC, saat US DST tidak aktif
ROLLOVER_QUARANTINE_DURATION_HOURS: int = 1  # 1 jam quarantine

# Timezone references untuk kalkulasi DST
TZ_US_EASTERN: str = "US/Eastern"
TZ_UK_LONDON: str = "Europe/London"

# =============================================================================
# 5. SYNTHETIC SPREAD MODEL (digunakan jika spread historis tidak tersedia)
# =============================================================================
# Spread dalam pips; 1 pip XAU/USD = $0.10
SYNTHETIC_SPREAD: Dict[str, float] = {
    "asian":    3.0,   # 00:00 - 07:00 UTC (Tokyo)
    "london":   2.5,   # 07:00 - 13:00 UTC (London)
    "overlap":  2.5,   # 13:00 - 17:00 UTC (London + NY overlap)
    "newyork":  2.8,   # 17:00 - 21:00 UTC (NY only)
    "rollover": 5.0,   # 21:00 - 22:00 UTC (spread spike)
}

# =============================================================================
# 6. OUTPUT PATHS
# =============================================================================
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"

RAW_CSV_FILENAME = "xauusd_m30_raw.csv"
CLEAN_PARQUET_FILENAME = "xauusd_m30_clean.parquet"
FEATURES_PARQUET_FILENAME = "xauusd_m30_features.parquet"
TRAIN_PARQUET_FILENAME = "xauusd_m30_train.parquet"
TEST_PARQUET_FILENAME = "xauusd_m30_test.parquet"
FEATURE_REPORT_FILENAME = "feature_quality_report.json"

# Parquet compression
PARQUET_COMPRESSION = "snappy"

# =============================================================================
# 7. FLAG COLUMNS (ditambahkan saat cleaning)
# =============================================================================
FLAG_COLUMNS: List[str] = [
    "is_weekend",
    "is_rollover_quarantine",
    "is_flat_candle",
    "is_bad_tick",
    "is_news_blackout",    # Akan diisi di TAHAP 2/3
    "entry_eligible",
]
