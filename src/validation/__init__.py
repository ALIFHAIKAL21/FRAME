"""
XAU_DEEP_SNIPER - Validation & Backtesting Module (TAHAP 6)
============================================================
Infrastruktur validasi ilmiah institusional:
- Purged Walk-Forward Cross-Validation
- Realistic Bar-by-Bar Event-Driven Backtest Engine
- Monte Carlo Stress Testing (1,000 trade permutations)
- 3 Hard Scientific Gates Auditor
"""

from .walk_forward import PurgedWalkForwardCV
from .backtest_engine import RealisticBacktestEngine
from .monte_carlo import MonteCarloStressTester
from .scientific_gates import ScientificGatesAuditor

__all__ = [
    "PurgedWalkForwardCV",
    "RealisticBacktestEngine",
    "MonteCarloStressTester",
    "ScientificGatesAuditor",
]
