"""
XAU_DEEP_SNIPER - src.labeling
===============================
Modul pelabelan realistis pasca-biaya (Triple Barrier) dan Focal Loss weights.
"""
from .triple_barrier import (
    label_triple_barrier,
    compute_structural_risk,
    ACTION_CLASSES,
    TIME_BARRIER_BARS,
    COMMISSION_PER_OZ,
)
from .focal_weights import (
    compute_focal_weights,
    numpy_focal_loss,
    DEFAULT_GAMMA,
    NUM_CLASSES,
)

__all__ = [
    "label_triple_barrier",
    "compute_structural_risk",
    "ACTION_CLASSES",
    "TIME_BARRIER_BARS",
    "COMMISSION_PER_OZ",
    "compute_focal_weights",
    "numpy_focal_loss",
    "DEFAULT_GAMMA",
    "NUM_CLASSES",
]
