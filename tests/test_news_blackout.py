"""
XAU_DEEP_SNIPER - Unit Tests: News Blackout Gate (TAHAP 3A)
============================================================
Test suite untuk memverifikasi:
1. Calendar generation US High-Impact (NFP, CPI, FOMC)
2. Akurasi jadwal NFP (Jumat pertama) & FOMC
3. Blackout flag logic (T +- 30 min)
4. Hard zero-entry enforcement (entry_eligible = False)
"""

import sys
import pathlib
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import pytz

project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from pipeline.news_blackout import (
    generate_high_impact_calendar,
    flag_news_blackout,
    apply_news_blackout_gate,
    _get_first_friday,
)


class TestNewsCalendar:
    def test_calendar_not_empty(self):
        cal = generate_high_impact_calendar(2021, 2026)
        assert len(cal) > 150
        assert "timestamp_utc" in cal.columns
        assert "event_name" in cal.columns

    def test_nfp_is_always_friday(self):
        cal = generate_high_impact_calendar(2022, 2024)
        nfp_events = cal[cal["event_name"] == "US_NFP"]
        for _, row in nfp_events.iterrows():
            ts = row["timestamp_utc"]
            assert ts.weekday() == 4, f"NFP on {ts} is not Friday!"

    def test_first_friday_helper(self):
        # Jan 2023: 1st is Sunday, first Friday is 6th
        assert _get_first_friday(2023, 1) == date(2023, 1, 6)
        # Sep 2023: 1st is Friday
        assert _get_first_friday(2023, 9) == date(2023, 9, 1)

    def test_fomc_events_present(self):
        cal = generate_high_impact_calendar(2023, 2023)
        fomc = cal[cal["event_name"].str.contains("FOMC")]
        assert len(fomc) >= 16  # 8 meetings * (statement + press conf)


class TestBlackoutGate:
    def test_event_at_exact_bar(self):
        # Bar tepat di waktu rilis NFP (e.g. 2023-09-01 12:30 UTC)
        ts = pd.date_range("2023-09-01 10:00", "2023-09-01 15:00", freq="30min", tz="UTC")
        df = pd.DataFrame({
            "timestamp_utc": ts,
            "open": 1940.0, "high": 1945.0, "low": 1935.0, "close": 1942.0,
            "entry_eligible": True,
        })
        
        events = pd.DataFrame([{
            "timestamp_utc": pd.Timestamp("2023-09-01 12:30:00", tz="UTC"),
            "event_name": "US_NFP",
            "impact": "HIGH",
        }])
        
        flags = flag_news_blackout(df, events_df=events, blackout_minutes=30)
        # Bar 12:30 (bar 12:30-13:00) harus True
        idx_event = df[df["timestamp_utc"] == "2023-09-01 12:30:00+00:00"].index[0]
        assert flags.iloc[idx_event] == True

    def test_pre_event_blackout(self):
        # Bar 30 menit sebelum event (12:00-12:30 UTC untuk event 12:30 UTC)
        ts = pd.date_range("2023-09-01 10:00", "2023-09-01 15:00", freq="30min", tz="UTC")
        df = pd.DataFrame({
            "timestamp_utc": ts,
            "entry_eligible": True,
        })
        events = pd.DataFrame([{
            "timestamp_utc": pd.Timestamp("2023-09-01 12:30:00", tz="UTC"),
            "event_name": "US_NFP",
            "impact": "HIGH",
        }])
        flags = flag_news_blackout(df, events_df=events, blackout_minutes=30)
        idx_pre = df[df["timestamp_utc"] == "2023-09-01 12:00:00+00:00"].index[0]
        # Bar 12:00 ends at 12:30, yang bersinggungan dengan window [12:00, 13:00]
        assert flags.iloc[idx_pre] == True

    def test_far_bar_not_blackout(self):
        ts = pd.date_range("2023-09-01 10:00", "2023-09-01 15:00", freq="30min", tz="UTC")
        df = pd.DataFrame({
            "timestamp_utc": ts,
            "entry_eligible": True,
        })
        events = pd.DataFrame([{
            "timestamp_utc": pd.Timestamp("2023-09-01 12:30:00", tz="UTC"),
            "event_name": "US_NFP",
            "impact": "HIGH",
        }])
        flags = flag_news_blackout(df, events_df=events, blackout_minutes=30)
        idx_far = df[df["timestamp_utc"] == "2023-09-01 10:00:00+00:00"].index[0]
        assert flags.iloc[idx_far] == False

    def test_apply_gate_overrides_eligibility(self):
        ts = pd.date_range("2023-09-01 11:30", "2023-09-01 13:30", freq="30min", tz="UTC")
        df = pd.DataFrame({
            "timestamp_utc": ts,
            "entry_eligible": [True, True, True, True, True],
        })
        events = pd.DataFrame([{
            "timestamp_utc": pd.Timestamp("2023-09-01 12:30:00", tz="UTC"),
            "event_name": "US_NFP",
            "impact": "HIGH",
        }])
        df_gated = apply_news_blackout_gate(df, events_df=events, verbose=False)
        assert "is_news_blackout" in df_gated.columns
        # Bar yang blackout harus entry_eligible == False
        blackout_mask = df_gated["is_news_blackout"]
        assert (~df_gated.loc[blackout_mask, "entry_eligible"]).all()
