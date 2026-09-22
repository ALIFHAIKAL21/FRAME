"""
XAU_DEEP_SNIPER — Unit Tests: DST Harmonizer
==============================================
Menguji kalkulasi DST untuk tanggal-tanggal kritis:
- Tepat sebelum/sesudah transisi US DST (Maret & November)
- Tepat sebelum/sesudah transisi UK DST (Maret & Oktober)
"""

import pytest
from datetime import date
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.pipeline.dst_harmonizer import (
    get_rollover_hour_utc,
    is_dst_active_us,
    is_dst_active_uk,
    get_session_boundaries_utc,
)


class TestUSDST:
    """Test kalkulasi DST US Eastern."""

    def test_winter_no_dst(self):
        """Januari = EST (no DST), rollover = 22:00 UTC."""
        d = date(2023, 1, 15)
        assert is_dst_active_us(d) is False
        assert get_rollover_hour_utc(d) == 22

    def test_summer_dst_active(self):
        """Juli = EDT (DST active), rollover = 21:00 UTC."""
        d = date(2023, 7, 15)
        assert is_dst_active_us(d) is True
        assert get_rollover_hour_utc(d) == 21

    def test_spring_forward_2023(self):
        """12 Maret 2023 = US Spring Forward (Minggu ke-2 Maret)."""
        before = date(2023, 3, 11)
        after = date(2023, 3, 13)
        assert is_dst_active_us(before) is False  # Sebelum transition
        assert is_dst_active_us(after) is True     # Setelah transition

    def test_fall_back_2023(self):
        """5 November 2023 = US Fall Back (Minggu ke-1 November)."""
        before = date(2023, 11, 4)
        after = date(2023, 11, 6)
        assert is_dst_active_us(before) is True   # Sebelum transition
        assert is_dst_active_us(after) is False    # Setelah transition

    def test_spring_forward_2024(self):
        """10 Maret 2024."""
        before = date(2024, 3, 9)
        after = date(2024, 3, 11)
        assert is_dst_active_us(before) is False
        assert is_dst_active_us(after) is True

    def test_rollover_consistency_across_years(self):
        """Rollover harus 21 (summer) atau 22 (winter) untuk semua tahun."""
        for year in [2021, 2022, 2023, 2024, 2025]:
            summer = date(year, 7, 1)
            winter = date(year, 1, 1)
            assert get_rollover_hour_utc(summer) == 21, f"Summer {year} failed"
            assert get_rollover_hour_utc(winter) == 22, f"Winter {year} failed"


class TestUKDST:
    """Test kalkulasi DST UK (BST)."""

    def test_winter_no_bst(self):
        """Januari = GMT (no BST)."""
        assert is_dst_active_uk(date(2023, 1, 15)) is False

    def test_summer_bst_active(self):
        """Juli = BST (DST aktif)."""
        assert is_dst_active_uk(date(2023, 7, 15)) is True

    def test_spring_forward_2023(self):
        """UK Spring Forward: Minggu terakhir Maret 2023 = 26 Maret."""
        before = date(2023, 3, 25)
        after = date(2023, 3, 27)
        assert is_dst_active_uk(before) is False
        assert is_dst_active_uk(after) is True

    def test_fall_back_2023(self):
        """UK Fall Back: Minggu terakhir Oktober 2023 = 29 Oktober."""
        before = date(2023, 10, 28)
        after = date(2023, 10, 30)
        assert is_dst_active_uk(before) is True
        assert is_dst_active_uk(after) is False


class TestSessionBoundaries:
    """Test session boundary calculation."""

    def test_summer_sessions(self):
        """Summer: London start 06, NY start 12."""
        d = date(2023, 7, 10)  # Kedua DST aktif
        b = get_session_boundaries_utc(d)
        assert b["asian_start"] == 0
        assert b["london_start"] == 6
        assert b["newyork_start"] == 12
        assert b["rollover_start"] == 21

    def test_winter_sessions(self):
        """Winter: London start 07, NY start 13."""
        d = date(2023, 1, 10)  # Kedua DST tidak aktif
        b = get_session_boundaries_utc(d)
        assert b["asian_start"] == 0
        assert b["london_start"] == 7
        assert b["newyork_start"] == 13
        assert b["rollover_start"] == 22
