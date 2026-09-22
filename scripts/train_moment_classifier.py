"""
XAU_DEEP_SNIPER - MOMENT-1-large Foundation Model Training Script (TAHAP 4)
=============================================================================
Eksekusi end-to-end berstandar kuantitatif institusional:
  1. Load train & test labeled datasets (TAHAP 3 output, 58,581 window)
  2. Load Class-Balanced Focal Loss alpha weights dari labeling_quality_report.json
  3. Inisialisasi PyTorch DataLoaders (B x 9 x 64 tensors, pin_memory=True)
  4. Inisialisasi arsitektur PretrainedMOMENTClassifier (342M params)
     dengan LoRA rank 16 (alpha 32) pada seluruh 24 layer atensi T5 (W_q, W_v)
  5. Fine-tune model dengan AdamW + Cosine Annealing with Warmup + PyTorch AMP FP16
  6. Evaluasi performa Out-of-Sample (OOS) pada Sealed Test Set (11,681 window)
  7. Simpan model checkpoint (checkpoints/best_moment_pretrained_lora.pt)
     dan laporan komprehensif (reports/model_training_report.json)
"""

import sys
import json
import time
import argparse
import pathlib
import pandas as pd
import numpy as np
import torch

# Setup paths
project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from pipeline import config
from models.dataset import create_dataloaders
from models.moment_model import PretrainedMOMENTClassifier, MOMENTClassifier, MOMENTConfig
from models.loss import ClassBalancedFocalLoss
from models.trainer import MOMENTTrainer, compute_classification_metrics
from labeling.triple_barrier import ACTION_CLASSES


