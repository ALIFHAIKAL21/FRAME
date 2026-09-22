"""
XAU_DEEP_SNIPER - src.models
=============================
Modul arsitektur model tunggal MOMENT-1-large, dataset, loss, dan trainer.
"""
from .dataset import (
    XAUTimeSeriesDataset,
    create_dataloaders,
    DEFAULT_FEATURE_CHANNELS,
    DEFAULT_SEQUENCE_LENGTH,
)
from .moment_model import (
    MOMENTClassifier,
    MOMENTConfig,
    LoRALinear,
    PatchEmbedding,
    ClassificationHead,
)
from .loss import (
    ClassBalancedFocalLoss,
    DEFAULT_GAMMA,
)
from .trainer import (
    MOMENTTrainer,
    compute_classification_metrics,
)

__all__ = [
    "XAUTimeSeriesDataset",
    "create_dataloaders",
    "DEFAULT_FEATURE_CHANNELS",
    "DEFAULT_SEQUENCE_LENGTH",
    "MOMENTClassifier",
    "MOMENTConfig",
    "LoRALinear",
    "PatchEmbedding",
    "ClassificationHead",
    "ClassBalancedFocalLoss",
    "DEFAULT_GAMMA",
    "MOMENTTrainer",
    "compute_classification_metrics",
]
