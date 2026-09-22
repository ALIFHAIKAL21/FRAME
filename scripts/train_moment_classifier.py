"""
XAU_DEEP_SNIPER - Train MOMENT-1-large Classifier on Real Data (TAHAP 4)
==========================================================================
Eksekusi end-to-end:
  1. Load train & test labeled datasets (TAHAP 3 output)
  2. Load Class-Balanced Focal Loss alpha weights dari labeling_quality_report.json
  3. Inisialisasi PyTorch DataLoaders (B x 9 x 64 tensors)
  4. Inisialisasi arsitektur MOMENTClassifier dengan LoRA (r=8, alpha=16)
  5. Fine-tune model dengan AdamW + Cosine Annealing schedule
  6. Evaluasi performa Out-of-Sample (OOS) pada Sealed Test Set
  7. Simpan model checkpoint (checkpoints/best_moment_lora.pt) dan reports/model_training_report.json
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
from models.moment_model import MOMENTClassifier, MOMENTConfig
from models.loss import ClassBalancedFocalLoss
from models.trainer import MOMENTTrainer, compute_classification_metrics
from labeling.triple_barrier import ACTION_CLASSES


def parse_args():
    parser = argparse.ArgumentParser(description="Train MOMENT-1-large Classifier on XAU/USD M30")
    parser.add_argument("--epochs", type=int, default=5, help="Number of fine-tuning epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size for training")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate for AdamW")
    parser.add_argument("--d-model", type=int, default=256, help="Transformer latent dimension (default 256 for fast convergence, or 1024)")
    parser.add_argument("--num-layers", type=int, default=4, help="Transformer encoder layers")
    parser.add_argument("--num-heads", type=int, default=8, help="Attention heads")
    parser.add_argument("--lora-r", type=int, default=8, help="LoRA rank")
    parser.add_argument("--device", type=str, default=None, help="Device (cpu or cuda)")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 76)
    print("XAU_DEEP_SNIPER - MOMENT-1-LARGE FOUNDATION MODEL TRAINING (TAHAP 4)")
    print("=" * 76)

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
        print(f"\n[2/6] Loaded Class-Balanced Focal Weights from report:")
        print(f"      Alpha weights: {alpha_weights}")
    else:
        alpha_weights = [0.43, 1.10, 1.19, 1.10, 1.18]
        print(f"\n[2/6] Using default alpha weights: {alpha_weights}")

    # 3. Create DataLoaders
    print(f"\n[3/6] Building PyTorch DataLoaders (Batch Size = {args.batch_size}, Window L = 64)...")
    train_loader, test_loader, train_ds, test_ds = create_dataloaders(
        df_train,
        df_test,
        batch_size=args.batch_size,
        sequence_length=64,
    )
    print(f"      Train windows: {len(train_ds):,} ({len(train_loader)} batches)")
    print(f"      Test windows : {len(test_ds):,} ({len(test_loader)} batches)")

    # 4. Initialize Model
    print(f"\n[4/6] Initializing MOMENTClassifier Architecture with LoRA...")
    model_cfg = MOMENTConfig(
        n_channels=9,
        seq_len=64,
        patch_len=8,
        patch_stride=8,
        d_model=args.d_model,
        num_layers=args.num_layers,
        num_heads=args.num_heads,
        d_ff=args.d_model * 4,
        dropout=0.2,
        num_classes=5,
        use_lora=True,
        lora_r=args.lora_r,
        lora_alpha=args.lora_r * 2,
    )

    model = MOMENTClassifier(model_cfg)
    summary = model.parameter_summary()
    print(f"      Total parameters     : {summary['total_parameters']:,}")
    print(f"      Trainable parameters : {summary['trainable_parameters']:,} ({summary['trainable_percentage']}%)")
    print(f"      Frozen parameters    : {summary['frozen_parameters']:,}")
    print(f"      LoRA Adapter Rank    : r = {model_cfg.lora_r}, alpha = {model_cfg.lora_alpha}")

    # 5. Trainer & Loss
    print(f"\n[5/6] Setting up Class-Balanced Focal Loss & Trainer...")
    criterion = ClassBalancedFocalLoss(alpha=alpha_weights, gamma=2.0)
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"      Compute Device       : {device.upper()}")

    trainer = MOMENTTrainer(
        model=model,
        criterion=criterion,
        learning_rate=args.lr,
        weight_decay=0.01,
        max_grad_norm=1.0,
        device=device,
    )

    chk_dir = config.PROJECT_ROOT / "checkpoints"
    chk_name = "best_moment_lora.pt"

    fit_results = trainer.fit(
        train_loader=train_loader,
        val_loader=test_loader,
        epochs=args.epochs,
        checkpoint_dir=str(chk_dir),
        checkpoint_name=chk_name,
        verbose=True,
    )

    # 6. Final Evaluation on Sealed Holdout
    print(f"\n[6/6] Final Out-of-Sample Sealed Holdout Evaluation...")
    best_checkpoint_path = fit_results["checkpoint_path"]
    checkpoint = torch.load(best_checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])

    test_metrics = trainer.evaluate(test_loader)
    print(f"      Final OOS Accuracy       : {test_metrics['accuracy'] * 100:.2f}%")
    print(f"      Final OOS Macro Precision: {test_metrics['macro_precision'] * 100:.2f}%")
    print(f"      Final OOS Macro Recall   : {test_metrics['macro_recall'] * 100:.2f}%")
    print(f"      Final OOS Macro F1-Score : {test_metrics['macro_f1']:.4f}")
    print(f"      Final OOS Focal Loss     : {test_metrics['loss']:.4f}")

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
            "batch_size": args.batch_size,
            "learning_rate": args.lr,
            "gamma": 2.0,
            "alpha_weights": alpha_weights,
            "device": device,
        },
        "training_history": fit_results["history"],
        "sealed_holdout_metrics": test_metrics,
        "checkpoint_file": best_checkpoint_path,
    }

    report_out_path = config.REPORTS_DIR / "model_training_report.json"
    with open(report_out_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, default=str)
    print(f"\n      [OK] Training report saved: {report_out_path}")

    print("\n" + "=" * 76)
    print("TAHAP 4 MOMENT-1-LARGE INTEGRATION COMPLETE")
    print("=" * 76)
    print(f"  Best Validation Macro F1 : {fit_results['best_val_f1']:.4f}")
    print(f"  Checkpoint saved         : {best_checkpoint_path}")
    print("=" * 76)


if __name__ == "__main__":
    main()
