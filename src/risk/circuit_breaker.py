"""
XAU_DEEP_SNIPER - Weekly Drawdown Circuit Breaker (BAB 8.2)
============================================================
Aturan Hard Gating Institusional:
- Jika akumulasi drawdown mingguan mencapai batas pertahanan 5% (-5.0%),
  pembukaan posisi dihentikan hingga pergantian minggu kalender berikutnya.
- Batas kerugian mutlak 50% berfungsi sebagai fail-safe struktural permanent stop.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import pandas as pd


@dataclass
class CircuitBreakerStatus:
    is_tripped: bool
    can_trade: bool
    weekly_starting_equity: float
    current_equity: float
    weekly_drawdown_pct: float
    all_time_peak_equity: float
    peak_drawdown_pct: float
    current_week_id: str
    rejection_reason: str = ""


class WeeklyCircuitBreaker:
    """
    Pelindung modal mingguan berbasis siklus kalender UTC.
    """

    def __init__(
        self,
        weekly_drawdown_limit: float = 0.05,     # 5.0% cap
        absolute_drawdown_limit: float = 0.50,   # 50.0% structural stop
    ):
        self.weekly_drawdown_limit = weekly_drawdown_limit
        self.absolute_drawdown_limit = absolute_drawdown_limit

        self.current_week_id: Optional[str] = None
        self.weekly_starting_equity: float = 0.0
        self.all_time_peak_equity: float = 0.0
        self.is_weekly_tripped: bool = False
        self.is_permanent_stopped: bool = False
        self.trip_reason: str = ""

    def _get_week_id(self, timestamp: pd.Timestamp) -> str:
        """Format week ID: 'YYYY-Www' berdasarkan ISO calendar UTC."""
        iso = timestamp.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    def update(
        self,
        current_equity: float,
        timestamp_utc: pd.Timestamp,
    ) -> CircuitBreakerStatus:
        """
        Memperbarui status ekuitas dan mengecek apakah batas circuit breaker tersentuh.
        """
        if current_equity <= 0:
            self.is_permanent_stopped = True
            self.trip_reason = "Account equity depleted (<= 0)"
            return CircuitBreakerStatus(
                is_tripped=True,
                can_trade=False,
                weekly_starting_equity=self.weekly_starting_equity,
                current_equity=current_equity,
                weekly_drawdown_pct=-1.0,
                all_time_peak_equity=self.all_time_peak_equity,
                peak_drawdown_pct=-1.0,
                current_week_id=self.current_week_id or "UNKNOWN",
                rejection_reason=self.trip_reason,
            )

        week_id = self._get_week_id(timestamp_utc)

        # Inisialisasi awal atau pergantian minggu kalender
        if self.current_week_id is None:
            self.current_week_id = week_id
            self.weekly_starting_equity = current_equity
            self.all_time_peak_equity = current_equity
        elif week_id != self.current_week_id:
            # Pergantian minggu baru: Reset weekly breaker
            self.current_week_id = week_id
            self.weekly_starting_equity = current_equity
            if not self.is_permanent_stopped:
                self.is_weekly_tripped = False
                self.trip_reason = ""

        # Update all-time peak
        if current_equity > self.all_time_peak_equity:
            self.all_time_peak_equity = current_equity

        # Hitung Drawdown
        weekly_dd = (current_equity - self.weekly_starting_equity) / self.weekly_starting_equity
        peak_dd = (current_equity - self.all_time_peak_equity) / self.all_time_peak_equity

        # Evaluasi permanent fail-safe (50%) & weekly breaker (5%)
        # Permanent emergency shutdown takes precedence
        if peak_dd <= -self.absolute_drawdown_limit:
            self.is_permanent_stopped = True
            self.trip_reason = f"Absolute safety limit reached ({peak_dd*100:.1f}% <= -{self.absolute_drawdown_limit*100:.1f}%)"
        elif weekly_dd <= -self.weekly_drawdown_limit:
            self.is_weekly_tripped = True
            self.trip_reason = f"Weekly circuit breaker triggered ({weekly_dd*100:.2f}% <= -{self.weekly_drawdown_limit*100:.1f}%)"

        can_trade = (not self.is_weekly_tripped) and (not self.is_permanent_stopped)

        return CircuitBreakerStatus(
            is_tripped=(self.is_weekly_tripped or self.is_permanent_stopped),
            can_trade=can_trade,
            weekly_starting_equity=round(self.weekly_starting_equity, 2),
            current_equity=round(current_equity, 2),
            weekly_drawdown_pct=round(weekly_dd, 4),
            all_time_peak_equity=round(self.all_time_peak_equity, 2),
            peak_drawdown_pct=round(peak_dd, 4),
            current_week_id=self.current_week_id,
            rejection_reason="" if can_trade else self.trip_reason,
        )

    def can_trade(self) -> Tuple[bool, str]:
        """Query cepat status kelaikan trading saat ini."""
        if self.is_permanent_stopped:
            return False, self.trip_reason
        if self.is_weekly_tripped:
            return False, self.trip_reason
        return True, "OK"
