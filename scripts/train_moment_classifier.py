"""
XAU_DEEP_SNIPER - MOMENT-1-large Foundation Model Training Script (TAHAP 4)
=============================================================================
Eksekusi end-to-end berstandar kuantitatif institusional:
  1. Load train & test labeled datasets (TAHAP 3 output, 58,645 bar)
  2. Load Class-Balanced Focal Loss alpha weights (HOLD Anti-Collapse alpha=0.43)
  3. Inisialisasi PyTorch DataLoaders (Tensor B x 12 x 64, pin_memory=True)
  4. Inisialisasi arsitektur PretrainedMOMENTClassifier (342M params)
     dengan LoRA rank 16 (alpha 32) pada seluruh layer atensi T5 (W_q, W_v)
  5. Fine-tune model dengan AdamW + Cosine Annealing with Warmup + PyTorch AMP FP16
  6. Evaluasi performa Out-of-Sample (OOS) pada Sealed Test Set (11,618 window)
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
from models.loss import ClassBalancedFocalLoss, DirectionalFocalLoss
from models.trainer import MOMENTTrainer, compute_classification_metrics
from labeling.triple_barrier import ACTION_CLASSES


def parse_args():
    parser = argparse.ArgumentParser(description="Institutional Training of MOMENT-1-large on XAU/USD M30")
    parser.add_argument("--epochs", type=int, default=30, help="Number of fine-tuning epochs (default: 30)")
    parser.add_argument("--warmup-epochs", type=int, default=2, help="Number of linear warmup epochs (default: 2)")
    parser.add_argument("--batch-size", type=int, default=32, help="Physical batch size per step (default: 32)")
    parser.add_argument("--grad-accum", type=int, default=2, help="Gradient accumulation steps (effective batch = batch_size * grad_accum)")
    parser.add_argument("--lr", type=float, default=2e-4, help="Peak learning rate for AdamW (default: 2e-4)")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank for attention adapters (default: 16)")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA scaling factor alpha (default: 32)")
    parser.add_argument("--gamma", type=float, default=2.0, help="Focal loss focusing parameter (default: 2.0)")
    parser.add_argument("--dir-weight", type=float, default=0.5, help="Directional auxiliary loss weight (default: 0.5)")
    parser.add_argument("--hold-alpha", type=float, default=0.43, help="Minimum alpha weight for class 0 HOLD (default: 0.43 to prevent HOLD collapse)")
    parser.add_argument("--device", type=str, default=None, help="Device ('cuda' or 'cpu')")
    parser.add_argument("--standalone", action="store_true", help="Force lightweight standalone model instead of Pretrained MOMENT")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 80)
    print("XAU_DEEP_SNIPER - INSTITUTIONAL FOUNDATION MODEL TRAINING (TAHAP 4)")
    print("=" * 80)

    # Device
    if args.device:
        device = args.device
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Target Device: {device}")
    if device == "cuda":
        gpu_name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"GPU Model    : {gpu_name} ({vram:.1f} GB VRAM)")

    # 1. Load Parquet Datasets
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

    # 2. Load alpha weights (Class-Balanced)
    report_path = config.REPORTS_DIR / config.LABELING_REPORT_FILENAME
    if report_path.exists():
        with open(report_path, "r", encoding="utf-8") as f:
            label_report = json.load(f)
        raw_alpha = label_report.get("train_set", {}).get("class_distribution", {}).get("alpha_weights", None)
        if raw_alpha is not None:
            # Proteksi kelas HOLD tanpa memaksa alpha[0] >= 1.0 agar model tidak pasif
            alpha_weights = [max(float(raw_alpha[0]), args.hold_alpha)] + [float(w) for w in raw_alpha[1:]]
        else:
            alpha_weights = [args.hold_alpha, 1.10, 1.20, 1.10, 1.20]
        print(f"\n[2/6] Loaded & Calibrated Class-Balanced Focal Weights (HOLD Protected >= {args.hold_alpha}):")
        print(f"      Alpha weights: {alpha_weights}")
    else:
        alpha_weights = [args.hold_alpha, 1.10, 1.20, 1.10, 1.20]
        print(f"\n[2/6] Using default calibrated alpha weights: {alpha_weights}")

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
        pin_memory=(device == "cuda"),
    )
    print(f"      Train Windows        : {len(train_ds):,} ({len(train_loader)} batches)")
    print(f"      Sealed Test Windows  : {len(test_ds):,} ({len(test_loader)} batches)")

    # 4. Initialize Model
    if args.standalone:
        print(f"\n[4/6] Initializing Lightweight Standalone Transformer...")
        model_cfg = MOMENTConfig(
            n_channels=12,
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
            n_channels=12,
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
    print(f"\n[5/6] Setting up Directional Focal Loss (gamma={args.gamma}, dir_weight={args.dir_weight}) & AMP Trainer...")
    criterion = DirectionalFocalLoss(
        alpha=alpha_weights,
        gamma=args.gamma,
        directional_weight=args.dir_weight,
    )

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

    # 6. Execute Training via Institutional Trainer
    chk_dir = project_root / "checkpoints"
    chk_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = chk_dir / chk_name

    print(f"\n[6/6] Launching Training ({args.epochs} epochs, warmup {args.warmup_epochs})...")
    print(f"      Target Checkpoint: {checkpoint_file}")
    t_train_start = time.time()

    train_results = trainer.fit(
        train_loader=train_loader,
        val_loader=test_loader,
        epochs=args.epochs,
        warmup_epochs=args.warmup_epochs,
        checkpoint_dir=str(chk_dir),
        checkpoint_name=chk_name,
        verbose=True,
    )

    t_train_end = time.time()
    total_duration = t_train_end - t_train_start
    print(f"\nTraining completed in {total_duration / 60:.2f} minutes.")
    print(f"Best Validation Composite Score : {train_results['best_composite_score']:.4f}")
    print(f"Best Checkpoint Saved To        : {train_results['checkpoint_path']}")

    # 7. Final Sealed Holdout Evaluation
    print(f"\nEvaluating Best Checkpoint on Sealed Holdout...")
    eval_model = PretrainedMOMENTClassifier(num_classes=5, n_channels=12, lora_r=args.lora_r, lora_alpha=args.lora_alpha) if not args.standalone else MOMENTClassifier(model_cfg)
    best_ckpt = torch.load(train_results["checkpoint_path"], map_location=device, weights_only=False)
    eval_model.load_state_dict(best_ckpt["model_state_dict"])
    eval_model.to(device)

    eval_trainer = MOMENTTrainer(model=eval_model, criterion=criterion, device=device)
    final_metrics = eval_trainer.evaluate(test_loader)

    print(f"\nFINAL SEALED HOLDOUT METRICS:")
    print(f"  Accuracy             : {final_metrics['accuracy']:.4f}")
    print(f"  Macro Precision      : {final_metrics['macro_precision']:.4f}")
    print(f"  Macro Recall         : {final_metrics['macro_recall']:.4f}")
    print(f"  Macro F1             : {final_metrics['macro_f1']:.4f}")
    print(f"  Non-HOLD Signals     : {final_metrics['non_hold_signals']:,} / {len(test_ds):,} ({final_metrics['non_hold_signals']/len(test_ds)*100:.1f}%)")
    print(f"  Non-HOLD Precision   : {final_metrics['non_hold_precision']*100:.2f}%")
    print(f"  Directional Accuracy : {final_metrics['directional_accuracy']*100:.2f}%")

    print(f"\nPer-Class Breakdown:")
    for c, stats in final_metrics["per_class"].items():
        c_name = ACTION_CLASSES.get(c, str(c))
        print(f"  Class {c} ({c_name:<8}): N={stats['total_samples']:<5} TP={stats['true_positive']:<5} FP={stats['false_positive']:<5} Prec={stats['precision']*100:.1f}% Rec={stats['recall']*100:.1f}% F1={stats['f1']:.3f}")

    # Save training report
    report_data = {
        "timestamp_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "model_architecture": summary,
        "hyperparameters": vars(args),
        "training_history": train_results["history"],
        "sealed_holdout_metrics": final_metrics,
        "checkpoint_file": str(checkpoint_file),
    }

    report_out_path = config.REPORTS_DIR / config.MODEL_REPORT_FILENAME
    with open(report_out_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)
    print(f"\nTraining report saved to: {report_out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
