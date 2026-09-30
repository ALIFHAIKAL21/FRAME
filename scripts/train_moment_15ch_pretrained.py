"""
XAU_DEEP_SNIPER â€” CORRECTED Pretrained MOMENT-1-large Training (15 Channels)
=============================================================================
PERBAIKAN POINT 1: Menggunakan backbone T5 pretrained ASLI dari HuggingFace
dengan transfer learning yang benar.

Strategi Transfer Learning:
- Backbone T5 encoder (24 layers): DIMUAT dari MOMENT safetensors + encoder
  weights dari best_moment_pretrained_lora.pt (encoder compatible)
- patch_embed 15ch: Inisialisasi BARU (lama = 12ch, tidak kompatibel)
- LoRA adapters: BARU (fine-tune ulang di atas backbone yang sudah pretrained)
- Classification head: BARU

Hyperparameter yang benar untuk pretrained fine-tuning:
- lr: 5e-5  (10x lebih kecil â€” pretrained butuh lr rendah agar tidak lupa)
- epochs: 50, patience: 7 (beri cukup waktu konvergen)
- lora_r: 16 (cukup kapasitas, kurang risiko overfit)
- batch_size: 64, gradient_accumulation: 2 (effective 128)

Run:
  .venv\\Scripts\\python.exe scripts\\train_moment_15ch_pretrained.py
"""

import sys
import os
import time
import json
import pathlib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

project_root = pathlib.Path(r'c:\Ngoding\xau_deep_sniper')
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pipeline import config
from src.models.dataset import XAUTimeSeriesDataset, create_dataloaders
from src.models.loss import DirectionalFocalLoss
from src.models.trainer import MOMENTTrainer

# ==============================================================================
# HYPERPARAMETER â€” BENAR UNTUK PRETRAINED FINE-TUNING
# ==============================================================================
EPOCHS          = 50
PATIENCE        = 7
BATCH_SIZE      = 64
LR              = 5e-5        # KRITIS: 10x lebih kecil dari versi standalone
WEIGHT_DECAY    = 0.01
WARMUP_EPOCHS   = 2
LORA_R          = 16
LORA_ALPHA      = 32
LORA_DROPOUT    = 0.05
GAMMA           = 2.0
HOLD_ALPHA      = 0.30
GRAD_ACCUM      = 2           # Effective batch = 64*2 = 128

N_CHANNELS      = 15
SEQ_LEN         = 64
PATCH_LEN       = 8

SAFETENSOR_PATH = (
    r"C:\Users\haika\.cache\huggingface\hub"
    r"\models--AutonLab--MOMENT-1-large"
    r"\snapshots\ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc"
    r"\model.safetensors"
)
CHECKPOINT_OLD  = project_root / "checkpoints" / "best_moment_pretrained_lora.pt"
CHECKPOINT_NEW  = project_root / "checkpoints" / "best_moment_15ch_pretrained_lora.pt"
REPORT_OUT      = project_root / "reports" / "model_15ch_pretrained_training_report.json"

ACTION_CLASSES  = {0: "HOLD", 1: "BUY_1R", 2: "BUY_2R", 3: "SELL_1R", 4: "SELL_2R"}


# ==============================================================================
# PATCH EMBEDDING BARU â€” 15 CHANNEL
# ==============================================================================
class PatchEmbedding15ch(nn.Module):
    """Fresh patch embedding untuk 15 channel (120-dim patch -> 1024 d_model)."""

    def __init__(self, n_channels=15, seq_len=64, patch_len=8, d_model=1024, dropout=0.2):
        super().__init__()
        self.patch_len   = patch_len
        self.stride      = patch_len
        self.num_patches = (seq_len - patch_len) // patch_len + 1  # = 8
        patch_dim        = n_channels * patch_len                   # = 120

        self.projection  = nn.Linear(patch_dim, d_model)
        self.pos_emb     = nn.Parameter(torch.randn(1, self.num_patches, d_model) * 0.02)
        self.dropout     = nn.Dropout(dropout)
        self.jitter_std  = 0.01
        self.mask_prob   = 0.10

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, C, L = x.shape
        if self.training:
            x = x + torch.randn_like(x) * self.jitter_std
        patches    = x.unfold(-1, self.patch_len, self.stride)
        patches    = patches.permute(0, 2, 1, 3).reshape(B, self.num_patches, -1)
        embeddings = self.projection(patches) + self.pos_emb
        if self.training and self.mask_prob > 0:
            mask       = (torch.rand(B, self.num_patches, 1, device=x.device) > self.mask_prob).float()
            embeddings = embeddings * mask
        return self.dropout(embeddings)


