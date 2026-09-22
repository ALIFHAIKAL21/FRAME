"""
XAU_DEEP_SNIPER - PyTorch Dataset & DataLoader Module (TAHAP 4A)
==================================================================
Mengonversi dataset fitur berlabel menjadi sliding window tensors
untuk arsitektur Foundation Model MOMENT-1-large.

Spesifikasi Tensor (BAB 5.1):
- Input Tensor Shape: (B x C x L)
  * B: Batch size
  * C: 9 feature channels
  * L: 64 bars M30 (lookback window t-63 s.d. t)
- Target Tensor: Class integer a_t in {0, 1, 2, 3, 4} (dtype torch.long)
- Data type: torch.float32
"""

import torch
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from typing import List, Tuple, Optional, Union
import pathlib

# 9 Feature Channels sesuai BAB 3.2
DEFAULT_FEATURE_CHANNELS: List[str] = [
    "ohlc_norm_open",      # Ch 1: Open normalized
    "ohlc_norm_high",      # Ch 2: High normalized
    "ohlc_norm_low",       # Ch 3: Low normalized
    "ohlc_norm_close",     # Ch 4: Close normalized
    "volume_zscore",       # Ch 5: Volume Z-score
    "smi",                 # Ch 6: Stochastic Momentum Index
    "ma_ribbon_slope",     # Ch 7: MA Ribbon Slope
    "liquidity_distance",  # Ch 8: Liquidity Pool Distance
    "fvg_status",          # Ch 9: Fair Value Gap Status
]

DEFAULT_SEQUENCE_LENGTH: int = 64  # L = 64 bar M30


class XAUTimeSeriesDataset(Dataset):
    """
    PyTorch Dataset untuk sliding window tensor (C, L) dan label target diskrit a.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame berlabel (harus memuat 9 kolom fitur dan kolom 'action').
    sequence_length : int
        Panjang jendela lookback L (default 64 bar M30).
    feature_channels : list of str
        Daftar nama kolom channel fitur (default 9 channel).
    target_column : str
        Nama kolom target (default 'action').
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

        # Bentuk zero-copy sliding window view (N, C, L)
        # sliding_window_view sepanjang axis 0 dengan window_shape = sequence_length
        # Menghasilkan shape: (N, C, L)
        self.windows = sliding_window_view(feature_data, window_shape=self.sequence_length, axis=0)

        # Target label a_t pada akhir setiap window (bar t = idx + sequence_length - 1)
        self.targets = df[self.target_column].iloc[self.sequence_length - 1:].values.astype(np.int64)

        # Timestamps pada bar t (akhir window) untuk audit dan evaluasi
        if "timestamp_utc" in df.columns:
            self.timestamps = df["timestamp_utc"].iloc[self.sequence_length - 1:].reset_index(drop=True)
        else:
            self.timestamps = pd.Series(range(len(self.targets)))

        self.n_samples = len(self.targets)
        assert len(self.windows) == self.n_samples, "Mismatch antara jumlah windows dan targets"

    def __len__(self) -> int:
        return self.n_samples

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Mengembalikan:
        - x: torch.FloatTensor shape (C, L) = (9, 64)
        - y: torch.LongTensor scalar int64 in {0, 1, 2, 3, 4}
        """
        x = torch.from_numpy(self.windows[idx].copy())  # shape: (9, 64)
        y = torch.tensor(self.targets[idx], dtype=torch.long)
        return x, y

    def get_timestamp(self, idx: int) -> pd.Timestamp:
        """Mengembalikan timestamp UTC pada akhir window ke-idx."""
        return self.timestamps.iloc[idx]


def create_dataloaders(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    batch_size: int = 64,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    feature_channels: Optional[List[str]] = None,
    num_workers: int = 0,
    pin_memory: bool = False,
) -> Tuple[DataLoader, DataLoader, XAUTimeSeriesDataset, XAUTimeSeriesDataset]:
    """
    Membuat DataLoader untuk training dan testing.
    
    Training loader di-shuffle untuk stochastic gradient descent.
    Testing loader sequential tanpa shuffle untuk walk-forward temporal evaluation.
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
