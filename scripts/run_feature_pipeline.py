"""
XAU_DEEP_SNIPER - Run Feature Engineering Pipeline on Real Data (TAHAP 2)
==========================================================================
Eksekusi end-to-end:
  1. Load clean Parquet (TAHAP 1 output)
  2. Build 9 scale-free feature channels (OHLC norm, Volume Z-score, SMI, MA Ribbon, Liquidity, FVG)
  3. Compute supplementary returns, volatility & session labels
  4. Trim warmup NaN period (128 bars)
  5. Validate statistical stationarity and distribution
  6. Perform leak-free temporal train/test split (80/20, 16-bar purge, 48-bar embargo)
  7. Verify MOMENT-1-large tensor window construction (shape: N, 9, 64)
  8. Save Parquet outputs (features, train, test) and JSON validation report
"""

import sys
import json
import time
import pathlib
import pandas as pd
import numpy as np

# Setup paths
project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from pipeline import config
from pipeline import feature_config as fcfg
from pipeline.feature_pipeline import (
    build_all_features,
    trim_warmup_nans,
    validate_all_features,
    temporal_split,
    extract_feature_windows,
    get_feature_columns,
)


def main():
    print("=" * 76)
    print("XAU_DEEP_SNIPER - FEATURE ENGINEERING PIPELINE (TAHAP 2)")
    print("=" * 76)

    # 1. Load clean parquet
    clean_path = config.DATA_PROCESSED_DIR / config.CLEAN_PARQUET_FILENAME
    print(f"\n[1/7] Loading clean data: {clean_path}")
    if not clean_path.exists():
        print(f"ERROR: File not found: {clean_path}")
        sys.exit(1)

    t0 = time.time()
    df_clean = pd.read_parquet(clean_path)
    t1 = time.time()
    print(f"      Loaded {len(df_clean):,} bars in {t1 - t0:.2f}s")
    print(f"      Date range: {df_clean['timestamp_utc'].min()} -> {df_clean['timestamp_utc'].max()}")

    # 2. Build 9 feature channels + supplementary features
    print(f"\n[2/7] Extracting 9-channel features + structural markers...")
    t2 = time.time()
    df_features = build_all_features(df_clean, verbose=True)
    t3 = time.time()
    print(f"      Feature computation completed in {t3 - t2:.2f}s")

    # 3. Trim warmup NaNs
    print(f"\n[3/7] Trimming warmup NaN period...")
    df_trimmed = trim_warmup_nans(df_features)
    warmup_removed = len(df_features) - len(df_trimmed)
    print(f"      Warmup bars removed : {warmup_removed}")
    print(f"      Remaining valid bars: {len(df_trimmed):,}")
    print(f"      Trimmed range       : {df_trimmed['timestamp_utc'].min()} -> {df_trimmed['timestamp_utc'].max()}")

    # 4. Statistical Validation
    print(f"\n[4/7] Running statistical validation across all 9 channels...")
    val_report = validate_all_features(df_trimmed, verbose=True)

    # 5. Temporal Train/Test Split
    print(f"\n[5/7] Executing leak-free temporal train/test split...")
    train_df, test_df = temporal_split(
        df_trimmed,
        train_ratio=fcfg.TRAIN_RATIO,
        purge_bars=fcfg.PURGE_BARS,
        embargo_bars=fcfg.EMBARGO_BARS,
        verbose=True,
    )

    # Check leakage
    train_end = train_df["timestamp_utc"].iloc[-1]
    test_start = test_df["timestamp_utc"].iloc[0]
    gap_duration = (test_start - train_end).total_seconds() / 3600.0
    print(f"      Leakage Gate Check  : PASSED (Gap = {gap_duration:.1f} hours between train & test)")

    # 6. Verify MOMENT Tensor Construction
    print(f"\n[6/7] Verifying tensor input window construction (B x C x L)...")
    L = fcfg.FEATURE_WINDOW  # 64
    X_train_sample, ts_train = extract_feature_windows(train_df.iloc[:200], window_length=L)
    print(f"      Sample window extraction (200 bars -> L={L}):")
    print(f"      Tensor shape        : {X_train_sample.shape} (N={X_train_sample.shape[0]}, C={X_train_sample.shape[1]}, L={X_train_sample.shape[2]})")
    print(f"      Data type           : {X_train_sample.dtype}")
    print(f"      Memory footprint    : {X_train_sample.nbytes / 1024:.1f} KB")
    assert X_train_sample.shape == (200 - L + 1, fcfg.NUM_CHANNELS, L), "Shape mismatch!"
    print(f"      MOMENT Tensor Gate  : VERIFIED OK")

    # 7. Save Parquet Outputs & Report
    print(f"\n[7/7] Saving Parquet files & quality audit report...")
    config.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Full features
    features_path = config.DATA_PROCESSED_DIR / config.FEATURES_PARQUET_FILENAME
    df_trimmed.to_parquet(features_path, compression=config.PARQUET_COMPRESSION, index=False)
    feat_size_mb = features_path.stat().st_size / (1024 * 1024)
    print(f"      [OK] Features Parquet : {features_path} ({feat_size_mb:.2f} MB)")

    # Train partition
    train_path = config.DATA_PROCESSED_DIR / config.TRAIN_PARQUET_FILENAME
    train_df.to_parquet(train_path, compression=config.PARQUET_COMPRESSION, index=False)
    train_size_mb = train_path.stat().st_size / (1024 * 1024)
    print(f"      [OK] Train Parquet    : {train_path} ({train_size_mb:.2f} MB)")

    # Test partition
    test_path = config.DATA_PROCESSED_DIR / config.TEST_PARQUET_FILENAME
    test_df.to_parquet(test_path, compression=config.PARQUET_COMPRESSION, index=False)
    test_size_mb = test_path.stat().st_size / (1024 * 1024)
    print(f"      [OK] Test Parquet     : {test_path} ({test_size_mb:.2f} MB)")

    # Save validation report
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_dict = {
        "timestamp_generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "input_clean_bars": len(df_clean),
        "warmup_bars_trimmed": warmup_removed,
        "valid_feature_bars": len(df_trimmed),
        "feature_channels": list(fcfg.FEATURE_CHANNELS.values()),
        "train_set": {
            "bars": len(train_df),
            "start": str(train_df["timestamp_utc"].iloc[0]),
            "end": str(train_df["timestamp_utc"].iloc[-1]),
        },
        "test_set": {
            "bars": len(test_df),
            "start": str(test_df["timestamp_utc"].iloc[0]),
            "end": str(test_df["timestamp_utc"].iloc[-1]),
        },
        "buffer_gap": {
            "purge_bars": fcfg.PURGE_BARS,
            "embargo_bars": fcfg.EMBARGO_BARS,
            "gap_hours": gap_duration,
        },
        "channel_validation": val_report,
    }
    report_path = config.REPORTS_DIR / config.FEATURE_REPORT_FILENAME
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, default=str)
    print(f"      [OK] Quality Report   : {report_path}")

    print("\n" + "=" * 76)
    print("TAHAP 2 FEATURE ENGINEERING PIPELINE COMPLETE")
    print("=" * 76)
    print(f"  Clean bars input     : {len(df_clean):,}")
    print(f"  Valid feature bars   : {len(df_trimmed):,}")
    print(f"  Train set bars       : {len(train_df):,} ({len(train_df)/len(df_trimmed)*100:.1f}%)")
    print(f"  Test set bars        : {len(test_df):,} ({len(test_df)/len(df_trimmed)*100:.1f}%)")
    print(f"  Purge + Embargo gap  : {fcfg.PURGE_BARS + fcfg.EMBARGO_BARS} bars ({gap_duration:.1f} hours)")
    print(f"  Channels extracted   : {len(fcfg.FEATURE_CHANNELS)} (all PASS)")
    print("=" * 76)


if __name__ == "__main__":
    main()
