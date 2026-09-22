"""
XAU_DEEP_SNIPER — Unit Tests: Pipeline Schema Validation
=========================================================
Menguji validasi skema, parsing timestamp, dan integritas data
menggunakan DataFrame sintetis.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import pathlib

# Tambahkan project root ke path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.pipeline.ingest import load_raw_csv, SchemaValidationError, validate_timestamp_monotonicity
from src.pipeline import config


@pytest.fixture
def synthetic_csv(tmp_path):
    """Buat file CSV sintetis yang valid untuk testing."""
    n_bars = 200
    start = pd.Timestamp("2023-01-02 00:00:00", tz="UTC")
    timestamps = pd.date_range(start, periods=n_bars, freq="30min")

    # Filter weekend
    timestamps = timestamps[timestamps.weekday < 5][:n_bars]

    np.random.seed(42)
    base_price = 1900.0
    noise = np.cumsum(np.random.randn(len(timestamps)) * 0.5)
    prices = base_price + noise

    df = pd.DataFrame({
        "timestamp_utc": timestamps.strftime("%Y-%m-%d %H:%M:%S"),
        "open": np.round(prices, 2),
        "high": np.round(prices + np.abs(np.random.randn(len(timestamps))) * 2, 2),
        "low": np.round(prices - np.abs(np.random.randn(len(timestamps))) * 2, 2),
        "close": np.round(prices + np.random.randn(len(timestamps)) * 0.3, 2),
        "volume": np.random.randint(100, 5000, len(timestamps)),
    })

    # Pastikan high >= max(open, close) dan low <= min(open, close)
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"] = df[["open", "close", "low"]].min(axis=1)

    csv_path = tmp_path / "test_xauusd.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def synthetic_csv_with_spread(tmp_path):
    """CSV sintetis dengan kolom spread."""
    n_bars = 50
    start = pd.Timestamp("2023-06-05 00:00:00", tz="UTC")
    timestamps = pd.date_range(start, periods=n_bars, freq="30min")
    timestamps = timestamps[timestamps.weekday < 5]

    np.random.seed(123)
    n = len(timestamps)

    df = pd.DataFrame({
        "timestamp_utc": timestamps.strftime("%Y-%m-%d %H:%M:%S"),
        "open": np.round(1950 + np.random.randn(n) * 2, 2),
        "high": np.round(1955 + np.abs(np.random.randn(n)) * 3, 2),
        "low": np.round(1945 - np.abs(np.random.randn(n)) * 3, 2),
        "close": np.round(1950 + np.random.randn(n) * 2, 2),
        "volume": np.random.randint(50, 3000, n),
        "spread": np.round(2.5 + np.random.rand(n) * 1.5, 1),
    })
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"] = df[["open", "close", "low"]].min(axis=1)

    csv_path = tmp_path / "test_xauusd_spread.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


class TestLoadRawCSV:
    """Test suite untuk load_raw_csv()."""

    def test_basic_load_succeeds(self, synthetic_csv):
        """CSV valid harus dimuat tanpa error."""
        df = load_raw_csv(synthetic_csv)
        assert len(df) > 0
        assert list(df.columns) == config.RAW_COLUMNS

    def test_timestamp_is_utc_aware(self, synthetic_csv):
        """Timestamp harus tz-aware UTC."""
        df = load_raw_csv(synthetic_csv)
        assert df["timestamp_utc"].dt.tz is not None
        assert str(df["timestamp_utc"].dt.tz) == "UTC"

    def test_timestamp_is_monotonic(self, synthetic_csv):
        """Timestamp harus strictly monotonic increasing setelah sort."""
        df = load_raw_csv(synthetic_csv)
        assert df["timestamp_utc"].is_monotonic_increasing

    def test_no_duplicate_timestamps(self, synthetic_csv):
        """Tidak boleh ada timestamp duplikat."""
        df = load_raw_csv(synthetic_csv)
        assert df["timestamp_utc"].duplicated().sum() == 0

    def test_spread_column_filled_nan_if_missing(self, synthetic_csv):
        """Jika CSV tidak punya kolom spread, harus diisi NaN."""
        df = load_raw_csv(synthetic_csv)
        assert "spread" in df.columns
        assert df["spread"].isna().all()

    def test_spread_column_preserved_if_present(self, synthetic_csv_with_spread):
        """Jika CSV punya kolom spread, data harus dipertahankan."""
        df = load_raw_csv(synthetic_csv_with_spread)
        assert "spread" in df.columns
        assert df["spread"].notna().all()

    def test_prices_positive(self, synthetic_csv):
        """Semua harga harus positif."""
        df = load_raw_csv(synthetic_csv)
        for col in ["open", "high", "low", "close"]:
            assert (df[col] > 0).all(), f"{col} memiliki nilai non-positif"

    def test_ohlc_integrity(self, synthetic_csv):
        """High >= max(O,C) dan Low <= min(O,C)."""
        df = load_raw_csv(synthetic_csv)
        assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
        assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()

    def test_missing_column_raises_error(self, tmp_path):
        """CSV tanpa kolom wajib harus raise SchemaValidationError."""
        csv_path = tmp_path / "bad.csv"
        df = pd.DataFrame({"timestamp_utc": ["2023-01-02"], "open": [1900]})
        df.to_csv(csv_path, index=False)
        with pytest.raises(SchemaValidationError):
            load_raw_csv(csv_path)

    def test_file_not_found_raises(self):
        """File yang tidak ada harus raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_raw_csv(pathlib.Path("nonexistent_file.csv"))

    def test_negative_price_raises_error(self, tmp_path):
        """Harga negatif harus raise SchemaValidationError."""
        csv_path = tmp_path / "neg_price.csv"
        df = pd.DataFrame({
            "timestamp_utc": ["2023-01-02 00:00:00", "2023-01-02 00:30:00"],
            "open": [1900, -100],
            "high": [1905, 1905],
            "low": [1895, -105],
            "close": [1902, 1902],
            "volume": [1000, 1000],
        })
        df.to_csv(csv_path, index=False)
        with pytest.raises(SchemaValidationError, match="harga <= 0"):
            load_raw_csv(csv_path)


class TestTimestampMonotonicity:
    """Test suite untuk validate_timestamp_monotonicity()."""

    def test_no_gaps_in_clean_data(self, synthetic_csv):
        """Data bersih yang berurutan tidak boleh ada gap internal."""
        df = load_raw_csv(synthetic_csv)
        result = validate_timestamp_monotonicity(df)
        assert result["is_monotonic"] is True

    def test_total_bars_correct(self, synthetic_csv):
        """Total bars harus sesuai jumlah baris DataFrame."""
        df = load_raw_csv(synthetic_csv)
        result = validate_timestamp_monotonicity(df)
        assert result["total_bars"] == len(df)
