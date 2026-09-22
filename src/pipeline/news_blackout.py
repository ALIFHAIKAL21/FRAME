"""
XAU_DEEP_SNIPER - Hard Deterministic News Blackout Gate (TAHAP 3A)
===================================================================
Sesuai spesifikasi BAB 3.3:
- Pemanfaatan data kalender makro berstatus High-Impact (NFP, CPI, Keputusan FOMC).
- Variabel biner B_t in {0, 1} menandai interval T +- 30 menit dari waktu rilis.
- Selama B_t = 1, proses inferensi dimatikan secara deterministik (Hard Zero Entry),
  sehingga entry_eligible = False dan aksi otomatis = HOLD (Class 0).

PRINSIP DESAIN:
- Waktu rilis presisi dalam UTC, dikoreksi secara dinamis dengan kalender DST US.
- Mendukung pemuatan kalender eksternal jika ada file kalender tambahan.
- Built-in generator presisi untuk jadwal NFP, CPI, dan FOMC 2021-2026.
"""

import pandas as pd
import numpy as np
import pytz
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import pathlib

from . import config
from .dst_harmonizer import is_dst_active_us


# =============================================================================
# 1. BUILT-IN HIGH-IMPACT CALENDAR GENERATOR (2021 - 2026)
# =============================================================================

def _get_first_friday(year: int, month: int) -> date:
    """Mengembalikan tanggal Jumat pertama di bulan dan tahun tertentu (jadwal NFP)."""
    d = date(year, month, 1)
    # weekday: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4
    days_until_friday = (4 - d.weekday()) % 7
    return d + timedelta(days=days_until_friday)


def _get_cpi_release_date(year: int, month: int) -> date:
    """
    Mengembalikan perkiraan/tanggal rilis resmi CPI AS.
    Biasanya dirilis pada hari kerja kedua atau ketiga dari minggu kedua (sekitar tanggal 10-15).
    """
    # Cari hari Rabu di minggu kedua
    d = date(year, month, 8)
    days_until_wed = (2 - d.weekday()) % 7
    return d + timedelta(days=days_until_wed)


# Jadwal pertemuan FOMC historis & terkonfirmasi Federal Reserve (2021 - 2026)
FOMC_HISTORICAL_DATES: List[Tuple[int, int, int]] = [
    # 2021
    (2021, 1, 27), (2021, 3, 17), (2021, 4, 28), (2021, 6, 16),
    (2021, 7, 28), (2021, 9, 22), (2021, 11, 3), (2021, 12, 15),
    # 2022
    (2022, 1, 26), (2022, 3, 16), (2022, 5, 4),  (2022, 6, 15),
    (2022, 7, 27), (2022, 9, 21), (2022, 11, 2), (2022, 12, 14),
    # 2023
    (2023, 2, 1),  (2023, 3, 22), (2023, 5, 3),  (2023, 6, 14),
    (2023, 7, 26), (2023, 9, 20), (2023, 11, 1), (2023, 12, 13),
    # 2024
    (2024, 1, 31), (2024, 3, 20), (2024, 5, 1),  (2024, 6, 12),
    (2024, 7, 31), (2024, 9, 18), (2024, 11, 7), (2024, 12, 18),
    # 2025
    (2025, 1, 29), (2025, 3, 19), (2025, 5, 7),  (2025, 6, 18),
    (2025, 7, 30), (2025, 9, 17), (2025, 10, 29),(2025, 12, 10),
    # 2026
    (2026, 1, 28), (2026, 3, 18), (2026, 5, 6),  (2026, 6, 17),
    (2026, 7, 29), (2026, 9, 16), (2026, 11, 4), (2026, 12, 16),
]


def generate_high_impact_calendar(
    start_year: int = 2021,
    end_year: int = 2026,
) -> pd.DataFrame:
    """
    Menghasilkan kalender rilis ekonomi makro US High-Impact dengan waktu UTC presisi.
    
    Events:
    - NFP (Non-Farm Payrolls): 08:30 US Eastern
    - CPI (Consumer Price Index): 08:30 US Eastern
    - FOMC Rate Decision & Press Conference: 14:00 - 14:30 US Eastern
    
    Returns
    -------
    pd.DataFrame
        Kolom: timestamp_utc, event_name, impact, blackout_start, blackout_end
    """
    tz_eastern = pytz.timezone(config.TZ_US_EASTERN)
    events = []

    for yr in range(start_year, end_year + 1):
        for mo in range(1, 13):
            # 1. NFP
            nfp_d = _get_first_friday(yr, mo)
            nfp_dt = tz_eastern.localize(datetime(nfp_d.year, nfp_d.month, nfp_d.day, 8, 30, 0))
            nfp_utc = nfp_dt.astimezone(pytz.utc)
            events.append({
                "timestamp_utc": nfp_utc,
                "event_name": "US_NFP",
                "impact": "HIGH",
            })

            # 2. CPI
            cpi_d = _get_cpi_release_date(yr, mo)
            cpi_dt = tz_eastern.localize(datetime(cpi_d.year, cpi_d.month, cpi_d.day, 8, 30, 0))
            cpi_utc = cpi_dt.astimezone(pytz.utc)
            events.append({
                "timestamp_utc": cpi_utc,
                "event_name": "US_CPI",
                "impact": "HIGH",
            })

    # 3. FOMC Meetings
    for yr, mo, dy in FOMC_HISTORICAL_DATES:
        if start_year <= yr <= end_year:
            # Statement at 14:00 Eastern
            fomc_dt = tz_eastern.localize(datetime(yr, mo, dy, 14, 0, 0))
            fomc_utc = fomc_dt.astimezone(pytz.utc)
            events.append({
                "timestamp_utc": fomc_utc,
                "event_name": "US_FOMC_STATEMENT",
                "impact": "HIGH",
            })
            # Press Conference at 14:30 Eastern
            fomc_pc_dt = tz_eastern.localize(datetime(yr, mo, dy, 14, 30, 0))
            fomc_pc_utc = fomc_pc_dt.astimezone(pytz.utc)
            events.append({
                "timestamp_utc": fomc_pc_utc,
                "event_name": "US_FOMC_PRESS_CONF",
                "impact": "HIGH",
            })

    df_events = pd.DataFrame(events)
    df_events = df_events.sort_values("timestamp_utc").reset_index(drop=True)
    return df_events


