import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
"""
XAU_DEEP_SNIPER — TAHAP 6: End-to-End Walk-Forward Validation & Scientific Gates Audit
========================================================================================
Script CLI yang mengeksekusi:
1. Load sealed holdout test data (11,618 bar, 1 tahun)
2. Load best pretrained MOMENT-1-large checkpoint
3. Run GPU inference (AMP FP16) untuk mendapatkan probabilitas prediksi
4. Run realistic bar-by-bar backtest dengan seluruh gerbang risiko
5. Run Monte Carlo stress test (1,000 trade shuffle permutations)
6. Audit 3 Hard Scientific Gates
7. Simpan laporan ke reports/scientific_gates_audit.json

Usage:
    .venv\\Scripts\\python.exe scripts/run_walk_forward_validation.py --tau 0.35 --slippage-pip 0.3
"""

import argparse
import json
import sys
import time
import pathlib
import numpy as np
import pandas as pd
import torch

# Add project root to path
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.config import (
    DATA_PROCESSED_DIR, REPORTS_DIR,
    TEST_LABELED_PARQUET_FILENAME,
)
from src.models.dataset import XAUTimeSeriesDataset, DEFAULT_FEATURE_CHANNELS
from src.validation.backtest_engine import RealisticBacktestEngine
from src.validation.monte_carlo import MonteCarloStressTester
from src.validation.scientific_gates import ScientificGatesAuditor
from src.validation.walk_forward import PurgedWalkForwardCV


