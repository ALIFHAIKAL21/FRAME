"""
XAU_DEEP_SNIPER — Data Ingestion Module
========================================
Memuat data mentah CSV ke DataFrame dengan validasi skema ketat.
Tidak ada transformasi fitur di sini — hanya load, parse, dan validasi integritas.
"""

import pandas as pd
import pathlib
from typing import Optional, List

from . import config


class SchemaValidationError(Exception):
    """Raised ketika data mentah gagal validasi skema."""
    pass


def load_raw_csv(
    filepath: pathlib.Path,
    timestamp_col: str = "timestamp_utc",
    datetime_format: Optional[str] = None,
    separator: str = ",",
) -> pd.DataFrame:
    """
    Memuat file CSV data mentah XAU/USD M30.

    Parameters
    ----------
    filepath : pathlib.Path
        Path ke file CSV.
    timestamp_col : str
        Nama kolom timestamp di CSV sumber. Akan di-rename ke 'timestamp_utc'.
    datetime_format : str, optional
        Format strftime untuk parsing timestamp. None = auto-detect.
    separator : str
        Delimiter CSV.

    Returns
    -------
    pd.DataFrame
        DataFrame dengan kolom sesuai skema RAW_COLUMNS.

    Raises
    ------
    SchemaValidationError
        Jika validasi skema gagal.
    FileNotFoundError
        Jika file CSV tidak ditemukan.
    """
    filepath = pathlib.Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File CSV tidak ditemukan: {filepath}")

    # Load CSV
    df = pd.read_csv(
        filepath,
        sep=separator,
        parse_dates=[timestamp_col] if datetime_format is None else False,
    )

    # Jika format datetime spesifik, parse manual
    if datetime_format is not None:
        df[timestamp_col] = pd.to_datetime(df[timestamp_col], format=datetime_format)

    # Rename timestamp column ke standar
    if timestamp_col != "timestamp_utc":
        df = df.rename(columns={timestamp_col: "timestamp_utc"})

    # Localize ke UTC jika belum tz-aware
    if df["timestamp_utc"].dt.tz is None:
        df["timestamp_utc"] = df["timestamp_utc"].dt.tz_localize("UTC")
    else:
        df["timestamp_utc"] = df["timestamp_utc"].dt.tz_convert("UTC")

    # Validasi kolom wajib
    _validate_required_columns(df)

    # Tambah kolom spread jika tidak ada
    if "spread" not in df.columns:
        df["spread"] = float("nan")  # Akan diisi oleh synthetic spread model nanti

    # Pilih dan urutkan kolom sesuai skema
    df = df[config.RAW_COLUMNS].copy()

    # Validasi tipe dan integritas data
    _validate_data_integrity(df)

    # Sort by timestamp dan reset index
    df = df.sort_values("timestamp_utc").reset_index(drop=True)

    return df


def _validate_required_columns(df: pd.DataFrame) -> None:
    """Validasi bahwa semua kolom wajib ada."""
    missing = set(config.RAW_COLUMNS_REQUIRED) - set(df.columns)
    if missing:
        raise SchemaValidationError(
            f"Kolom wajib tidak ditemukan: {missing}. "
            f"Kolom yang tersedia: {list(df.columns)}"
        )


def _validate_data_integrity(df: pd.DataFrame) -> None:
    """
    Validasi integritas data:
    - Harga > 0
    - High >= max(Open, Close)
    - Low <= min(Open, Close)
    - Volume >= 0
    - Timestamp monotonic (tidak ada duplikat)
    """
    errors: List[str] = []

    # Harga positif
    for col in ["open", "high", "low", "close"]:
        invalid_count = (df[col] <= 0).sum()
        if invalid_count > 0:
            errors.append(f"{col}: {invalid_count} baris memiliki harga <= 0")

    # High >= max(Open, Close)
    high_violation = (df["high"] < df[["open", "close"]].max(axis=1)).sum()
    if high_violation > 0:
        errors.append(
            f"high < max(open, close) pada {high_violation} baris — "
            f"indikasi data corrupt"
        )

    # Low <= min(Open, Close)
    low_violation = (df["low"] > df[["open", "close"]].min(axis=1)).sum()
    if low_violation > 0:
        errors.append(
            f"low > min(open, close) pada {low_violation} baris — "
            f"indikasi data corrupt"
        )

    # Volume non-negatif
    vol_negative = (df["volume"] < 0).sum()
    if vol_negative > 0:
        errors.append(f"volume < 0 pada {vol_negative} baris")

    # Timestamp duplikat
    dup_count = df["timestamp_utc"].duplicated().sum()
    if dup_count > 0:
        errors.append(f"{dup_count} timestamp duplikat ditemukan")

    if errors:
        error_msg = "Data integrity validation GAGAL:\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        raise SchemaValidationError(error_msg)


def validate_timestamp_monotonicity(df: pd.DataFrame) -> dict:
    """
    Memeriksa apakah timestamp strictly monotonic increasing
    dan mendeteksi gap (bar yang hilang).

    Returns
    -------
    dict
        {
            "is_monotonic": bool,
            "total_bars": int,
            "expected_intervals": int,  # jumlah interval 30-menit yang diharapkan
            "gaps": List[dict],  # [{from_ts, to_ts, missing_bars}, ...]
        }
    """
    ts = df["timestamp_utc"].sort_values().reset_index(drop=True)
    diffs = ts.diff().dropna()

    expected_delta = pd.Timedelta(minutes=config.TIMEFRAME_MINUTES)

    # Deteksi gap: interval > 30 menit yang bukan weekend
    gaps = []
    for idx in diffs[diffs > expected_delta].index:
        from_ts = ts.iloc[idx - 1]
        to_ts = ts.iloc[idx]
        gap_minutes = (to_ts - from_ts).total_seconds() / 60
        missing_bars = int(gap_minutes / config.TIMEFRAME_MINUTES) - 1

        # Abaikan gap weekend (Jumat 21:00-22:00 UTC -> Minggu 21:00-22:00 UTC)
        if from_ts.weekday() == 4 and to_ts.weekday() == 6:
            continue  # Weekend gap normal
        if from_ts.weekday() == 4 and to_ts.weekday() == 0:
            continue  # Weekend gap (Jumat -> Senin)

        gaps.append({
            "from_ts": str(from_ts),
            "to_ts": str(to_ts),
            "gap_minutes": gap_minutes,
            "missing_bars_estimate": missing_bars,
        })

    return {
        "is_monotonic": ts.is_monotonic_increasing,
        "total_bars": len(df),
        "gaps_detected": len(gaps),
        "gaps": gaps[:50],  # Limit output untuk readability
    }