# =============================================================================
# 2. BLACKOUT GATE APPLICATION
# =============================================================================

def flag_news_blackout(
    df: pd.DataFrame,
    events_df: Optional[pd.DataFrame] = None,
    blackout_minutes: int = 30,
) -> pd.Series:
    """
    Menandai bar M30 yang bersinggungan dengan jendela pengaman berita makro:
    
        [T_event - blackout_minutes, T_event + blackout_minutes]
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan kolom 'timestamp_utc' (tz-aware UTC).
    events_df : pd.DataFrame, optional
        DataFrame event dengan kolom 'timestamp_utc'. Jika None, menggunakan built-in calendar.
    blackout_minutes : int
        Ukuran jendela sebelum dan sesudah rilis (default 30 menit).
        
    Returns
    -------
    pd.Series
        Boolean series: True jika bar jatuh dalam jendela blackout.
    """
    if events_df is None:
        events_df = generate_high_impact_calendar()

    bar_ts = df["timestamp_utc"]
    bar_duration = timedelta(minutes=config.TIMEFRAME_MINUTES)
    buffer = timedelta(minutes=blackout_minutes)

    # Blackout flag per bar
    is_blackout = np.zeros(len(df), dtype=bool)

    # Filter events yang berada dalam rentang data bar
    min_bar_ts = bar_ts.min() - buffer
    max_bar_ts = bar_ts.max() + bar_duration + buffer

    relevant_events = events_df[
        (events_df["timestamp_utc"] >= min_bar_ts) &
        (events_df["timestamp_utc"] <= max_bar_ts)
    ]

    # Bar [t_start, t_end] bersinggungan dengan [T - buffer, T + buffer]
    # jika t_start <= T + buffer dan t_end >= T - buffer
    for ev_ts in relevant_events["timestamp_utc"]:
        if hasattr(ev_ts, "tzinfo") and ev_ts.tzinfo is None:
            ev_ts = ev_ts.tz_localize("UTC")
        elif not hasattr(ev_ts, "tzinfo"):
            ev_ts = pd.Timestamp(ev_ts, tz="UTC")
            
        window_start = ev_ts - buffer
        window_end = ev_ts + buffer

        # Bar start = timestamp_utc, Bar end = timestamp_utc + 30 min
        mask = (bar_ts <= window_end) & ((bar_ts + bar_duration) >= window_start)
        is_blackout |= mask.values

    return pd.Series(is_blackout, index=df.index, dtype=bool, name="is_news_blackout")


def apply_news_blackout_gate(
    df: pd.DataFrame,
    events_df: Optional[pd.DataFrame] = None,
    blackout_minutes: int = 30,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Menerapkan Hard Deterministic News Blackout Gate:
    1. Mengisi kolom 'is_news_blackout'
    2. Memperbarui 'entry_eligible': bar blackout DILARANG entry (Hard Zero Entry)
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame data bar (dengan timestamp_utc dan entry_eligible).
    events_df : pd.DataFrame, optional
        Custom calendar events.
    blackout_minutes : int
        Window size (default 30 min -> T +- 30m).
        
    Returns
    -------
    pd.DataFrame
        DataFrame dengan is_news_blackout dan entry_eligible yang ter-update.
    """
    df = df.copy()
    
    blackout_flags = flag_news_blackout(df, events_df=events_df, blackout_minutes=blackout_minutes)
    df["is_news_blackout"] = blackout_flags

    # Update entry eligibility:
    # entry_eligible = entry_eligible & (~is_news_blackout)
    if "entry_eligible" in df.columns:
        initial_eligible = df["entry_eligible"].sum()
        df["entry_eligible"] = df["entry_eligible"] & (~df["is_news_blackout"])
        final_eligible = df["entry_eligible"].sum()
    else:
        df["entry_eligible"] = ~df["is_news_blackout"]
        initial_eligible = len(df)
        final_eligible = df["entry_eligible"].sum()

    if verbose:
        blackout_count = df["is_news_blackout"].sum()
        blackout_pct = blackout_count / len(df) * 100
        print(f"[NEWS GATE] Macro News Blackout Applied (T +- {blackout_minutes} min):")
        print(f"  Total blackout bars : {blackout_count:,} ({blackout_pct:.2f}%)")
        print(f"  Entry eligible bars : {final_eligible:,} / {len(df):,} ({final_eligible/len(df)*100:.2f}%)")
        print(f"  Bar quarantined     : {initial_eligible - final_eligible:,} newly restricted bars")

    return df
