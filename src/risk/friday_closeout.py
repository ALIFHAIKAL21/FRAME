"""
XAU_DEEP_SNIPER - Friday Close-Out Rule (BAB 8.4)
==================================================
Proteksi Weekend Price Gap pada Instrumen Emas:
- Pukul 18:00 UTC hari Jumat: Bot dilarang membuka posisi baru (allow_entry = False).
- Pukul 20:00 UTC hari Jumat: Seluruh posisi mengambang dilikuidasi pada harga pasar
  (force_liquidate = True).
"""

from dataclasses import dataclass
import pandas as pd


@dataclass
class FridayRuleStatus:
    allow_new_entries: bool
    force_liquidate_all: bool
    reason: str


class FridayCloseoutRule:
    """
    Pengendali jadwal trading akhir pekan berbasis jam UTC.
    """

    def __init__(
        self,
        entry_freeze_hour_utc: int = 18,
        liquidation_hour_utc: int = 20,
    ):
        self.entry_freeze_hour_utc = entry_freeze_hour_utc
        self.liquidation_hour_utc = liquidation_hour_utc

    def check(self, timestamp_utc: pd.Timestamp) -> FridayRuleStatus:
        """
        Memeriksa apakah waktu bar berada dalam jendela larangan Jumat/Weekend.
        """
        if timestamp_utc.tzinfo is None:
            ts = timestamp_utc.tz_localize("UTC")
        else:
            ts = timestamp_utc.tz_convert("UTC")

        day_of_week = ts.dayofweek  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        hour = ts.hour

        # Hari Jumat (Day 4)
        if day_of_week == 4:
            if hour >= self.liquidation_hour_utc:
                return FridayRuleStatus(
                    allow_new_entries=False,
                    force_liquidate_all=True,
                    reason=f"Friday >= {self.liquidation_hour_utc}:00 UTC: Mandatory weekend liquidation active",
                )
            elif hour >= self.entry_freeze_hour_utc:
                return FridayRuleStatus(
                    allow_new_entries=False,
                    force_liquidate_all=False,
                    reason=f"Friday >= {self.entry_freeze_hour_utc}:00 UTC: New entry freeze active",
                )
            else:
                return FridayRuleStatus(
                    allow_new_entries=True,
                    force_liquidate_all=False,
                    reason="Friday normal hours before freeze",
                )

        # Hari Sabtu (Day 5) & Minggu sebelum market open (Day 6 jam < 22)
        if day_of_week == 5 or (day_of_week == 6 and hour < 22):
            return FridayRuleStatus(
                allow_new_entries=False,
                force_liquidate_all=True,
                reason="Weekend market closed",
            )

        # Hari kerja normal (Minggu 22:00 UTC s.d. Jumat 17:59 UTC)
        return FridayRuleStatus(
            allow_new_entries=True,
            force_liquidate_all=False,
            reason="Market open normal trading hours",
        )