def compute_atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Menghitung ATR(14) dari OHLC data."""
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    tr = np.zeros(len(df))
    tr[0] = high[0] - low[0]
    for i in range(1, len(df)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )

    # EMA ATR
    atr = np.zeros(len(df))
    atr[:period] = np.mean(tr[:period])
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(df)):
        atr[i] = tr[i] * multiplier + atr[i - 1] * (1 - multiplier)

    return atr


def load_model(checkpoint_path: str, device: str):
    """Load model checkpoint dan kembalikan model siap inferensi."""
    print(f"[LOAD] Loading checkpoint: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)

    # Auto-detect LoRA rank from checkpoint
    detected_r = 16
    for k, v in checkpoint["model_state_dict"].items():
        if "lora_A" in k:
            detected_r = v.shape[0]
            break
    detected_alpha = detected_r * 2
    print(f"[LOAD] Auto-detected LoRA rank: {detected_r}, alpha: {detected_alpha}")

    # Coba load PretrainedMOMENTClassifier dulu, fallback ke MOMENTClassifier
    try:
        from src.models.moment_model import PretrainedMOMENTClassifier
        model = PretrainedMOMENTClassifier(
            num_classes=5,
            dropout=0.2,
            lora_r=detected_r,
            lora_alpha=detected_alpha,
        )
        model.load_state_dict(checkpoint["model_state_dict"])
        print("[LOAD] Loaded PretrainedMOMENTClassifier (342M params)")
    except Exception as e:
        print(f"[LOAD] PretrainedMOMENTClassifier failed ({e}), trying MOMENTClassifier...")
        from src.models.moment_model import MOMENTClassifier, MOMENTConfig
        config = checkpoint.get("config", None)
        if config is None:
            config = MOMENTConfig(use_lora=True, lora_r=detected_r, lora_alpha=detected_alpha)
        model = MOMENTClassifier(config)
        model.load_state_dict(checkpoint["model_state_dict"])
        print("[LOAD] Loaded MOMENTClassifier")

    model.to(device)
    model.eval()

    summary = model.parameter_summary()
    print(f"[LOAD] Total params: {summary['total_parameters']:,}")
    print(f"[LOAD] Trainable:    {summary['trainable_parameters']:,} ({summary['trainable_percentage']}%)")

    return model


def run_inference(
    model: torch.nn.Module,
    dataset: XAUTimeSeriesDataset,
    device: str,
    batch_size: int = 64,
    use_amp: bool = True,
) -> np.ndarray:
    """Jalankan inferensi pada seluruh dataset, kembalikan probabilitas (N, 5)."""
    from torch.utils.data import DataLoader

    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=(device == "cuda"),
    )

    all_probs = []
    model.eval()

    with torch.no_grad():
        for x_batch, _ in loader:
            x_batch = x_batch.to(device, non_blocking=True)
            with torch.amp.autocast(device_type="cuda", dtype=torch.float16, enabled=(use_amp and device == "cuda")):
                logits = model(x_batch)
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
            all_probs.append(probs)

    predictions = np.concatenate(all_probs, axis=0)
    return predictions


def main():
    parser = argparse.ArgumentParser(
        description="XAU_DEEP_SNIPER TAHAP 6: Walk-Forward Validation & Scientific Gates Audit"
    )
    parser.add_argument("--tau", type=float, default=0.35,
                        help="Confidence threshold tau (default: 0.35)")
    parser.add_argument("--slippage-pip", type=float, default=0.3,
                        help="Adverse slippage in pips (default: 0.3)")
    parser.add_argument("--spread-pip", type=float, default=0.75,
                        help="Spread in pips (default: 0.75)")
    parser.add_argument("--commission", type=float, default=3.50,
                        help="Commission per lot USD (default: 3.50)")
    parser.add_argument("--initial-equity", type=float, default=10000.0,
                        help="Initial equity USD (default: 10000)")
    parser.add_argument("--checkpoint", type=str,
                        default=str(PROJECT_ROOT / "checkpoints" / "best_moment_pretrained_lora.pt"),
                        help="Path to model checkpoint")
    parser.add_argument("--mc-iterations", type=int, default=1000,
                        help="Monte Carlo iterations (default: 1000)")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Inference batch size (default: 64)")
    parser.add_argument("--cpu", action="store_true",
                        help="Force CPU inference")
    args = parser.parse_args()

    # =========================================================================
    # STEP 1: Load Sealed Holdout Test Data
    # =========================================================================
    print("\n" + "=" * 80)
    print("TAHAP 6: WALK-FORWARD VALIDATION & SCIENTIFIC GATES AUDIT")
    print("=" * 80)

    test_path = DATA_PROCESSED_DIR / TEST_LABELED_PARQUET_FILENAME
    print(f"\n[STEP 1] Loading sealed holdout test data: {test_path}")
    df_test = pd.read_parquet(test_path)
    print(f"  Loaded {len(df_test):,} bars ({df_test.timestamp_utc.min()} to {df_test.timestamp_utc.max()})")
    print(f"  Action distribution:\n{df_test.action.value_counts().sort_index().to_string()}")

    # Walk-Forward CV summary (informational)
    wfcv = PurgedWalkForwardCV(n_folds=5, purge_bars=16, embargo_bars=48)
    try:
        folds = wfcv.split(len(df_test))
        print(f"\n{wfcv.summary(folds)}")
        wfcv.validate_no_leakage(folds)
        print("  [OK] Walk-Forward CV: Zero leakage verified")
    except ValueError as e:
        print(f"  [INFO] Walk-Forward CV: {e}")
        print("  [INFO] Proceeding with full holdout validation instead")

    # =========================================================================
    # STEP 2: Load Foundation Model Checkpoint
    # =========================================================================
    device = "cpu" if args.cpu else ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n[STEP 2] Device: {device}")

    if device == "cuda":
        gpu = torch.cuda.get_device_properties(0)
        print(f"  GPU: {gpu.name} ({gpu.total_memory / (1024**3):.1f} GB VRAM)")

    model = load_model(args.checkpoint, device)

    # =========================================================================
    # STEP 3: Run GPU Inference
    # =========================================================================
    print(f"\n[STEP 3] Running model inference on {len(df_test):,} bars...")

    dataset = XAUTimeSeriesDataset(
        df_test,
        sequence_length=64,
        feature_channels=DEFAULT_FEATURE_CHANNELS,
        target_column="action",
    )
    print(f"  Dataset: {len(dataset):,} windows (64-bar sliding window)")

    t0 = time.time()
    predictions = run_inference(model, dataset, device, batch_size=args.batch_size)
    t1 = time.time()

    print(f"  Inference complete: {predictions.shape} in {t1 - t0:.1f}s")
    print(f"  Mean P(HOLD): {predictions[:, 0].mean():.3f}")
    print(f"  Mean P(BUY_1R): {predictions[:, 1].mean():.3f}")
    print(f"  Mean P(BUY_2R): {predictions[:, 2].mean():.3f}")
    print(f"  Mean P(SELL_1R): {predictions[:, 3].mean():.3f}")
    print(f"  Mean P(SELL_2R): {predictions[:, 4].mean():.3f}")

    # Non-HOLD precision preview
    pred_classes = np.argmax(predictions, axis=1)
    true_labels = dataset.targets
    non_hold_mask = pred_classes > 0
    if non_hold_mask.sum() > 0:
        non_hold_acc = (pred_classes[non_hold_mask] == true_labels[non_hold_mask]).mean()
        print(f"\n  Non-HOLD signals: {non_hold_mask.sum():,} / {len(predictions):,} ({non_hold_mask.mean()*100:.1f}%)")
        print(f"  Non-HOLD accuracy: {non_hold_acc*100:.1f}%")

    # =========================================================================
    # STEP 4: Run Realistic Backtest
    # =========================================================================
    print(f"\n[STEP 4] Running realistic bar-by-bar backtest...")
    print(f"  Parameters: tau={args.tau}, spread={args.spread_pip}pip, "
          f"slippage={args.slippage_pip}pip, commission=${args.commission}/lot")

    atr_values = compute_atr(df_test, period=14)

    engine = RealisticBacktestEngine(
        initial_equity=args.initial_equity,
        risk_fraction=0.01,
        confidence_tau=args.tau,
        sl_atr_multiplier=1.5,
        spread_pip=args.spread_pip,
        commission_per_lot=args.commission,
        slippage_pip=args.slippage_pip,
        time_barrier_bars=16,
    )

    t0 = time.time()
    bt_result = engine.run(df_test, predictions, atr_values)
    t1 = time.time()

    print(f"  Backtest complete in {t1 - t0:.1f}s")
    engine.print_report(bt_result)

    # =========================================================================
    # STEP 5: Monte Carlo Stress Test
    # =========================================================================
    print(f"\n[STEP 5] Running Monte Carlo stress test ({args.mc_iterations:,} iterations)...")

    if bt_result.total_trades > 0:
        trade_pnls = np.array([t.pnl_net for t in bt_result.trades])

        # Estimate trades per week
        if len(bt_result.trades) >= 2:
            first_ts = bt_result.trades[0].entry_timestamp
            last_ts = bt_result.trades[-1].exit_timestamp
            days_span = (last_ts - first_ts).total_seconds() / 86400
            weeks_span = max(1, days_span / 7)
            trades_per_week = bt_result.total_trades / weeks_span
        else:
            trades_per_week = 5.0

        mc_tester = MonteCarloStressTester(
            n_iterations=args.mc_iterations,
            random_seed=42,
        )
        t0 = time.time()
        mc_result = mc_tester.run(
            trade_pnls,
            initial_equity=args.initial_equity,
            avg_trades_per_week=trades_per_week,
        )
        t1 = time.time()
        print(f"  Monte Carlo complete in {t1 - t0:.1f}s")
        mc_tester.print_report(mc_result)
    else:
        print("  [SKIP] No trades to simulate Monte Carlo")
        mc_result = None

    # =========================================================================
    # STEP 6: 3 Hard Scientific Gates Audit
    # =========================================================================
    print(f"\n[STEP 6] Running 3 Hard Scientific Gates Audit...")

    auditor = ScientificGatesAuditor(
        min_sharpe=1.4,
        min_non_hold_precision=0.55,
        max_mc_p95_drawdown=-0.18,
        min_net_profit_factor=1.35,
    )

    # Konvergensi model dari training report (dari TAHAP 4)
    training_report_path = REPORTS_DIR / "model_training_report.json"
    val_convergence_stable = True  # Default
    if training_report_path.exists():
        try:
            with open(training_report_path, "r") as f:
                tr_report = json.load(f)
            val_losses = tr_report.get("history", {}).get("val_loss", [])
            if len(val_losses) >= 3:
                # Convergence check: val loss di 3 epoch terakhir tidak naik monoton
                last3 = val_losses[-3:]
                val_convergence_stable = not (last3[0] < last3[1] < last3[2])
        except Exception:
            pass

    audit_report = auditor.full_audit(
        bt_result,
        mc_result,
        val_convergence_stable=val_convergence_stable,
    )

    auditor.print_audit(audit_report)

    # =========================================================================
    # STEP 7: Save Reports
    # =========================================================================
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Save Scientific Gates Audit
    audit_path = REPORTS_DIR / "scientific_gates_audit.json"
    auditor.save_report(audit_report, audit_path)
    print(f"\n[SAVE] Scientific Gates Audit Report: {audit_path}")

    # Save Backtest Summary
    bt_summary = {
        "initial_equity": bt_result.initial_equity,
        "final_equity": bt_result.final_equity,
        "total_trades": bt_result.total_trades,
        "winning_trades": bt_result.winning_trades,
        "losing_trades": bt_result.losing_trades,
        "win_rate": bt_result.win_rate,
        "net_pnl": bt_result.net_pnl,
        "net_profit_factor": bt_result.net_profit_factor,
        "sharpe_ratio": bt_result.sharpe_ratio,
        "sortino_ratio": bt_result.sortino_ratio,
        "max_drawdown_pct": bt_result.max_drawdown_pct,
        "max_drawdown_usd": bt_result.max_drawdown_usd,
        "avg_r_multiple": bt_result.avg_r_multiple,
        "expectancy_r": bt_result.expectancy_r,
        "total_friction": bt_result.total_friction,
        "circuit_breaker_trips": bt_result.circuit_breaker_trips,
        "confidence_tau": args.tau,
        "spread_pip": args.spread_pip,
        "slippage_pip": args.slippage_pip,
        "commission_per_lot": args.commission,
    }
    bt_path = REPORTS_DIR / "backtest_report.json"
    with open(bt_path, "w", encoding="utf-8") as f:
        json.dump(bt_summary, f, indent=2, default=str)
    print(f"[SAVE] Backtest Report: {bt_path}")

    # Save Monte Carlo Summary
    if mc_result:
        mc_summary = {
            "n_iterations": mc_result.n_iterations,
            "n_trades": mc_result.n_trades,
            "median_final_equity": mc_result.median_final_equity,
            "p5_final_equity": mc_result.p5_final_equity,
            "p95_final_equity": mc_result.p95_final_equity,
            "mean_max_drawdown": mc_result.mean_max_drawdown,
            "p95_max_drawdown": mc_result.p95_max_drawdown,
            "worst_case_drawdown": mc_result.worst_case_drawdown,
            "prob_circuit_breaker_trip": mc_result.prob_circuit_breaker_trip,
            "prob_permanent_stop": mc_result.prob_permanent_stop,
        }
        mc_path = REPORTS_DIR / "monte_carlo_report.json"
        with open(mc_path, "w", encoding="utf-8") as f:
            json.dump(mc_summary, f, indent=2, default=str)
        print(f"[SAVE] Monte Carlo Report: {mc_path}")

    # Final verdict
    print("\n" + "=" * 80)
    if audit_report.all_gates_passed:
        print("FINAL: MODEL APPROVED FOR LIVE DEPLOYMENT")
    else:
        print("FINAL: MODEL REQUIRES ADDITIONAL RESEARCH ITERATIONS")
    print("=" * 80)

    return 0 if audit_report.all_gates_passed else 1


if __name__ == "__main__":
    sys.exit(main())
