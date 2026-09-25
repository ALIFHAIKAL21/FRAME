"""
XAU_DEEP_SNIPER - 3 Hard Scientific Gates Auditor (BAB 9.4)
=============================================================
Evaluasi deterministik hasil backtest dan Monte Carlo terhadap
3 kriteria kelayakan institusional non-negosiabel.

Gate 1: Out-of-Sample Performance (Konvergensi & Sharpe)
Gate 2: Resolusi Bot Malas & Monte Carlo Stress (Precision & DD)
Gate 3: Net Profit Factor Pasca-Biaya (Expectancy Realistis)
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
from pathlib import Path

from .backtest_engine import BacktestResult
from .monte_carlo import MonteCarloResult


@dataclass
class GateResult:
    """Hasil evaluasi satu gate."""
    gate_id: int
    gate_name: str
    passed: bool
    criteria: Dict[str, Any]
    actual_values: Dict[str, Any]
    verdict: str


@dataclass
class ScientificAuditReport:
    """Laporan audit komprehensif seluruh 3 gate."""
    gate_1: GateResult
    gate_2: GateResult
    gate_3: GateResult
    all_gates_passed: bool
    system_verdict: str

    def to_dict(self) -> Dict[str, Any]:
        """Konversi ke dictionary untuk serialisasi JSON."""
        return {
            "gate_1": asdict(self.gate_1),
            "gate_2": asdict(self.gate_2),
            "gate_3": asdict(self.gate_3),
            "all_gates_passed": self.all_gates_passed,
            "system_verdict": self.system_verdict,
        }


class ScientificGatesAuditor:
    """
    Auditor 3 Hard Scientific Gates.

    Parameters
    ----------
    min_sharpe : float
        Minimum Sharpe Ratio annualized untuk Gate 1 (default 1.4).
    min_non_hold_precision : float
        Minimum precision sinyal non-HOLD untuk Gate 2 (default 0.55 = 55%).
    max_mc_p95_drawdown : float
        Maximum Monte Carlo 95th pctl worst-case drawdown untuk Gate 2 (default -0.18 = -18%).
    min_net_profit_factor : float
        Minimum Net Profit Factor pasca-biaya untuk Gate 3 (default 1.35).
    max_weekly_dd_trigger : float
        Maximum weekly drawdown sebelum circuit breaker trip (default -0.05 = -5%).
    """

    def __init__(
        self,
        min_sharpe: float = 1.4,
        min_non_hold_precision: float = 0.55,
        max_mc_p95_drawdown: float = -0.18,
        min_net_profit_factor: float = 1.35,
        max_weekly_dd_trigger: float = -0.05,
    ):
        self.min_sharpe = min_sharpe
        self.min_non_hold_precision = min_non_hold_precision
        self.max_mc_p95_drawdown = max_mc_p95_drawdown
        self.min_net_profit_factor = min_net_profit_factor
        self.max_weekly_dd_trigger = max_weekly_dd_trigger

    def evaluate_gate_1(
        self,
        backtest_result: BacktestResult,
        val_convergence_stable: bool = True,
    ) -> GateResult:
        """
        Gate 1: Out-of-Sample Performance.
        - Sharpe Ratio Annualized >= min_sharpe
        - Konvergensi pelatihan stabil (val loss tidak naik terus)
        """
        sharpe = backtest_result.sharpe_ratio
        sharpe_passed = sharpe >= self.min_sharpe

        all_passed = sharpe_passed and val_convergence_stable

        return GateResult(
            gate_id=1,
            gate_name="Out-of-Sample Performance (Konvergensi & Sharpe)",
            passed=all_passed,
            criteria={
                "min_sharpe_ratio": self.min_sharpe,
                "val_convergence_required": True,
            },
            actual_values={
                "sharpe_ratio": round(sharpe, 4),
                "sharpe_passed": sharpe_passed,
                "val_convergence_stable": val_convergence_stable,
            },
            verdict=(
                f"{'PASS' if all_passed else 'FAIL'}: "
                f"Sharpe={sharpe:.4f} (req >={self.min_sharpe}) "
                f"{'✓' if sharpe_passed else '✗'} | "
                f"Convergence {'✓' if val_convergence_stable else '✗'}"
            ),
        )

    def evaluate_gate_2(
        self,
        backtest_result: BacktestResult,
        mc_result: Optional[MonteCarloResult] = None,
    ) -> GateResult:
        """
        Gate 2: Resolusi Bot Malas & Monte Carlo Stress Test.
        - Non-HOLD precision >= 55%
        - Monte Carlo 95th pctl worst-case DD <= 18%
        """
        precision = backtest_result.non_hold_precision
        precision_passed = precision >= self.min_non_hold_precision

        if mc_result is not None:
            mc_p95_dd = mc_result.p95_max_drawdown  # Negative value
            mc_passed = mc_p95_dd >= self.max_mc_p95_drawdown  # e.g., -0.12 >= -0.18
        else:
            mc_p95_dd = 0.0
            mc_passed = False

        all_passed = precision_passed and mc_passed

        return GateResult(
            gate_id=2,
            gate_name="Resolusi Bot Malas & Monte Carlo Stress Test",
            passed=all_passed,
            criteria={
                "min_non_hold_precision": self.min_non_hold_precision,
                "max_mc_p95_drawdown": self.max_mc_p95_drawdown,
            },
            actual_values={
                "non_hold_precision": round(precision, 4),
                "precision_passed": precision_passed,
                "mc_p95_drawdown": round(mc_p95_dd, 4) if mc_result else None,
                "mc_passed": mc_passed,
                "mc_iterations": mc_result.n_iterations if mc_result else 0,
            },
            verdict=(
                f"{'PASS' if all_passed else 'FAIL'}: "
                f"Precision={precision*100:.1f}% (req >={self.min_non_hold_precision*100}%) "
                f"{'✓' if precision_passed else '✗'} | "
                f"MC P95 DD={mc_p95_dd*100:.2f}% (req >={self.max_mc_p95_drawdown*100}%) "
                f"{'✓' if mc_passed else '✗'}"
            ),
        )

    def evaluate_gate_3(
        self,
        backtest_result: BacktestResult,
    ) -> GateResult:
        """
        Gate 3: Net Profit Factor Pasca-Biaya & Realistis.
        - Net Profit Factor >= 1.35
        - Weekly drawdown tidak pernah menyentuh circuit breaker 5%
        """
        npf = backtest_result.net_profit_factor
        npf_passed = npf >= self.min_net_profit_factor

        cb_trips = backtest_result.circuit_breaker_trips
        cb_clean = cb_trips == 0

        all_passed = npf_passed and cb_clean

        return GateResult(
            gate_id=3,
            gate_name="Expectancy Pasca-Biaya Bersih & Realistis",
            passed=all_passed,
            criteria={
                "min_net_profit_factor": self.min_net_profit_factor,
                "max_circuit_breaker_trips": 0,
            },
            actual_values={
                "net_profit_factor": round(npf, 4),
                "npf_passed": npf_passed,
                "circuit_breaker_trips": cb_trips,
                "cb_clean": cb_clean,
                "total_friction_usd": backtest_result.total_friction,
                "net_pnl_usd": backtest_result.net_pnl,
            },
            verdict=(
                f"{'PASS' if all_passed else 'FAIL'}: "
                f"Net PF={npf:.4f} (req >={self.min_net_profit_factor}) "
                f"{'✓' if npf_passed else '✗'} | "
                f"CB Trips={cb_trips} (req ==0) "
                f"{'✓' if cb_clean else '✗'}"
            ),
        )

    def full_audit(
        self,
        backtest_result: BacktestResult,
        mc_result: Optional[MonteCarloResult] = None,
        val_convergence_stable: bool = True,
    ) -> ScientificAuditReport:
        """
        Menjalankan audit lengkap 3 Hard Scientific Gates.
        """
        g1 = self.evaluate_gate_1(backtest_result, val_convergence_stable)
        g2 = self.evaluate_gate_2(backtest_result, mc_result)
        g3 = self.evaluate_gate_3(backtest_result)

        all_passed = g1.passed and g2.passed and g3.passed

        if all_passed:
            verdict = (
                "SYSTEM APPROVED: Seluruh 3 Hard Scientific Gates LULUS. "
                "Model memenuhi standar kelayakan institusional untuk "
                "integrasi ke antarmuka live trading."
            )
        else:
            failed_gates = []
            if not g1.passed:
                failed_gates.append("Gate 1 (Sharpe/Convergence)")
            if not g2.passed:
                failed_gates.append("Gate 2 (Precision/Monte Carlo)")
            if not g3.passed:
                failed_gates.append("Gate 3 (Net PF/Circuit Breaker)")
            verdict = (
                f"SYSTEM REJECTED: {len(failed_gates)}/3 gate GAGAL — "
                f"{', '.join(failed_gates)}. "
                f"Model BELUM memenuhi standar institusional. "
                f"Diperlukan iterasi penelitian tambahan."
            )

        return ScientificAuditReport(
            gate_1=g1,
            gate_2=g2,
            gate_3=g3,
            all_gates_passed=all_passed,
            system_verdict=verdict,
        )

    def save_report(
        self,
        report: ScientificAuditReport,
        output_path: Path,
    ) -> None:
        """Menyimpan laporan audit ke file JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, default=str, ensure_ascii=False)

    def print_audit(self, report: ScientificAuditReport) -> str:
        """Mencetak laporan audit dengan format tabel visual."""
        lines = [
            "",
            "█" * 80,
            "  3 HARD SCIENTIFIC GATES — INSTITUTIONAL AUDIT REPORT",
            "█" * 80,
            "",
        ]

        for gate in [report.gate_1, report.gate_2, report.gate_3]:
            status = "✅ PASS" if gate.passed else "❌ FAIL"
            lines.append(f"  Gate {gate.gate_id}: {gate.gate_name}")
            lines.append(f"    Status  : {status}")
            lines.append(f"    Verdict : {gate.verdict}")
            lines.append("")

        lines.append("─" * 80)
        final_status = "✅ ALL GATES PASSED" if report.all_gates_passed else "❌ SYSTEM REJECTED"
        lines.append(f"  FINAL VERDICT: {final_status}")
        lines.append(f"  {report.system_verdict}")
        lines.append("█" * 80)

        report_str = "\n".join(lines)
        try:
            print(report_str)
        except UnicodeEncodeError:
            print(report_str.encode("ascii", errors="replace").decode("ascii"))
        return report_str
