"""
XAU_DEEP_SNIPER - High-Performance PyTorch Dataset & DataLoader Module (15 Channels)
=====================================================================================
Mengonversi dataset fitur berlabel menjadi sliding window tensors
untuk arsitektur Foundation Model MOMENT-1-large.

Spesifikasi Tensor (BAB 5.1 & UPGRADE.MD):
- Input Tensor Shape: (B x C x L)
  * B: Batch size (e.g. 128)
  * C: 15 feature channels (12 baseline + 3 H4 macro)
  * L: 64 bars M30 (lookback window t-63 s.d. t)
- Target Tensor: Class integer a_t in {0, 1, 2, 3, 4} (dtype torch.long)
- Data type: torch.float32

OPTIMASI KECEPATAN NON-PINTAS:
- Pre-allocated contiguous in-memory tensors:
  Seluruh window disimpan dalam satu blok tensor contiguous di RAM (~180 MB).
  Pengambilan batch di DataLoader berjalan tanpa copy overhead (zero-copy memory slicing).
"""

import torch
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from typing import List, Tuple, Optional, Union
import pathlib

# 15 Feature Channels sesuai BAB 3.2 & UPGRADE.MD
DEFAULT_FEATURE_CHANNELS: List[str] = [
    "ohlc_norm_open",      # Ch 1: Open normalized
    "ohlc_norm_high",      # Ch 2: High normalized
    "ohlc_norm_low",       # Ch 3: Low normalized
    "ohlc_norm_close",     # Ch 4: Close normalized
    "volume_zscore",       # Ch 5: Volume Z-score
    "sma_cross_spread",    # Ch 6: MA Cross (SMA 9 x SMA 21 spread / ATR)
    "smi_val",             # Ch 7: Stochastic Momentum Index (10, 3, 3, 10) in [-1, 1]
    "smi_signal_hist",     # Ch 8: SMI Signal Line Difference / Momentum
    "smi_reversal_zone",   # Ch 9: SMI +/-40 Reversal Signal (+1 OS bull, -1 OB bear)
    "order_block_zone",    # Ch 10: Supply / Demand Order Block (+1 Demand, -1 Supply)
    "liquidity_sweep",     # Ch 11: Liquidity Sweeps (+1 SSL sweep, -1 BSL sweep)
    "valuation_regime",    # Ch 12: Premium/Discount Valuation & Sideways Regime
    "h4_macro_trend_velocity",        # Ch 13: H4 Macro Velocity
    "h4_market_structure",            # Ch 14: H4 Structural Ribbon Alignment
    "momentum_expansion_persistence", # Ch 15: Expansion Persistence & Proximity
]

DEFAULT_SEQUENCE_LENGTH: int = 64  # L = 64 bar M30


class XAUTimeSeriesDataset(Dataset):
    """
    High-Performance PyTorch Dataset untuk sliding window tensor (C, L) dan target diskrit a.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
        feature_channels: Optional[List[str]] = None,
        target_column: str = "action",
    ):
        super().__init__()
        self.sequence_length = sequence_length
        self.feature_channels = feature_channels or DEFAULT_FEATURE_CHANNELS
        self.target_column = target_column

        # Validasi kolom
        missing_features = [c for c in self.feature_channels if c not in df.columns]
        if missing_features:
            raise ValueError(f"Channel fitur tidak ditemukan dalam DataFrame: {missing_features}")
        if self.target_column not in df.columns:
            raise ValueError(f"Kolom target '{self.target_column}' tidak ditemukan dalam DataFrame")

        n_bars = len(df)
        if n_bars < self.sequence_length:
            raise ValueError(
                f"Jumlah bar ({n_bars}) lebih kecil dari sequence_length ({self.sequence_length})"
            )

        # Ambil matriks fitur (T, C)
        feature_data = df[self.feature_channels].values.astype(np.float32)

        # Bentuk sliding window view (N, C, L)
        windows = sliding_window_view(feature_data, window_shape=self.sequence_length, axis=0)
        targets = df[self.target_column].iloc[self.sequence_length - 1:].values.astype(np.int64)

        # Pre-allocate contiguous PyTorch tensors in RAM (Zero-Copy Slicing)
        self.x_tensor = torch.from_numpy(np.ascontiguousarray(windows))
        self.y_tensor = torch.from_numpy(np.ascontiguousarray(targets))

        # Timestamps pada bar t (akhir window) untuk audit dan evaluasi
        if "timestamp_utc" in df.columns:
            self.timestamps = df["timestamp_utc"].iloc[self.sequence_length - 1:].reset_index(drop=True)
        else:
            self.timestamps = pd.Series(range(len(targets)))

        self.n_samples = len(self.y_tensor)
        assert len(self.x_tensor) == self.n_samples, "Mismatch antara jumlah windows dan targets"

    def __len__(self) -> int:
        return self.n_samples

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return self.x_tensor[idx], self.y_tensor[idx]

    def get_timestamp(self, idx: int) -> pd.Timestamp:
        """Mengembalikan timestamp UTC pada akhir window ke-idx."""
        return self.timestamps.iloc[idx]


def create_dataloaders(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    batch_size: int = 128,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    feature_channels: Optional[List[str]] = None,
    num_workers: int = 0,
    pin_memory: bool = True,
) -> Tuple[DataLoader, DataLoader, XAUTimeSeriesDataset, XAUTimeSeriesDataset]:
    """
    Membuat DataLoader teroptimasi untuk training dan testing.
    """
    train_dataset = XAUTimeSeriesDataset(
        train_df,
        sequence_length=sequence_length,
        feature_channels=feature_channels,
    )
    test_dataset = XAUTimeSeriesDataset(
        test_df,
        sequence_length=sequence_length,
        feature_channels=feature_channels,
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=True,
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=False,
    )

    return train_loader, test_loader, train_dataset, test_dataset
