"""
XAU_DEEP_SNIPER — DST Harmonizer Module
========================================
Menghitung jam rollover broker secara dinamis berdasarkan kalender DST
historis US Eastern (New York). Menggunakan pytz/zoneinfo untuk akurasi
penuh — BUKAN tabel statis yang rentan terhadap perubahan aturan DST.

Logika Inti:
- Rollover broker XAU/USD terjadi pada 17:00 New York Time.
- Dalam UTC: 21:00 (saat US DST aktif) atau 22:00 (saat US DST tidak aktif).
- Bar yang jatuh di zona rollover +-1 jam di-flag sebagai quarantine zone.
"""

import pandas as pd
import pytz
from datetime import datetime, date
from typing import Tuple

from . import config


def get_rollover_hour_utc(target_date: date) -> int:
    """
    Menghitung jam rollover broker dalam UTC untuk tanggal tertentu.

    Rollover terjadi pada 17:00 US/Eastern:
    - Saat EDT (DST aktif): 17:00 EDT = 21:00 UTC
    - Saat EST (DST tidak aktif): 17:00 EST = 22:00 UTC

    Parameters
    ----------
    target_date : date
        Tanggal yang ingin dihitung jam rollovernya.

    Returns
    -------
    int
        Jam rollover dalam UTC (21 atau 22).
    """
    tz_eastern = pytz.timezone(config.TZ_US_EASTERN)

    # Buat datetime 17:00 di timezone Eastern untuk tanggal tersebut
    naive_dt = datetime(target_date.year, target_date.month, target_date.day, 17, 0, 0)
    local_dt = tz_eastern.localize(naive_dt)

    # Convert ke UTC dan ambil jam
    utc_dt = local_dt.astimezone(pytz.utc)
    return utc_dt.hour


def is_dst_active_us(target_date: date) -> bool:
    """
    Memeriksa apakah US DST aktif pada tanggal tertentu.

    Returns
    -------
    bool
        True jika DST aktif (EDT), False jika tidak (EST).
    """
    tz_eastern = pytz.timezone(config.TZ_US_EASTERN)
    naive_dt = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0)
    local_dt = tz_eastern.localize(naive_dt)
    return bool(local_dt.dst())


def is_dst_active_uk(target_date: date) -> bool:
    """
    Memeriksa apakah UK DST (BST) aktif pada tanggal tertentu.

    Returns
    -------
    bool
        True jika BST aktif, False jika GMT.
    """
    tz_london = pytz.timezone(config.TZ_UK_LONDON)
    naive_dt = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0)
    local_dt = tz_london.localize(naive_dt)
    return bool(local_dt.dst())


def get_session_boundaries_utc(target_date: date) -> dict:
    """
    Mengembalikan batas-batas sesi trading dalam UTC untuk tanggal tertentu,
    dengan koreksi DST.

    Returns
    -------
    dict
        {
            "asian_start": int,     # UTC hour
            "london_start": int,    # 7 (GMT) atau 6 (BST)
            "newyork_start": int,   # 13 (EST) atau 12 (EDT)
            "rollover_start": int,  # 21 (EDT) atau 22 (EST)
        }
    """
    uk_dst = is_dst_active_uk(target_date)
    us_dst = is_dst_active_us(target_date)

    return {
        "asian_start": 0,
        "london_start": 6 if uk_dst else 7,
        "newyork_start": 12 if us_dst else 13,
        "rollover_start": get_rollover_hour_utc(target_date),
    }


def flag_rollover_quarantine(df: pd.DataFrame) -> pd.Series:
    """
    Membuat boolean Series yang menandai bar-bar dalam zona rollover quarantine.

    Zona quarantine: [rollover_hour, rollover_hour + QUARANTINE_DURATION)

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan kolom 'timestamp_utc' (tz-aware UTC).

    Returns
    -------
    pd.Series
        Boolean series, True = bar berada di zona rollover quarantine.
    """
    flags = pd.Series(False, index=df.index, dtype=bool)

    # Vectorized: ambil date dan hour dari setiap timestamp
    dates = df["timestamp_utc"].dt.date
    hours = df["timestamp_utc"].dt.hour

    # Cache rollover hours per date unik untuk efisiensi
    unique_dates = dates.unique()
    rollover_map = {d: get_rollover_hour_utc(d) for d in unique_dates}

    # Map rollover hour ke setiap bar
    rollover_hours = dates.map(rollover_map)

    # Flag: bar berada di [rollover_hour, rollover_hour + duration)
    duration = config.ROLLOVER_QUARANTINE_DURATION_HOURS
    for offset in range(duration):
        flags = flags | (hours == (rollover_hours + offset) % 24)

    return flags


def add_session_labels(df: pd.DataFrame) -> pd.Series:
    """
    Menambahkan label sesi trading berdasarkan jam UTC dan DST aktif.
    Berguna untuk synthetic spread model.

    Returns
    -------
    pd.Series
        String series: 'asian', 'london', 'overlap', 'newyork', 'rollover'
    """
    sessions = pd.Series("asian", index=df.index, dtype="object")

    dates = df["timestamp_utc"].dt.date
    hours = df["timestamp_utc"].dt.hour

    unique_dates = dates.unique()
    boundaries_map = {d: get_session_boundaries_utc(d) for d in unique_dates}

    for idx in df.index:
        d = dates.iloc[idx] if hasattr(dates, 'iloc') else dates[idx]
        h = hours.iloc[idx] if hasattr(hours, 'iloc') else hours[idx]
        b = boundaries_map[d]

        rollover_end = (b["rollover_start"] + 1) % 24

        if b["rollover_start"] <= h < b["rollover_start"] + 1:
            sessions.iloc[idx] = "rollover"
        elif b["newyork_start"] <= h < b["rollover_start"]:
            # Sub-divide: overlap vs pure NY
            if b["london_start"] <= h < b["newyork_start"] + 4:
                sessions.iloc[idx] = "overlap"
            else:
                sessions.iloc[idx] = "newyork"
        elif b["london_start"] <= h < b["newyork_start"]:
            sessions.iloc[idx] = "london"
        else:
            sessions.iloc[idx] = "asian"

    return sessions
