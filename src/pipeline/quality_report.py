"""
XAU_DEEP_SNIPER — Quality Report Module
========================================
Menghasilkan laporan statistik audit kualitas data setelah cleaning.
Output berupa dict terstruktur dan teks laporan ke stdout/file.
"""

import pandas as pd
import json
import pathlib
from typing import Optional

from . import config


def generate_quality_report(df: pd.DataFrame) -> dict:
    """
    Menghasilkan laporan kualitas data komprehensif.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame setelah cleaning (dengan flag columns).

    Returns
    -------
    dict
        Laporan terstruktur.
    """
    report = {}

    # --- 1. Overview ---
    report["overview"] = {
        "total_bars": len(df),
        "date_range_start": str(df["timestamp_utc"].min()) if len(df) > 0 else None,
        "date_range_end": str(df["timestamp_utc"].max()) if len(df) > 0 else None,
        "total_trading_days": df["timestamp_utc"].dt.date.nunique() if len(df) > 0 else 0,
    }

    # Hitung duration dalam tahun
    if len(df) > 0:
        delta = df["timestamp_utc"].max() - df["timestamp_utc"].min()
        report["overview"]["duration_days"] = delta.days
        report["overview"]["duration_years"] = round(delta.days / 365.25, 2)

    # --- 2. Flag Distribution ---
    flag_cols = [c for c in config.FLAG_COLUMNS if c in df.columns]
    flag_stats = {}
    for col in flag_cols:
        count = df[col].sum()
        pct = (count / len(df) * 100) if len(df) > 0 else 0
        flag_stats[col] = {"count": int(count), "pct": round(pct, 3)}
    report["flag_distribution"] = flag_stats

    # --- 3. Bars Per Day Distribution ---
    if len(df) > 0:
        bars_per_day = df.groupby(df["timestamp_utc"].dt.date).size()
        report["bars_per_day"] = {
            "mean": round(float(bars_per_day.mean()), 2),
            "median": float(bars_per_day.median()),
            "min": int(bars_per_day.min()),
            "max": int(bars_per_day.max()),
            "std": round(float(bars_per_day.std()), 2),
            "days_below_40_bars": int((bars_per_day < config.BARS_PER_DAY_MIN_VALID).sum()),
            "days_with_48_bars": int((bars_per_day == config.BARS_PER_DAY_EXPECTED).sum()),
        }
    else:
        report["bars_per_day"] = {}

    # --- 4. OHLCV Statistics ---
    if len(df) > 0:
        report["price_stats"] = {
            "price_range": {
                "min_low": float(df["low"].min()),
                "max_high": float(df["high"].max()),
            },
            "bar_range_stats": {
                "mean": round(float((df["high"] - df["low"]).mean()), 4),
                "median": round(float((df["high"] - df["low"]).median()), 4),
                "max": round(float((df["high"] - df["low"]).max()), 4),
                "min": round(float((df["high"] - df["low"]).min()), 4),
            },
            "volume_stats": {
                "mean": round(float(df["volume"].mean()), 2),
                "median": round(float(df["volume"].median()), 2),
                "zero_volume_bars": int((df["volume"] == 0).sum()),
                "zero_volume_pct": round(float((df["volume"] == 0).sum() / len(df) * 100), 2),
            },
        }

    # --- 5. Spread Statistics ---
    if "spread" in df.columns and df["spread"].notna().sum() > 0:
        spread_data = df["spread"].dropna()
        report["spread_stats"] = {
            "has_real_spread": True,
            "mean": round(float(spread_data.mean()), 3),
            "median": round(float(spread_data.median()), 3),
            "max": round(float(spread_data.max()), 3),
            "min": round(float(spread_data.min()), 3),
        }
    else:
        report["spread_stats"] = {
            "has_real_spread": False,
            "note": "Spread tidak tersedia — akan menggunakan synthetic spread model",
        }

    # --- 6. Entry Eligibility Summary ---
    if "entry_eligible" in df.columns:
        eligible = df["entry_eligible"].sum()
        total = len(df)
        report["entry_eligibility"] = {
            "eligible_bars": int(eligible),
            "total_bars": total,
            "eligible_pct": round(eligible / total * 100, 2) if total > 0 else 0,
            "blocked_bars": total - int(eligible),
        }

    return report


