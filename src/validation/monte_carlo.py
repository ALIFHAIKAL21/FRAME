"""
XAU_DEEP_SNIPER - Monte Carlo Trade Shuffle Stress Tester (BAB 9.3)
=====================================================================
Melakukan 1,000 iterasi permutasi acak urutan trade untuk menguji
ketahanan sistem terhadap variasi statistik eksekusi temporal.

Metrik utama:
- Distribusi equity curve (median, 5th, 95th percentile)
- Distribusi peak-to-trough drawdown
- Probabilitas menyentuh circuit breaker mingguan 5%
- 95th percentile worst-case drawdown
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np


@dataclass
class MonteCarloResult:
    """Hasil dari simulasi Monte Carlo."""
    n_iterations: int
    n_trades: int
    initial_equity: float

    # Equity curve statistics
    median_final_equity: float
    p5_final_equity: float
    p95_final_equity: float
    mean_final_equity: float
    std_final_equity: float

    # Drawdown statistics
    median_max_drawdown: float
    p5_max_drawdown: float       # Best case (shallowest)
    p95_max_drawdown: float      # Worst case (deepest)
    mean_max_drawdown: float
    worst_case_drawdown: float   # Absolute worst across all sims

    # Circuit breaker probability
    prob_circuit_breaker_trip: float  # Fraction of sims that hit 5% weekly DD
    prob_permanent_stop: float       # Fraction of sims that hit 50% peak DD

    # Raw arrays for downstream analysis
    final_equities: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    max_drawdowns: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))


class MonteCarloStressTester:
    """
    Generator stress test Monte Carlo berbasis permutasi urutan trade.

    Parameters
    ----------
    n_iterations : int
        Jumlah simulasi Monte Carlo (default 1,000).
    weekly_dd_limit : float
        Batas drawdown mingguan untuk circuit breaker (default 5.0%).
    absolute_dd_limit : float
        Batas drawdown absolut untuk permanent stop (default 50.0%).
    random_seed : int
        Seed untuk reprodusibilitas (default 42).
    """

    def __init__(
        self,
        n_iterations: int = 1000,
        weekly_dd_limit: float = 0.05,
        absolute_dd_limit: float = 0.50,
        random_seed: int = 42,
    ):
        self.n_iterations = n_iterations
        self.weekly_dd_limit = weekly_dd_limit
        self.absolute_dd_limit = absolute_dd_limit
        self.rng = np.random.default_rng(random_seed)

    def run(
        self,
        trade_pnls: np.ndarray,
        initial_equity: float = 10_000.0,
        avg_trades_per_week: float = 5.0,
    ) -> MonteCarloResult:
        """
        Menjalankan simulasi Monte Carlo.

        Parameters
        ----------
        trade_pnls : np.ndarray
            Array PnL net dari setiap trade (shape: (n_trades,)).
        initial_equity : float
            Modal awal simulasi.
        avg_trades_per_week : float
            Estimasi rata-rata jumlah trade per minggu (untuk
            simulasi circuit breaker mingguan).

        Returns
        -------
        MonteCarloResult
            Hasil simulasi lengkap.
        """
        n_trades = len(trade_pnls)
        if n_trades == 0:
            return MonteCarloResult(
                n_iterations=self.n_iterations,
                n_trades=0,
                initial_equity=initial_equity,
                median_final_equity=initial_equity,
                p5_final_equity=initial_equity,
                p95_final_equity=initial_equity,
                mean_final_equity=initial_equity,
                std_final_equity=0.0,
                median_max_drawdown=0.0,
                p5_max_drawdown=0.0,
                p95_max_drawdown=0.0,
                mean_max_drawdown=0.0,
                worst_case_drawdown=0.0,
                prob_circuit_breaker_trip=0.0,
                prob_permanent_stop=0.0,
            )

        # Approximation: jumlah trade per "week" dalam simulasi
        trades_per_week = max(1, int(round(avg_trades_per_week)))

        final_equities = np.zeros(self.n_iterations)
        max_drawdowns = np.zeros(self.n_iterations)
        cb_trips = 0
        perm_stops = 0

        for sim_idx in range(self.n_iterations):
            # Permutasi acak urutan trade
            shuffled = self.rng.permutation(trade_pnls)

            # Simulasi ekuitas
            equity = initial_equity
            peak = equity
            max_dd = 0.0
            hit_cb = False
            hit_perm = False

            # Simulasi weekly circuit breaker
            week_start_eq = equity

            for t_idx, pnl in enumerate(shuffled):
                equity += pnl

                # Track peak
                if equity > peak:
                    peak = equity

                # Track drawdown
                if peak > 0:
                    dd = (equity - peak) / peak
                    if dd < max_dd:
                        max_dd = dd

                # Check permanent stop
                if peak > 0 and dd <= -self.absolute_dd_limit:
                    hit_perm = True

                # Weekly reset simulation
                if (t_idx + 1) % trades_per_week == 0:
                    if week_start_eq > 0:
                        weekly_dd = (equity - week_start_eq) / week_start_eq
                        if weekly_dd <= -self.weekly_dd_limit:
                            hit_cb = True
                    week_start_eq = equity

            final_equities[sim_idx] = equity
            max_drawdowns[sim_idx] = max_dd

            if hit_cb:
                cb_trips += 1
            if hit_perm:
                perm_stops += 1

        return MonteCarloResult(
            n_iterations=self.n_iterations,
            n_trades=n_trades,
            initial_equity=initial_equity,
            median_final_equity=round(float(np.median(final_equities)), 2),
            p5_final_equity=round(float(np.percentile(final_equities, 5)), 2),
            p95_final_equity=round(float(np.percentile(final_equities, 95)), 2),
            mean_final_equity=round(float(np.mean(final_equities)), 2),
            std_final_equity=round(float(np.std(final_equities)), 2),
            median_max_drawdown=round(float(np.median(max_drawdowns)), 4),
            p5_max_drawdown=round(float(np.percentile(max_drawdowns, 5)), 4),  # "best"
            p95_max_drawdown=round(float(np.percentile(max_drawdowns, 95)), 4),  # "worst"
            mean_max_drawdown=round(float(np.mean(max_drawdowns)), 4),
            worst_case_drawdown=round(float(np.min(max_drawdowns)), 4),
            prob_circuit_breaker_trip=round(cb_trips / self.n_iterations, 4),
            prob_permanent_stop=round(perm_stops / self.n_iterations, 4),
            final_equities=final_equities,
            max_drawdowns=max_drawdowns,
        )

    def print_report(self, result: MonteCarloResult) -> str:
        """Mencetak laporan Monte Carlo."""
        lines = [
            "=" * 80,
            "MONTE CARLO STRESS TEST REPORT",
            f"  Iterations: {result.n_iterations:,} | Trades: {result.n_trades}",
            "=" * 80,
            "",
            "--- FINAL EQUITY DISTRIBUTION ---",
            f"  Mean               : ${result.mean_final_equity:,.2f}",
            f"  Median             : ${result.median_final_equity:,.2f}",
            f"  5th Percentile     : ${result.p5_final_equity:,.2f}",
            f"  95th Percentile    : ${result.p95_final_equity:,.2f}",
            f"  Std Dev            : ${result.std_final_equity:,.2f}",
            "",
            "--- MAX DRAWDOWN DISTRIBUTION ---",
            f"  Mean Max DD        : {result.mean_max_drawdown * 100:.2f}%",
            f"  Median Max DD      : {result.median_max_drawdown * 100:.2f}%",
            f"  5th Pctl (Best)    : {result.p5_max_drawdown * 100:.2f}%",
            f"  95th Pctl (Worst)  : {result.p95_max_drawdown * 100:.2f}%",
            f"  Absolute Worst     : {result.worst_case_drawdown * 100:.2f}%",
            "",
            "--- CIRCUIT BREAKER ANALYSIS ---",
            f"  P(Weekly CB Trip)  : {result.prob_circuit_breaker_trip * 100:.1f}%",
            f"  P(Permanent Stop)  : {result.prob_permanent_stop * 100:.1f}%",
            "=" * 80,
        ]
        report = "\n".join(lines)
        print(report)
        return report
