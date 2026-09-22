"""
XAU_DEEP_SNIPER - Run Full Cleaning Pipeline on Real Data
==========================================================
Eksekusi end-to-end:
  1. Load raw CSV
  2. Validasi skema & integritas
  3. Cek timestamp monotonicity & gap
  4. Jalankan full cleaning (weekend, DST rollover, flat, bad tick)
  5. Generate & cetak quality report
  6. Simpan ke Parquet (clean) + JSON (report)
"""

import sys
import pathlib
import time

project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from pipeline import config
from pipeline.ingest import load_raw_csv, validate_timestamp_monotonicity
from pipeline.clean import run_full_cleaning_pipeline
from pipeline.quality_report import generate_quality_report, print_quality_report, save_quality_report


def main():
    print("=" * 72)
    print("XAU_DEEP_SNIPER - DATA CLEANING PIPELINE")
    print("=" * 72)

    raw_path = config.DATA_RAW_DIR / config.RAW_CSV_FILENAME
    print(f"\n[1/6] Loading raw CSV: {raw_path}")

    t0 = time.time()
    df_raw = load_raw_csv(raw_path)
    t1 = time.time()
    print(f"      OK - {len(df_raw)} bars loaded in {t1 - t0:.2f}s")
    print(f"      Date range: {df_raw['timestamp_utc'].min()} -> {df_raw['timestamp_utc'].max()}")

    print(f"\n[2/6] Validating timestamp monotonicity & gap detection...")
    mono_result = validate_timestamp_monotonicity(df_raw)
    print(f"      Monotonic: {mono_result['is_monotonic']}")
    print(f"      Total bars: {mono_result['total_bars']}")
    print(f"      Non-weekend gaps detected: {mono_result['gaps_detected']}")
    if mono_result['gaps_detected'] > 0:
        print(f"      First 10 gaps:")
        for g in mono_result['gaps'][:10]:
            print(f"        {g['from_ts']} -> {g['to_ts']} ({g['gap_minutes']:.0f} min, ~{g['missing_bars_estimate']} bars)")

    print(f"\n[3/6] Running full cleaning pipeline...")
    t2 = time.time()
    df_clean = run_full_cleaning_pipeline(df_raw)
    t3 = time.time()
    print(f"      Cleaning completed in {t3 - t2:.2f}s")

    print(f"\n[4/6] Generating quality report...")
    report = generate_quality_report(df_clean)

    print(f"\n[5/6] Quality Report:")
    report_text = print_quality_report(report)

    print(f"\n[6/6] Saving outputs...")

    config.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = config.DATA_PROCESSED_DIR / config.CLEAN_PARQUET_FILENAME
    df_clean.to_parquet(parquet_path, compression=config.PARQUET_COMPRESSION, index=False)
    parquet_size_mb = parquet_path.stat().st_size / (1024 * 1024)
    print(f"      Clean Parquet saved: {parquet_path} ({parquet_size_mb:.2f} MB)")

    report_path = save_quality_report(report)
    print(f"      Quality report saved: {report_path}")

    print("\n" + "=" * 72)
    print("PIPELINE SELESAI - RINGKASAN")
    print("=" * 72)
    print(f"  Raw bars loaded      : {len(df_raw)}")
    print(f"  Clean bars output    : {len(df_clean)}")
    print(f"  Bars removed         : {len(df_raw) - len(df_clean)} (weekend)")
    elig = report.get("entry_eligibility", {})
    print(f"  Entry eligible       : {elig.get('eligible_bars', '?')} / {elig.get('total_bars', '?')} ({elig.get('eligible_pct', '?')}%)")
    print(f"  Parquet output       : {parquet_path}")
    print(f"  Report output        : {report_path}")
    print("=" * 72)

    eligible_pct = elig.get("eligible_pct", 0)
    if eligible_pct >= 85:
        print("\n>>> VERDICT: DATA BERKUALITAS BAIK - Siap lanjut ke TAHAP 2")
    elif eligible_pct >= 70:
        print("\n>>> VERDICT: DATA PERLU REVIEW - Beberapa anomali, perlu investigasi")
    else:
        print("\n>>> VERDICT: DATA BERMASALAH - Terlalu banyak anomali")


if __name__ == "__main__":
    main()
