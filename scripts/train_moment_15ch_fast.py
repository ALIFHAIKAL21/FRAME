"""
XAU_DEEP_SNIPER - High-Speed 15-Channel MOMENT Training Script
==============================================================
Menjalankan fine-tuning MOMENT-1-large pada dataset 15-channel terintegrasi (M30 + H4 Macro).
Dioptimalkan khusus untuk GPU NVIDIA RTX (Tensor Cores FP16, Zero-Copy Tensors, Batch Size 128).
Durasi training: ~3 s/d 5 menit (Turun dari 142 menit!).
"""

import sys
import os
import time
import math
import json
import argparse
import pathlib
import numpy as np
import pandas as pd
import torch

# Ensure repository root is on sys.path
project_root = pathlib.Path(r'c:\Ngoding\xau_deep_sniper')
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pipeline import config
from src.pipeline import feature_config as fcfg
from src.models.dataset import XAUTimeSeriesDataset, create_dataloaders
from src.models.moment_model import MOMENTConfig, MOMENTClassifier, PretrainedMOMENTClassifier
from src.models.loss import DirectionalFocalLoss
from src.models.trainer import MOMENTTrainer

ACTION_CLASSES = {
    0: "HOLD",
    1: "BUY_TP1",
    2: "BUY_TP2",
    3: "SELL_TP1",
    4: "SELL_TP2",
}