def print_quality_report(report: dict) -> str:
    """
    Format laporan kualitas sebagai teks terstruktur.

    Returns
    -------
    str
        Laporan sebagai string terformat.
    """
    lines = []
    lines.append("=" * 72)
    lines.append("DATA QUALITY AUDIT REPORT — XAU/USD M30")
    lines.append("=" * 72)

    # Overview
    ov = report.get("overview", {})
    lines.append(f"\nTotal Bars           : {ov.get('total_bars', 'N/A')}")
    lines.append(f"Date Range           : {ov.get('date_range_start', '?')} -> {ov.get('date_range_end', '?')}")
    lines.append(f"Trading Days         : {ov.get('total_trading_days', 'N/A')}")
    lines.append(f"Duration             : {ov.get('duration_days', '?')} days ({ov.get('duration_years', '?')} years)")

    # Bars per day
    bpd = report.get("bars_per_day", {})
    if bpd:
        lines.append(f"\n--- Bars Per Day ---")
        lines.append(f"  Mean / Median      : {bpd.get('mean', '?')} / {bpd.get('median', '?')}")
        lines.append(f"  Min / Max          : {bpd.get('min', '?')} / {bpd.get('max', '?')}")
        lines.append(f"  Days < 40 bars     : {bpd.get('days_below_40_bars', '?')}")
        lines.append(f"  Days == 48 bars    : {bpd.get('days_with_48_bars', '?')}")

    # Flag distribution
    flags = report.get("flag_distribution", {})
    if flags:
        lines.append(f"\n--- Flag Distribution ---")
        for flag, stats in flags.items():
            lines.append(f"  {flag:30s}: {stats['count']:>6d} ({stats['pct']:.3f}%)")

    # Entry eligibility
    ee = report.get("entry_eligibility", {})
    if ee:
        lines.append(f"\n--- Entry Eligibility ---")
        lines.append(f"  Eligible           : {ee.get('eligible_bars', '?')} / {ee.get('total_bars', '?')} ({ee.get('eligible_pct', '?')}%)")
        lines.append(f"  Blocked            : {ee.get('blocked_bars', '?')}")

    # Price stats
    ps = report.get("price_stats", {})
    if ps:
        pr = ps.get("price_range", {})
        br = ps.get("bar_range_stats", {})
        vs = ps.get("volume_stats", {})
        lines.append(f"\n--- Price & Volume ---")
        lines.append(f"  Price Range        : ${pr.get('min_low', '?')} - ${pr.get('max_high', '?')}")
        lines.append(f"  Bar Range (mean)   : ${br.get('mean', '?')}")
        lines.append(f"  Zero Volume Bars   : {vs.get('zero_volume_bars', '?')} ({vs.get('zero_volume_pct', '?')}%)")

    # Spread
    ss = report.get("spread_stats", {})
    lines.append(f"\n--- Spread ---")
    if ss.get("has_real_spread"):
        lines.append(f"  Mean / Median      : {ss.get('mean', '?')} / {ss.get('median', '?')} pips")
    else:
        lines.append(f"  {ss.get('note', 'No spread data')}")

    lines.append("\n" + "=" * 72)

    text = "\n".join(lines)
    print(text)
    return text


def save_quality_report(report: dict, filepath: Optional[pathlib.Path] = None) -> pathlib.Path:
    """
    Simpan laporan sebagai JSON ke reports/.

    Returns
    -------
    pathlib.Path
        Path ke file laporan yang disimpan.
    """
    if filepath is None:
        config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath = config.REPORTS_DIR / "data_quality_report.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"[REPORT] Laporan disimpan ke: {filepath}")
    return filepath