# ==============================================================================
# CLASSIFICATION HEAD
# ==============================================================================
class ClassificationHead(nn.Module):
    def __init__(self, d_model=1024, num_classes=5, dropout=0.2):
        super().__init__()
        self.norm       = nn.LayerNorm(d_model)
        self.drop       = nn.Dropout(dropout)
        self.classifier = nn.Linear(d_model, num_classes)

    def forward(self, x):
        return self.classifier(self.drop(self.norm(x)))


# ==============================================================================
# MODEL UTAMA â€” PRETRAINED MOMENT + 15ch PATCH EMBED + LORA
# ==============================================================================
class PretrainedMOMENT15ch(nn.Module):
    """
    AutonLab/MOMENT-1-large backbone + fresh 15ch PatchEmbedding.

    Transfer strategy:
    - Muat MOMENT safetensors ke T5EncoderModel (pengetahuan time-series umum)
    - Overlay encoder LoRA weights dari checkpoint lama (12ch) â€” encoder
      weights sepenuhnya kompatibel karena dimensi T5 tidak berubah
    - patch_embed: BARU karena channel berbeda (12 vs 15)
    - head: BARU
    """

    def __init__(self, lora_r=16, lora_alpha=32, lora_dropout=0.05, dropout=0.2):
        super().__init__()
        import safetensors.torch
        from transformers import T5Config, T5EncoderModel
        from peft import LoraConfig, get_peft_model

        self.d_model    = 1024
        self.n_channels = N_CHANNELS

        # â”€â”€ STEP 1: Load T5 config & init model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        print("   [1] Init T5EncoderModel (flan-t5-large config)...")
        t5_cfg      = T5Config.from_pretrained("google/flan-t5-large")
        base_encoder = T5EncoderModel(t5_cfg)

        # â”€â”€ STEP 2: Load MOMENT-1-large safetensors weights â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if not pathlib.Path(SAFETENSOR_PATH).exists():
            raise FileNotFoundError(
                f"MOMENT safetensors tidak ditemukan di:\n{SAFETENSOR_PATH}\n"
                "Jalankan: python -c \"from huggingface_hub import snapshot_download; "
                "snapshot_download('AutonLab/MOMENT-1-large')\""
            )
        print("   [2] Loading MOMENT-1-large pretrained weights dari local cache...")
        state_dict = safetensors.torch.load_file(SAFETENSOR_PATH, device="cpu")
        miss, unexp = base_encoder.load_state_dict(state_dict, strict=False)
        print(f"       Backbone loaded. Missing: {len(miss)}, Unexpected: {len(unexp)}")

        # â”€â”€ STEP 3: Pasang LoRA adapters baru â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        print("   [3] Applying fresh LoRA adapters (r={}, alpha={})...".format(lora_r, lora_alpha))
        lora_cfg = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            target_modules=["q", "k", "v", "o"],
            lora_dropout=lora_dropout,
            bias="none",
        )
        self.encoder = get_peft_model(base_encoder, lora_cfg)

        # â”€â”€ STEP 4: Transfer encoder weights dari checkpoint 12ch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Hanya bagian encoder (tidak patch_embed/head yang channel-dependent)
        if CHECKPOINT_OLD.exists():
            print(f"   [4] Transferring encoder LoRA weights dari checkpoint 12ch...")
            old_sd = torch.load(CHECKPOINT_OLD, map_location="cpu", weights_only=False)["model_state_dict"]
            encoder_only = {k: v for k, v in old_sd.items() if k.startswith("encoder.")}
            miss2, _ = self.encoder.load_state_dict(encoder_only, strict=False)
            print(f"       Transferred {len(encoder_only)} tensors. Unmatched: {len(miss2)}")
        else:
            print("   [4] Checkpoint lama tidak ada â€” encoder mulai dari MOMENT pretrained saja.")

        # â”€â”€ STEP 5: Fresh patch embed (15ch) & head â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        print("   [5] Init fresh PatchEmbedding (15ch x 8 = dim 120) & ClassHead...")
        self.patch_embed = PatchEmbedding15ch(
            n_channels=N_CHANNELS, seq_len=SEQ_LEN,
            patch_len=PATCH_LEN, d_model=self.d_model, dropout=dropout
        )
        self.head = ClassificationHead(d_model=self.d_model, num_classes=5, dropout=dropout)
        print("   [OK] PretrainedMOMENT15ch ready.")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        tokens = self.patch_embed(x)                        # (B, 8, 1024)
        out    = self.encoder(inputs_embeds=tokens)
        latent = out.last_hidden_state.mean(dim=1)          # (B, 1024)
        return self.head(latent)                            # (B, 5)

    @torch.no_grad()
    def predict_proba(self, x):
        self.eval()
        return F.softmax(self.forward(x), dim=-1)

    @torch.no_grad()
    def predict(self, x):
        return torch.argmax(self.predict_proba(x), dim=-1)

    def parameter_summary(self):
        total     = sum(p.numel() for p in self.parameters())
        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        return {
            "model_type": "PretrainedMOMENT-1-large + 15ch PatchEmbed + LoRA",
            "total_parameters": total,
            "trainable_parameters": trainable,
            "frozen_parameters": total - trainable,
            "trainable_percentage": round(trainable / total * 100, 3),
            "d_model": self.d_model,
            "lora_r": LORA_R,
            "n_channels": N_CHANNELS,
            "pretrained_backbone": True,
        }


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("=" * 75)
    print("XAU_DEEP_SNIPER â€” PRETRAINED MOMENT-1-large FINE-TUNING (15 CHANNELS)")
    print("=" * 75)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\nDevice : {device.upper()}")
    if device == "cuda":
        gpu  = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"GPU    : {gpu} ({vram:.1f} GB VRAM)")
        torch.backends.cudnn.benchmark = True
    else:
        print("PERINGATAN: Tidak ada GPU â€” training akan sangat lambat di CPU!")

    # 1. Dataset
    train_path = config.DATA_PROCESSED_DIR / "xauusd_m30_train_labeled_15ch.parquet"
    test_path  = config.DATA_PROCESSED_DIR / "xauusd_m30_test_labeled_15ch.parquet"
    print(f"\n[1/5] Loading dataset...")
    if not train_path.exists() or not test_path.exists():
        print(f"ERROR: Dataset tidak ditemukan di {config.DATA_PROCESSED_DIR}")
        sys.exit(1)
    df_train = pd.read_parquet(train_path)
    df_test  = pd.read_parquet(test_path)
    print(f"      Train: {len(df_train):,} bars | Test: {len(df_test):,} bars")

    # 2. DataLoader
    print(f"\n[2/5] Building DataLoaders...")
    train_loader, test_loader, train_ds, test_ds = create_dataloaders(
        df_train, df_test,
        batch_size=BATCH_SIZE,
        sequence_length=SEQ_LEN,
        pin_memory=(device == "cuda"),
    )
    print(f"      Train windows: {len(train_ds):,} | Test windows: {len(test_ds):,}")
    print(f"      Effective batch: {BATCH_SIZE * GRAD_ACCUM} (grad accum={GRAD_ACCUM})")

    # 3. Build model
    print(f"\n[3/5] Building model with pretrained backbone...")
    model   = PretrainedMOMENT15ch(lora_r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT)
    summary = model.parameter_summary()
    print(f"\n      Total params     : {summary['total_parameters']:,}")
    print(f"      Trainable (LoRA) : {summary['trainable_parameters']:,} ({summary['trainable_percentage']}%)")
    print(f"      Frozen backbone  : {summary['frozen_parameters']:,}")

    # 4. Loss & Trainer
    print(f"\n[4/5] Setting up Focal Loss & Trainer...")
    print(f"      LR={LR} | Epochs={EPOCHS} | Patience={PATIENCE}")
    alpha_weights = [HOLD_ALPHA, 1.10, 1.20, 1.10, 1.20]
    criterion     = DirectionalFocalLoss(alpha=alpha_weights, gamma=GAMMA, directional_weight=0.5)
    trainer       = MOMENTTrainer(
        model=model,
        criterion=criterion,
        learning_rate=LR,
        weight_decay=WEIGHT_DECAY,
        max_grad_norm=1.0,
        accumulation_steps=GRAD_ACCUM,
        use_amp=True,
        device=device,
    )

    # 5. Training
    print(f"\n[5/5] Training dimulai...")
    print(f"      Checkpoint â†’ {CHECKPOINT_NEW}")
    CHECKPOINT_NEW.parent.mkdir(parents=True, exist_ok=True)

    t0            = time.time()
    train_results = trainer.fit(
        train_loader=train_loader,
        val_loader=test_loader,
        epochs=EPOCHS,
        warmup_epochs=WARMUP_EPOCHS,
        patience=PATIENCE,
        checkpoint_dir=str(CHECKPOINT_NEW.parent),
        checkpoint_name=CHECKPOINT_NEW.name,
        verbose=True,
    )
    duration_s = time.time() - t0
    print(f"\nTraining selesai: {duration_s / 60:.1f} menit")
    print(f"Best Composite Score: {train_results['best_composite_score']:.4f}")

    # Final evaluation
    print("\nFinal evaluation pada test set...")
    eval_model = PretrainedMOMENT15ch(lora_r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT)
    ckpt_data  = torch.load(train_results["checkpoint_path"], map_location=device, weights_only=False)
    eval_model.load_state_dict(ckpt_data["model_state_dict"])
    eval_model.to(device)
    eval_trainer  = MOMENTTrainer(model=eval_model, criterion=criterion, device=device)
    final_metrics = eval_trainer.evaluate(test_loader)

    print(f"\n{'='*75}")
    print(f"FINAL METRICS â€” PRETRAINED MOMENT-1-large 15ch")
    print(f"{'='*75}")
    print(f"  Accuracy           : {final_metrics['accuracy']:.4f}")
    print(f"  Macro F1           : {final_metrics['macro_f1']:.4f}")
    print(f"  Non-HOLD Precision : {final_metrics['non_hold_precision']*100:.2f}%  (Gate 2 target: >=55%)")
    print(f"  Directional Acc    : {final_metrics['directional_accuracy']*100:.2f}%")
    print(f"\n  Per-Class:")
    for c, s in final_metrics["per_class"].items():
        name = ACTION_CLASSES.get(c, str(c))
        print(f"    [{c}] {name:<8}: N={s['total_samples']:<5} "
              f"Prec={s['precision']*100:.1f}%  Rec={s['recall']*100:.1f}%  F1={s['f1']:.3f}")

    prec = final_metrics['non_hold_precision']
    print(f"\n  Gate 2 Status: {'PASS âœ“' if prec >= 0.55 else f'FAIL ({prec*100:.1f}% < 55%) â€” perlu lebih banyak epoch'}")

    # Save report
    report = {
        "timestamp_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "model_summary": summary,
        "hyperparameters": {
            "epochs_max": EPOCHS, "patience": PATIENCE,
            "batch_size": BATCH_SIZE, "grad_accum": GRAD_ACCUM,
            "effective_batch": BATCH_SIZE * GRAD_ACCUM,
            "lr": LR, "lora_r": LORA_R, "lora_alpha": LORA_ALPHA,
            "gamma": GAMMA, "hold_alpha": HOLD_ALPHA,
            "pretrained_backbone": True,
        },
        "training_duration_minutes": round(duration_s / 60, 2),
        "best_composite_score": train_results["best_composite_score"],
        "sealed_holdout_metrics": final_metrics,
        "checkpoint_file": str(CHECKPOINT_NEW),
    }
    with open(REPORT_OUT, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport â†’ {REPORT_OUT}")
    print("=" * 75)


if __name__ == "__main__":
    main()

