"""
XAU_DEEP_SNIPER — News Blackout Module
=======================================
Flag bar-bar yang jatuh dalam window ±N menit sekitar rilis
berita High-Impact USD/XAU (NFP, CPI, FOMC, PPI, GDP).

Prinsip:
- Tidak ada prediksi sentimen berita (dilarang per AGENTS.md)
- Hanya HARD GATE temporal: blackout window deterministik
- Window: 30 menit sebelum s/d 30 menit sesudah rilis (default)
- FOMC: 60 menit window karena press conference

Data source: data/raw/high_impact_calendar.csv
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional


CALENDAR_PATH = Path(__file__).parent.parent.parent / "data" / "raw" / "high_impact_calendar.csv"


def load_event_calendar(calendar_path: Optional[Path] = None) -> pd.DataFrame:
    path = calendar_path or CALENDAR_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Economic calendar tidak ditemukan: {path}\n"
            "Buat dulu dengan script generate_news_calendar.py"
        )
    df = pd.read_csv(path)
    # Parse datetime UTC
    df["event_utc"] = pd.to_datetime(
        df["date"] + " " + df["time_utc"], utc=True
    )
    return df


def flag_news_blackout(
    df: pd.DataFrame,
    calendar_path: Optional[Path] = None,
    default_window_minutes: int = 30,
) -> pd.Series:
    """
    Tandai bar-bar dalam window blackout sekitar rilis berita high-impact.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame dengan kolom 'timestamp_utc' (tz-aware UTC).
    calendar_path : Path, optional
        Path ke CSV kalender. Default ke data/raw/high_impact_calendar.csv.
    default_window_minutes : int
        Window default sebelum dan sesudah event (menit).

    Returns
    -------
    pd.Series
        Boolean series: True = bar dalam zona blackout.
    """
    events = load_event_calendar(calendar_path)
    ts = df["timestamp_utc"]

    # Pastikan timezone konsisten
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")

    blackout = pd.Series(False, index=df.index)

    for _, ev in events.iterrows():
        ev_time = ev["event_utc"]
        window_min = int(ev.get("window_minutes", default_window_minutes))

        delta = pd.Timedelta(minutes=window_min)
        start = ev_time - delta
        end   = ev_time + delta

        mask = (ts >= start) & (ts <= end)
        blackout |= mask

    return blackout


def get_blackout_stats(df: pd.DataFrame) -> dict:
    """Statistik singkat news blackout."""
    blackout = df.get("is_news_blackout", pd.Series(False, index=df.index))
    total    = len(df)
    flagged  = int(blackout.sum())
    return {
        "total_bars": total,
        "blackout_bars": flagged,
        "blackout_pct": round(flagged / total * 100, 2) if total > 0 else 0,
    }


# ─── Compatibility functions for run_labeling_pipeline.py ─────────────────────

def generate_high_impact_calendar(start_year: int = 2021, end_year: int = 2026) -> pd.DataFrame:
    """
    Load kalender high-impact events dari CSV, filter ke rentang tahun.
    Alias untuk kompatibilitas dengan run_labeling_pipeline.py.
    """
    events = load_event_calendar()
    mask = (
        (events["event_utc"].dt.year >= start_year) &
        (events["event_utc"].dt.year <= end_year)
    )
    return events[mask].copy().reset_index(drop=True)


def apply_news_blackout_gate(
    df: pd.DataFrame,
    events_df: Optional[pd.DataFrame] = None,
    blackout_minutes: int = 30,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Terapkan news blackout gate: set is_news_blackout dan update entry_eligible.
    Alias untuk kompatibilitas dengan run_labeling_pipeline.py.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame fitur dengan kolom timestamp_utc.
    events_df : pd.DataFrame, optional
        DataFrame kalender dari generate_high_impact_calendar().
        Jika None, load dari CSV default.
    blackout_minutes : int
        Window menit sebelum/sesudah event.
    verbose : bool
        Print statistik jika True.

    Returns
    -------
    pd.DataFrame
        DataFrame dengan is_news_blackout diperbarui dan entry_eligible di-recalc.
    """
    df = df.copy()
    ts = df["timestamp_utc"]
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")

    if events_df is None:
        events_df = load_event_calendar()

    blackout = pd.Series(False, index=df.index)
    for _, ev in events_df.iterrows():
        ev_time    = ev["event_utc"]
        win_min    = int(ev.get("window_minutes", blackout_minutes))
        delta      = pd.Timedelta(minutes=win_min)
        mask       = (ts >= ev_time - delta) & (ts <= ev_time + delta)
        blackout  |= mask

    df["is_news_blackout"] = blackout

    # Re-compute entry_eligible jika kolom flag lain sudah ada
    flag_cols = ["is_rollover_quarantine", "is_flat_candle", "is_bad_tick", "is_news_blackout"]
    existing  = [c for c in flag_cols if c in df.columns]
    if existing:
        df["entry_eligible"] = ~df[existing].any(axis=1)

    if verbose:
        nb  = int(blackout.sum())
        tot = len(df)
        print(f"      [NewsBlackout] Flagged {nb} bars ({nb/tot*100:.2f}%) as blackout")
        if "entry_eligible" in df.columns:
            elig = int(df["entry_eligible"].sum())
            print(f"      [NewsBlackout] Entry eligible: {elig}/{tot} ({elig/tot*100:.1f}%)")

    return df