def parse_args():
    parser = argparse.ArgumentParser(description="Institutional Training of MOMENT-1-large on XAU/USD M30")
    parser.add_argument("--epochs", type=int, default=12, help="Number of fine-tuning epochs (default: 12)")
    parser.add_argument("--warmup-epochs", type=int, default=1, help="Number of linear warmup epochs (default: 1)")
    parser.add_argument("--batch-size", type=int, default=32, help="Physical batch size per step (default: 32)")
    parser.add_argument("--grad-accum", type=int, default=2, help="Gradient accumulation steps (effective batch = batch_size * grad_accum)")
    parser.add_argument("--lr", type=float, default=2e-4, help="Peak learning rate for AdamW (default: 2e-4)")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank for W_q and W_v adapters (default: 16)")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA scaling factor alpha (default: 32)")
    parser.add_argument("--device", type=str, default=None, help="Device ('cuda' or 'cpu')")
    parser.add_argument("--standalone", action="store_true", help="Force lightweight standalone model instead of Pretrained MOMENT")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 80)
    print("XAU_DEEP_SNIPER - INSTITUTIONAL FOUNDATION MODEL TRAINING (TAHAP 4)")
    print("=" * 80)

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    if device == "cuda":
        gpu_name = torch.cuda.get_device_name(0)
        vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"  Target Accelerator   : {gpu_name} ({vram_total:.2f} GB VRAM, CUDA {torch.version.cuda})")
    else:
        print("  Target Accelerator   : CPU (Warning: High latency)")

    # 1. Load data
    train_path = config.DATA_PROCESSED_DIR / config.TRAIN_LABELED_PARQUET_FILENAME
    test_path = config.DATA_PROCESSED_DIR / config.TEST_LABELED_PARQUET_FILENAME

    print(f"\n[1/6] Loading labeled datasets:")
    print(f"      Train Parquet : {train_path}")
    print(f"      Test Parquet  : {test_path}")

    if not train_path.exists() or not test_path.exists():
        print("ERROR: Parquet dataset tidak ditemukan! Jalankan run_labeling_pipeline.py terlebih dahulu.")
        sys.exit(1)

    t0 = time.time()
    df_train = pd.read_parquet(train_path)
    df_test = pd.read_parquet(test_path)
    t1 = time.time()
    print(f"      Loaded Train ({len(df_train):,} bars) and Test ({len(df_test):,} bars) in {t1 - t0:.2f}s")

    # 2. Load alpha weights
    report_path = config.REPORTS_DIR / config.LABELING_REPORT_FILENAME
    if report_path.exists():
        with open(report_path, "r", encoding="utf-8") as f:
            label_report = json.load(f)
        alpha_weights = label_report.get("train_set", {}).get("class_distribution", {}).get("alpha_weights", None)
        print(f"\n[2/6] Loaded Class-Balanced Focal Weights from TAHAP 3:")
        print(f"      Alpha weights: {alpha_weights}")
    else:
        alpha_weights = [0.4323, 1.0979, 1.1903, 1.1038, 1.1757]
        print(f"\n[2/6] Using default alpha weights: {alpha_weights}")

    # 3. Create DataLoaders
    eff_batch = args.batch_size * args.grad_accum
    print(f"\n[3/6] Building PyTorch DataLoaders:")
    print(f"      Physical Batch Size  : {args.batch_size}")
    print(f"      Gradient Accum Steps : {args.grad_accum} (Effective Batch Size = {eff_batch})")
    print(f"      Sequence Length (L)  : 64 M30 bars (32 jam)")
    train_loader, test_loader, train_ds, test_ds = create_dataloaders(
        df_train,
        df_test,
        batch_size=args.batch_size,
        sequence_length=64,
    )
    print(f"      Train Windows        : {len(train_ds):,} ({len(train_loader)} batches)")
    print(f"      Sealed Test Windows  : {len(test_ds):,} ({len(test_loader)} batches)")

    # 4. Initialize Model
    if args.standalone:
        print(f"\n[4/6] Initializing Lightweight Standalone Transformer...")
        model_cfg = MOMENTConfig(
            n_channels=9,
            seq_len=64,
            patch_len=8,
            patch_stride=8,
            d_model=256,
            num_layers=4,
            num_heads=8,
            d_ff=1024,
            dropout=0.2,
            num_classes=5,
            use_lora=True,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
        )
        model = MOMENTClassifier(model_cfg)
        chk_name = "best_moment_standalone_lora.pt"
    else:
        print(f"\n[4/6] Initializing Pretrained AutonLab/MOMENT-1-large Foundation Model (342M)...")
        print(f"      Applying LoRA rank {args.lora_r} (alpha {args.lora_alpha}) across all 24 T5 Encoder Layers...")
        model = PretrainedMOMENTClassifier(
            num_classes=5,
            dropout=0.2,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.05,
        )
        chk_name = "best_moment_pretrained_lora.pt"

    summary = model.parameter_summary()
    print(f"      Architecture Name    : {summary.get('model_type', 'Pretrained MOMENT-1-large')}")
    print(f"      Total Parameters     : {summary.get('total_parameters', 0):,}")
    print(f"      Frozen Foundation    : {summary.get('frozen_parameters', 0):,}")
    print(f"      Trainable LoRA Params: {summary.get('trainable_parameters', 0):,} ({summary.get('trainable_percentage', 0)}%)")

    # 5. Trainer & Loss
    print(f"\n[5/6] Setting up Class-Balanced Focal Loss (gamma=2.0) & AMP Trainer...")
    criterion = ClassBalancedFocalLoss(alpha=alpha_weights, gamma=2.0)

    trainer = MOMENTTrainer(
        model=model,
        criterion=criterion,
        learning_rate=args.lr,
        weight_decay=0.01,
        max_grad_norm=1.0,
        accumulation_steps=args.grad_accum,
        use_amp=True,
        device=device,
    )

    chk_dir = config.PROJECT_ROOT / "checkpoints"

    fit_results = trainer.fit(
        train_loader=train_loader,
        val_loader=test_loader,
        epochs=args.epochs,
        warmup_epochs=args.warmup_epochs,
        checkpoint_dir=str(chk_dir),
        checkpoint_name=chk_name,
        verbose=True,
    )

    # 6. Final Evaluation on Sealed Holdout
    print(f"\n[6/6] Final Sealed Holdout Evaluation (Out-of-Sample Audit)...")
    best_checkpoint_path = fit_results["checkpoint_path"]
    checkpoint = torch.load(best_checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])

    test_metrics = trainer.evaluate(test_loader)
    print(f"      Final OOS Accuracy         : {test_metrics['accuracy'] * 100:.2f}%")
    print(f"      Final OOS Macro Precision  : {test_metrics['macro_precision'] * 100:.2f}%")
    print(f"      Final OOS Macro Recall     : {test_metrics['macro_recall'] * 100:.2f}%")
    print(f"      Final OOS Macro F1-Score   : {test_metrics['macro_f1']:.4f}")
    print(f"      Final OOS Non-HOLD Signals : {test_metrics['non_hold_signals']:,}")
    print(f"      Final OOS Signal Precision : {test_metrics['non_hold_precision'] * 100:.2f}% (Gate 2 Target: >= 50-55%)")
    print(f"      Final OOS Directional Acc  : {test_metrics['directional_accuracy'] * 100:.2f}%")
    print(f"      Final OOS Focal Loss       : {test_metrics['loss']:.4f}")

    print(f"\n      Per-Class Breakdown on Sealed Holdout:")
    for c in range(5):
        pc = test_metrics["per_class"][c]
        name = ACTION_CLASSES[c]
        print(f"        Class {c} ({name:7s}): N={pc['total_samples']:5,d} | Prec: {pc['precision']*100:5.1f}% | Rec: {pc['recall']*100:5.1f}% | F1: {pc['f1']:.3f}")

    # Save training report
    report_dict = {
        "timestamp_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "model_architecture": summary,
        "hyperparameters": {
            "epochs": args.epochs,
            "warmup_epochs": args.warmup_epochs,
            "batch_size": args.batch_size,
            "grad_accum": args.grad_accum,
            "effective_batch_size": eff_batch,
            "learning_rate": args.lr,
            "gamma": 2.0,
            "alpha_weights": alpha_weights,
            "device": device,
            "use_amp": True,
            "lora_r": args.lora_r,
            "lora_alpha": args.lora_alpha,
        },
        "training_history": fit_results["history"],
        "sealed_holdout_metrics": test_metrics,
        "checkpoint_file": best_checkpoint_path,
    }

    report_out_path = config.REPORTS_DIR / "model_training_report.json"
    with open(report_out_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, default=str)
    print(f"\n      [OK] Institutional training report saved: {report_out_path}")

    print("\n" + "=" * 80)
    print("TAHAP 4 MOMENT-1-LARGE INSTITUTIONAL TRAINING COMPLETE")
    print("=" * 80)
    print(f"  Best Validation Macro F1 : {fit_results['best_val_f1']:.4f}")
    print(f"  Best Signal Precision    : {test_metrics['non_hold_precision'] * 100:.2f}%")
    print(f"  Directional Accuracy     : {test_metrics['directional_accuracy'] * 100:.2f}%")
    print(f"  Checkpoint File          : {best_checkpoint_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
