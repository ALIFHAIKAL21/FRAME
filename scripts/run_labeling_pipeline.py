"""
XAU_DEEP_SNIPER - Run Labeling Pipeline on Real Data (TAHAP 3)
===============================================================
Eksekusi end-to-end:
  1. Load feature dataset (TAHAP 2 output)
  2. Terapkan Hard Deterministic News Blackout Gate (NFP, CPI, FOMC T +- 30 min)
  3. Eksekusi Net-Cost Triple Barrier Labeling (K=16, spread aktual + komisi institusional)
  4. Hitung Class-Balanced Focal Loss weights (alpha_c, gamma=2.0)
  5. Bagi dataset berlabel ke partisi Train (80%) dan Test Holdout (20%) dengan Purge & Embargo
  6. Simpan output Parquet dan laporan audit labeling_quality_report.json
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
from pipeline.news_blackout import apply_news_blackout_gate, generate_high_impact_calendar
from pipeline.feature_pipeline import temporal_split
from labeling.triple_barrier import label_triple_barrier, ACTION_CLASSES, TIME_BARRIER_BARS
from labeling.focal_weights import compute_focal_weights


def main():
    print("=" * 76)
    print("XAU_DEEP_SNIPER - LABELING & NEWS BLACKOUT PIPELINE (TAHAP 3)")
    print("=" * 76)

    # 1. Load feature dataset
    features_path = config.DATA_PROCESSED_DIR / config.FEATURES_PARQUET_FILENAME
    print(f"\n[1/6] Loading feature data: {features_path}")
    if not features_path.exists():
        print(f"ERROR: File not found: {features_path}")
        sys.exit(1)

    t0 = time.time()
    df_feat = pd.read_parquet(features_path)
    t1 = time.time()
    print(f"      Loaded {len(df_feat):,} bars in {t1 - t0:.2f}s")
    print(f"      Date range: {df_feat['timestamp_utc'].min()} -> {df_feat['timestamp_utc'].max()}")

    # 2. Apply News Blackout Gate
    print(f"\n[2/6] Applying Hard Deterministic News Blackout Gate...")
    t2 = time.time()
    cal = generate_high_impact_calendar(2021, 2026)
    df_gated = apply_news_blackout_gate(df_feat, events_df=cal, blackout_minutes=30, verbose=True)
    t3 = time.time()
    print(f"      News Gate applied in {t3 - t2:.2f}s")

    # 3. Execute Net-Cost Triple Barrier Labeling
    print(f"\n[3/6] Simulating Net-Cost Triple Barrier (K={TIME_BARRIER_BARS} bars / 8 hours)...")
    t4 = time.time()
    df_labeled = label_triple_barrier(df_gated, time_barrier=TIME_BARRIER_BARS, verbose=True)
    t5 = time.time()
    print(f"      Triple Barrier simulation completed in {t5 - t4:.2f}s")

    # 4. Compute Class-Balanced Focal Loss Weights
    print(f"\n[4/6] Computing Class-Balanced Focal Loss Weights (gamma=2.0)...")
    # Evaluasi hanya pada bar yang eligible dan bukan tail K bar
    eval_bars = df_labeled["action"].iloc[:-TIME_BARRIER_BARS]
    focal_info = compute_focal_weights(eval_bars, num_classes=5)
    print(f"      Class Distribution & Alpha Weights:")
    for c in range(5):
        cnt = focal_info["class_counts"][c]
        pct = focal_info["class_percentages"][c]
        alpha = focal_info["alpha_weights"][c]
        name = ACTION_CLASSES[c]
        print(f"        Class {c} ({name:7s}): {cnt:6,} bars ({pct:5.2f}%) -> alpha = {alpha:.4f}")

    # 5. Temporal Train/Test Split (Preserving Purge & Embargo)
    print(f"\n[5/6] Performing Temporal Train/Test Partitioning...")
    train_labeled, test_labeled = temporal_split(
        df_labeled,
        train_ratio=fcfg.TRAIN_RATIO,
        purge_bars=fcfg.PURGE_BARS,
        embargo_bars=fcfg.EMBARGO_BARS,
        verbose=True,
    )

    # Compute focal weights specifically on training set (for model loss function)
    train_focal_info = compute_focal_weights(train_labeled["action"], num_classes=5)
    print(f"\n      Train-Set Focal Loss Weights (To be used in MOMENT loss):")
    for c in range(5):
        print(f"        Class {c} ({ACTION_CLASSES[c]:7s}): alpha = {train_focal_info['alpha_weights'][c]:.4f}")

    # 6. Save Labeled Parquets & Report
    print(f"\n[6/6] Saving labeled Parquets & quality audit report...")
    config.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Full labeled
    labeled_path = config.DATA_PROCESSED_DIR / config.LABELED_PARQUET_FILENAME
    df_labeled.to_parquet(labeled_path, compression=config.PARQUET_COMPRESSION, index=False)
    labeled_size_mb = labeled_path.stat().st_size / (1024 * 1024)
    print(f"      [OK] Labeled Parquet       : {labeled_path} ({labeled_size_mb:.2f} MB)")

    # Train labeled
    train_labeled_path = config.DATA_PROCESSED_DIR / config.TRAIN_LABELED_PARQUET_FILENAME
    train_labeled.to_parquet(train_labeled_path, compression=config.PARQUET_COMPRESSION, index=False)
    train_size_mb = train_labeled_path.stat().st_size / (1024 * 1024)
    print(f"      [OK] Train Labeled Parquet : {train_labeled_path} ({train_size_mb:.2f} MB)")

    # Test labeled
    test_labeled_path = config.DATA_PROCESSED_DIR / config.TEST_LABELED_PARQUET_FILENAME
    test_labeled.to_parquet(test_labeled_path, compression=config.PARQUET_COMPRESSION, index=False)
    test_size_mb = test_labeled_path.stat().st_size / (1024 * 1024)
    print(f"      [OK] Test Labeled Parquet  : {test_labeled_path} ({test_size_mb:.2f} MB)")

    # Audit report
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_dict = {
        "timestamp_generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "total_bars": len(df_labeled),
        "evaluated_bars": len(df_labeled) - TIME_BARRIER_BARS,
        "news_blackout": {
            "blackout_bars": int(df_labeled["is_news_blackout"].sum()),
            "blackout_pct": round(float(df_labeled["is_news_blackout"].sum() / len(df_labeled) * 100), 2),
            "macro_events_count": len(cal),
        },
        "overall_class_distribution": focal_info,
        "train_set": {
            "bars": len(train_labeled),
            "start": str(train_labeled["timestamp_utc"].iloc[0]),
            "end": str(train_labeled["timestamp_utc"].iloc[-1]),
            "class_distribution": train_focal_info,
        },
        "test_set": {
            "bars": len(test_labeled),
            "start": str(test_labeled["timestamp_utc"].iloc[0]),
            "end": str(test_labeled["timestamp_utc"].iloc[-1]),
            "class_distribution": compute_focal_weights(test_labeled["action"], num_classes=5),
        },
        "parameters": {
            "time_barrier_bars": TIME_BARRIER_BARS,
            "commission_per_oz": 0.035,
            "default_spread_pips": 0.75,
            "purge_bars": fcfg.PURGE_BARS,
            "embargo_bars": fcfg.EMBARGO_BARS,
        }
    }
    report_path = config.REPORTS_DIR / config.LABELING_REPORT_FILENAME
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, default=str)
    print(f"      [OK] Quality Report        : {report_path}")

    print("\n" + "=" * 76)
    print("TAHAP 3 LABELING & NEWS BLACKOUT PIPELINE COMPLETE")
    print("=" * 76)
    print(f"  Total bars labeled   : {len(df_labeled):,}")
    print(f"  Blackout bars        : {df_labeled['is_news_blackout'].sum():,} ({df_labeled['is_news_blackout'].sum()/len(df_labeled)*100:.2f}%)")
    print(f"  Train labeled bars   : {len(train_labeled):,}")
    print(f"  Test labeled bars    : {len(test_labeled):,}")
    print(f"  Train Class breakdown:")
    for c in range(5):
        cnt = train_focal_info['class_counts'][c]
        pct = train_focal_info['class_percentages'][c]
        print(f"    {ACTION_CLASSES[c]:7s}: {cnt:5,} ({pct:5.2f}%)")
    print("=" * 76)


if __name__ == "__main__":
    main()
