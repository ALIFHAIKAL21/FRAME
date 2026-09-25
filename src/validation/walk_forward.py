"""
XAU_DEEP_SNIPER - Purged Walk-Forward Cross-Validation (BAB 9.1)
=================================================================
Implementasi protokol Marcos Lopez de Prado (Advances in Financial
Machine Learning) untuk validasi temporal tanpa kebocoran data.

Fitur:
- 5-Fold temporal expanding walk-forward splits
- Purge gap: H bar (default 16 bar, horizon triple barrier)
- Embargo gap: E bar (default 48 bar / 24 jam) di antara train & test
- Zero overlap guarantee: test set tidak pernah mengandung data train
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np
import pandas as pd


@dataclass
class WalkForwardFold:
    """Satu fold dari walk-forward split."""
    fold_idx: int
    train_start_idx: int
    train_end_idx: int    # inclusive
    test_start_idx: int
    test_end_idx: int     # inclusive
    purge_gap: int
    embargo_gap: int
    train_size: int
    test_size: int

    @property
    def total_excluded(self) -> int:
        return self.purge_gap + self.embargo_gap


class PurgedWalkForwardCV:
    """
    Generator temporal walk-forward cross-validation splits dengan
    purge gap dan embargo gap untuk mencegah kebocoran autokorelasi.

    Parameters
    ----------
    n_folds : int
        Jumlah fold walk-forward (default 5).
    purge_bars : int
        Jumlah bar yang dipurge (dihapus) antara akhir train dan
        awal test untuk mengeliminasi kebocoran label overlap.
        Default: 16 (horizon triple barrier H = 16 bar M30 = 8 jam).
    embargo_bars : int
        Jumlah bar embargo tambahan setelah purge gap sebagai
        buffer keamanan autokorelasi residual.
        Default: 48 (24 jam pada M30).
    min_train_size : int
        Ukuran minimum training set yang diizinkan per fold.
        Default: 5000 bar (~104 hari trading).
    expanding : bool
        Jika True, training set terus membesar (expanding window).
        Jika False, rolling window dengan ukuran tetap.
        Default: True (expanding, standar institusional).
    """

    def __init__(
        self,
        n_folds: int = 5,
        purge_bars: int = 16,
        embargo_bars: int = 48,
        min_train_size: int = 5000,
        expanding: bool = True,
    ):
        if n_folds < 2:
            raise ValueError("n_folds must be >= 2")
        if purge_bars < 0 or embargo_bars < 0:
            raise ValueError("purge_bars and embargo_bars must be >= 0")

        self.n_folds = n_folds
        self.purge_bars = purge_bars
        self.embargo_bars = embargo_bars
        self.min_train_size = min_train_size
        self.expanding = expanding

    def split(
        self,
        n_samples: int,
    ) -> List[WalkForwardFold]:
        """
        Membuat temporal walk-forward splits.

        Parameters
        ----------
        n_samples : int
            Total jumlah sampel (bar) dalam dataset penuh.

        Returns
        -------
        List[WalkForwardFold]
            Daftar fold dengan indeks train/test yang valid.
        """
        total_gap = self.purge_bars + self.embargo_bars

        # Hitung ukuran test per fold
        # Bagi sisa setelah min_train_size secara proporsional
        available_for_test = n_samples - self.min_train_size - total_gap
        if available_for_test <= 0:
            raise ValueError(
                f"Dataset terlalu kecil ({n_samples} bars) untuk "
                f"min_train={self.min_train_size}, gap={total_gap}"
            )

        test_size_per_fold = available_for_test // self.n_folds
        if test_size_per_fold < 100:
            raise ValueError(
                f"Test size per fold terlalu kecil ({test_size_per_fold}). "
                f"Kurangi n_folds atau min_train_size."
            )

        folds = []
        for fold_idx in range(self.n_folds):
            # Test set boundaries
            test_end = n_samples - 1 - (self.n_folds - 1 - fold_idx) * test_size_per_fold
            test_start = test_end - test_size_per_fold + 1

            # Train set: semua data sebelum purge+embargo gap
            train_end = test_start - total_gap - 1

            if self.expanding:
                train_start = 0
            else:
                # Rolling window: ukuran train tetap = min_train_size
                train_start = max(0, train_end - self.min_train_size + 1)

            train_size = train_end - train_start + 1
            test_size = test_end - test_start + 1

            # Validasi fold
            if train_size < self.min_train_size and fold_idx > 0:
                # Skip fold jika training set terlalu kecil
                continue

            if train_end < 0 or test_start < 0:
                continue

            fold = WalkForwardFold(
                fold_idx=fold_idx,
                train_start_idx=train_start,
                train_end_idx=train_end,
                test_start_idx=test_start,
                test_end_idx=test_end,
                purge_gap=self.purge_bars,
                embargo_gap=self.embargo_bars,
                train_size=train_size,
                test_size=test_size,
            )
            folds.append(fold)

        return folds

    def split_dataframe(
        self,
        df: pd.DataFrame,
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame, WalkForwardFold]]:
        """
        Membuat walk-forward splits langsung pada DataFrame.

        Returns
        -------
        List of (train_df, test_df, fold_info) tuples.
        """
        n_samples = len(df)
        folds = self.split(n_samples)
        results = []

        for fold in folds:
            train_df = df.iloc[fold.train_start_idx : fold.train_end_idx + 1].copy()
            test_df = df.iloc[fold.test_start_idx : fold.test_end_idx + 1].copy()
            results.append((train_df, test_df, fold))

        return results

    def validate_no_leakage(
        self,
        folds: List[WalkForwardFold],
    ) -> bool:
        """
        Memverifikasi bahwa tidak ada overlap antara train dan test
        pada setiap fold, dan purge+embargo gaps benar-benar diterapkan.

        Returns True jika semua fold valid, raises AssertionError jika tidak.
        """
        for fold in folds:
            gap = fold.test_start_idx - fold.train_end_idx - 1
            assert gap >= fold.purge_gap + fold.embargo_gap, (
                f"Fold {fold.fold_idx}: Gap ({gap}) < required "
                f"({fold.purge_gap + fold.embargo_gap})"
            )
            assert fold.train_end_idx < fold.test_start_idx, (
                f"Fold {fold.fold_idx}: Train end ({fold.train_end_idx}) "
                f">= Test start ({fold.test_start_idx})"
            )
            assert fold.train_size > 0 and fold.test_size > 0, (
                f"Fold {fold.fold_idx}: Empty train ({fold.train_size}) "
                f"or test ({fold.test_size})"
            )

        # Verifikasi antar-fold: test sets tidak overlap
        for i in range(len(folds)):
            for j in range(i + 1, len(folds)):
                fi, fj = folds[i], folds[j]
                assert (fi.test_end_idx < fj.test_start_idx or
                        fj.test_end_idx < fi.test_start_idx), (
                    f"Fold {fi.fold_idx} dan {fj.fold_idx} test sets overlap"
                )

        return True

    def summary(self, folds: List[WalkForwardFold]) -> str:
        """Menghasilkan ringkasan tabel fold untuk audit visual."""
        lines = [
            "=" * 90,
            "PURGED WALK-FORWARD CROSS-VALIDATION SUMMARY",
            f"  n_folds={self.n_folds}, purge={self.purge_bars} bars, "
            f"embargo={self.embargo_bars} bars, expanding={self.expanding}",
            "=" * 90,
            f"{'Fold':<6} {'Train Range':<25} {'Train Size':<12} "
            f"{'Gap':<8} {'Test Range':<25} {'Test Size':<12}",
            "-" * 90,
        ]
        for f in folds:
            lines.append(
                f"  {f.fold_idx:<4} [{f.train_start_idx:>6} - {f.train_end_idx:>6}] "
                f"{f.train_size:>10,} "
                f"{f.total_excluded:>6} "
                f"[{f.test_start_idx:>6} - {f.test_end_idx:>6}] "
                f"{f.test_size:>10,}"
            )
        lines.append("=" * 90)
        return "\n".join(lines)