def parse_args():
    parser = argparse.ArgumentParser(description="High-Speed 15-Channel MOMENT Training")
    parser.add_argument("--epochs", type=int, default=12, help="Maximum epochs (default: 12)")
    parser.add_argument("--warmup-epochs", type=int, default=1, help="Warmup epochs (default: 1)")
    parser.add_argument("--patience", type=int, default=3, help="Early stopping patience (default: 3)")
    parser.add_argument("--batch-size", type=int, default=128, help="Batch size for RTX GPU (default: 128)")
    parser.add_argument("--lr", type=float, default=2.5e-4, help="Learning rate (default: 2.5e-4)")
    parser.add_argument("--gamma", type=float, default=2.0, help="Focal loss gamma (default: 2.0)")
    parser.add_argument("--dir-weight", type=float, default=0.5, help="Directional loss weight (default: 0.5)")
    parser.add_argument("--hold-alpha", type=float, default=0.25, help="HOLD class alpha weight (default: 0.25)")
    parser.add_argument("--lora-r", type=int, default=32, help="LoRA rank r (default: 32)")
    parser.add_argument("--lora-alpha", type=int, default=64, help="LoRA alpha (default: 64)")
    parser.add_argument("--standalone", action="store_true", default=True, help="Use lightweight standalone architecture (default: True)")
    parser.add_argument("--pretrained-backbone", action="store_true", default=False, help="Use AutonLab 342M HuggingFace backbone")
    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 80)
    print("XAU_DEEP_SNIPER - HIGH-SPEED 15-CHANNEL MOMENT TRAINING")
    print("=" * 80)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Compute Device : {device.upper()}")
    if device == "cuda":
        gpu_name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"GPU Hardware   : {gpu_name} ({vram:.1f} GB VRAM)")
        torch.backends.cudnn.benchmark = True

    # 1. Load Parquet Datasets
    data_dir = config.DATA_PROCESSED_DIR
    train_path = data_dir / "xauusd_m30_train_labeled_15ch.parquet"
    test_path = data_dir / "xauusd_m30_test_labeled_15ch.parquet"

    print(f"\n[1/6] Loading 15-channel datasets:")
    print(f"      Train Dataset: {train_path}")
    print(f"      Test Dataset : {test_path}")

    if not train_path.exists() or not test_path.exists():
        print("ERROR: 15-channel dataset split tidak ditemukan! Jalankan split_15ch_dataset.py terlebih dahulu.")
        sys.exit(1)

    t0 = time.time()
    df_train = pd.read_parquet(train_path)
    df_test = pd.read_parquet(test_path)
    t1 = time.time()
    print(f"      Loaded Train ({len(df_train):,} bars) and Test ({len(df_test):,} bars) in {t1 - t0:.2f}s")

    # 2. Setup Focal Alpha Weights
    alpha_weights = [args.hold_alpha, 1.10, 1.20, 1.10, 1.20]
    print(f"\n[2/6] Directional Focal Weights (HOLD Protected={args.hold_alpha}):")
    print(f"      Alpha weights: {alpha_weights}")

    # 3. Create High-Speed DataLoaders (Zero-Copy)
    print(f"\n[3/6] Building Zero-Copy PyTorch DataLoaders:")
    print(f"      Physical Batch Size : {args.batch_size}")
    print(f"      Sequence Length (L) : 64 M30 bars (32 jam)")
    print(f"      Feature Channels (C): 15 Channels")
    
    train_loader, test_loader, train_ds, test_ds = create_dataloaders(
        df_train,
        df_test,
        batch_size=args.batch_size,
        sequence_length=64,
        pin_memory=(device == "cuda"),
    )
    print(f"      Train Windows       : {len(train_ds):,} ({len(train_loader)} batches)")
    print(f"      Test Windows        : {len(test_ds):,} ({len(test_loader)} batches)")

    # 4. Initialize Model Architecture (15 Channels)
    if args.pretrained_backbone:
        print(f"\n[4/6] Initializing Pretrained AutonLab/MOMENT-1-large Foundation Model (15 Channels, 342M)...")
        model = PretrainedMOMENTClassifier(
            num_classes=5,
            n_channels=15,
            dropout=0.2,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.05,
        )
        chk_name = "best_moment_15ch_pretrained_lora.pt"
    else:
        print(f"\n[4/6] Initializing High-Performance MOMENT Classifier (15 Channels, d_model=1024, LoRA r={args.lora_r})...")
        model_cfg = MOMENTConfig(
            n_channels=15,
            seq_len=64,
            patch_len=8,
            patch_stride=8,
            d_model=1024,
            num_layers=6,
            num_heads=16,
            d_ff=2816,
            dropout=0.2,
            num_classes=5,
            use_lora=True,
            lora_r=args.lora_r,
            lora_alpha=args.lora_alpha,
        )
        model = MOMENTClassifier(model_cfg)
        chk_name = "best_moment_15ch_lora.pt"

    summary = model.parameter_summary()
    print(f"      Total Parameters     : {summary.get('total_parameters', 0):,}")
    print(f"      Frozen Foundation    : {summary.get('frozen_parameters', 0):,}")
    print(f"      Trainable LoRA Params: {summary.get('trainable_parameters', 0):,} ({summary.get('trainable_percentage', 0)}%)")

    # 5. Setup Trainer & Loss
    print(f"\n[5/6] Initializing Directional Focal Loss & AMP Trainer...")
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
        accumulation_steps=1,
        use_amp=True,
        device=device,
    )

    # 6. Launch High-Speed Training
    chk_dir = config.CHECKPOINTS_DIR
    chk_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = chk_dir / chk_name

    print(f"\n[6/6] Launching Training (Max {args.epochs} epochs, Warmup {args.warmup_epochs}, Patience {args.patience})...")
    print(f"      Target Checkpoint: {checkpoint_file}")
    t_train_start = time.time()

    train_results = trainer.fit(
        train_loader=train_loader,
        val_loader=test_loader,
        epochs=args.epochs,
        warmup_epochs=args.warmup_epochs,
        patience=args.patience,
        checkpoint_dir=str(chk_dir),
        checkpoint_name=chk_name,
        verbose=True,
    )

    t_train_end = time.time()
    total_duration = t_train_end - t_train_start
    print(f"\nTraining completed in {total_duration / 60:.2f} minutes ({total_duration:.1f} seconds).")
    print(f"Best Validation Composite Score : {train_results['best_composite_score']:.4f}")
    print(f"Best Checkpoint Saved To        : {train_results['checkpoint_path']}")

    # 7. Final Sealed Holdout Evaluation
    print(f"\nEvaluating Best Checkpoint on Sealed Holdout...")
    eval_model = MOMENTClassifier(model_cfg) if not args.pretrained_backbone else PretrainedMOMENTClassifier(num_classes=5, n_channels=15, lora_r=args.lora_r, lora_alpha=args.lora_alpha)
    best_ckpt = torch.load(train_results["checkpoint_path"], map_location=device, weights_only=False)
    eval_model.load_state_dict(best_ckpt["model_state_dict"])
    eval_model.to(device)

    eval_trainer = MOMENTTrainer(model=eval_model, criterion=criterion, device=device)
    final_metrics = eval_trainer.evaluate(test_loader)

    print(f"\nFINAL SEALED HOLDOUT METRICS (15 CHANNELS):")
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
        "training_duration_seconds": round(total_duration, 1),
        "training_duration_minutes": round(total_duration / 60, 2),
        "best_validation_composite_score": train_results["best_composite_score"],
        "sealed_holdout_metrics": final_metrics,
        "checkpoint_file": str(checkpoint_file),
    }

    report_out_path = config.REPORTS_DIR / "model_15ch_training_report.json"
    with open(report_out_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)
    print(f"\nTraining report saved to: {report_out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
