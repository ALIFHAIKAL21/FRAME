"""
XAU_DEEP_SNIPER - MOMENT PyTorch Training and Evaluation Engine (TAHAP 4)
========================================================================
Mendukung:
- FP16 Automatic Mixed Precision (AMP) via torch.amp.autocast dan GradScaler
- Gradient Accumulation untuk stabilitas batch besar pada GPU 6GB VRAM
- Linear Warmup + Cosine Annealing Learning Rate Scheduler
- Perhitungan metrik kuantitatif trading: Macro F1, Non-HOLD Signal Precision,
  Directional Accuracy, dan Breakdown per-kelas
- Checkpointing model terbaik berdasarkan Validation Performance
"""

import time
import math
import pathlib
import numpy as np
import torch
import torch.nn as nn
from typing import Dict, List, Optional, Tuple, Any, Union

from .loss import ClassBalancedFocalLoss


def compute_classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int = 5) -> Dict[str, Any]:
    """
    Menghitung metrik klasifikasi multi-kelas dan metrik kuantitatif trading:
    - Accuracy, Macro Precision, Macro Recall, Macro F1
    - Per-class precision, recall, f1, TP, FP, FN
    - Non-HOLD Trade Signal Precision (Gate 2 requirement)
    - Directional Accuracy (BUY 1R/2R vs SELL 1R/2R correctness)
    """
    eps = 1e-8
    accuracy = float((y_true == y_pred).mean())

    precisions = []
    recalls = []
    f1s = []
    per_class = {}

    for c in range(num_classes):
        tp = int(((y_true == c) & (y_pred == c)).sum())
        fp = int(((y_true != c) & (y_pred == c)).sum())
        fn = int(((y_true == c) & (y_pred != c)).sum())
        total = int((y_true == c).sum())

        p = tp / (tp + fp + eps)
        r = tp / (tp + fn + eps)
        f1 = (2.0 * p * r) / (p + r + eps)

        precisions.append(p)
        recalls.append(r)
        f1s.append(f1)

        per_class[c] = {
            "total_samples": total,
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "precision": round(float(p), 4),
            "recall": round(float(r), 4),
            "f1": round(float(f1), 4),
        }

    macro_precision = float(np.mean(precisions))
    macro_recall = float(np.mean(recalls))
    macro_f1 = float(np.mean(f1s))

    # Trading-specific Institutional Metrics:
    # 1. Non-HOLD Signals (Classes 1, 2, 3, 4)
    non_hold_mask = (y_pred != 0)
    total_signals = int(non_hold_mask.sum())
    signal_tp = int(((y_pred != 0) & (y_true == y_pred)).sum())
    non_hold_precision = (signal_tp / (total_signals + eps)) if total_signals > 0 else 0.0

    # 2. Directional Precision:
    # BUY signals: pred in [1, 2] and true in [1, 2]
    # SELL signals: pred in [3, 4] and true in [3, 4]
    buy_signals = ((y_pred == 1) | (y_pred == 2))
    buy_correct = (buy_signals & ((y_true == 1) | (y_true == 2))).sum()
    sell_signals = ((y_pred == 3) | (y_pred == 4))
    sell_correct = (sell_signals & ((y_true == 3) | (y_true == 4))).sum()
    total_directional = int(buy_signals.sum() + sell_signals.sum())
    directional_correct = int(buy_correct + sell_correct)
    directional_accuracy = (directional_correct / (total_directional + eps)) if total_directional > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
        "non_hold_signals": total_signals,
        "non_hold_precision": round(float(non_hold_precision), 4),
        "directional_accuracy": round(float(directional_accuracy), 4),
        "per_class": per_class,
    }


class MOMENTTrainer:
    """
    Institutional-Grade Training and Evaluation Engine untuk MOMENT Classifier
    dengan CUDA Mixed Precision (AMP FP16) and Cosine Annealing with Warmup.
    """

    def __init__(
        self,
        model: nn.Module,
        criterion: ClassBalancedFocalLoss,
        learning_rate: float = 2e-4,
        weight_decay: float = 0.01,
        max_grad_norm: float = 1.0,
        accumulation_steps: int = 1,
        use_amp: bool = True,
        device: Optional[str] = None,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model.to(self.device)
        self.criterion = criterion.to(self.device)
        self.max_grad_norm = max_grad_norm
        self.accumulation_steps = max(1, accumulation_steps)
        self.use_amp = use_amp and (self.device == "cuda")

        # Filter parameter trainable (LoRA adapters + classification head)
        trainable_params = [p for p in self.model.parameters() if p.requires_grad]
        self.optimizer = torch.optim.AdamW(
            trainable_params,
            lr=learning_rate,
            weight_decay=weight_decay,
            betas=(0.9, 0.98),
            eps=1e-6,
        )

        # PyTorch AMP Scaler
        self.scaler = torch.amp.GradScaler("cuda", enabled=self.use_amp)
        self.scheduler = None

    def train_epoch(self, train_loader: torch.utils.data.DataLoader) -> Dict[str, Any]:
        """Melatih model selama 1 epoch dengan AMP FP16 dan Gradient Accumulation."""
        self.model.train()
        total_loss = 0.0
        all_preds = []
        all_targets = []

        self.optimizer.zero_grad()

        for step, (x_batch, y_batch) in enumerate(train_loader):
            x_batch = x_batch.to(self.device, non_blocking=True)
            y_batch = y_batch.to(self.device, non_blocking=True)

            with torch.amp.autocast(device_type="cuda", dtype=torch.float16, enabled=self.use_amp):
                logits = self.model(x_batch)
                raw_loss = self.criterion(logits, y_batch)
                loss = raw_loss / self.accumulation_steps

            self.scaler.scale(loss).backward()

            # Step optimizer setiap accumulation_steps
            if (step + 1) % self.accumulation_steps == 0 or (step + 1) == len(train_loader):
                if self.max_grad_norm > 0:
                    self.scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(
                        [p for p in self.model.parameters() if p.requires_grad],
                        self.max_grad_norm,
                    )
                self.scaler.step(self.optimizer)
                self.scaler.update()
                self.optimizer.zero_grad()

                if self.scheduler is not None:
                    self.scheduler.step()

            total_loss += raw_loss.item() * len(y_batch)
            preds = torch.argmax(logits, dim=-1)
            all_preds.extend(preds.detach().cpu().numpy())
            all_targets.extend(y_batch.detach().cpu().numpy())

        avg_loss = total_loss / len(train_loader.dataset)
        metrics = compute_classification_metrics(np.array(all_targets), np.array(all_preds))
        metrics["loss"] = round(avg_loss, 4)
        return metrics

    @torch.no_grad()
    def evaluate(self, eval_loader: torch.utils.data.DataLoader) -> Dict[str, Any]:
        """Mengevaluasi model pada dataset validasi/uji dengan AMP FP16."""
        self.model.eval()
        total_loss = 0.0
        all_preds = []
        all_targets = []

        for x_batch, y_batch in eval_loader:
            x_batch = x_batch.to(self.device, non_blocking=True)
            y_batch = y_batch.to(self.device, non_blocking=True)

            with torch.amp.autocast(device_type="cuda", dtype=torch.float16, enabled=self.use_amp):
                logits = self.model(x_batch)
                loss = self.criterion(logits, y_batch)

            total_loss += loss.item() * len(y_batch)
            preds = torch.argmax(logits, dim=-1)
            all_preds.extend(preds.cpu().numpy())
            all_targets.extend(y_batch.cpu().numpy())

        avg_loss = total_loss / len(eval_loader.dataset)
        metrics = compute_classification_metrics(np.array(all_targets), np.array(all_preds))
        metrics["loss"] = round(avg_loss, 4)
        return metrics

    def fit(
        self,
        train_loader: torch.utils.data.DataLoader,
        val_loader: torch.utils.data.DataLoader,
        epochs: int = 12,
        warmup_epochs: int = 1,
        checkpoint_dir: str = "checkpoints",
        checkpoint_name: str = "best_moment_pretrained_lora.pt",
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """
        Menjalankan full training loop dengan Warmup + Cosine Annealing scheduler.
        """
        chk_path = pathlib.Path(checkpoint_dir)
        chk_path.mkdir(parents=True, exist_ok=True)
        best_checkpoint_file = chk_path / checkpoint_name

        # Hitung total optim step untuk Cosine Annealing with Warmup
        steps_per_epoch = math.ceil(len(train_loader) / self.accumulation_steps)
        total_training_steps = steps_per_epoch * epochs
        warmup_steps = steps_per_epoch * max(1, warmup_epochs)

        try:
            from transformers import get_cosine_schedule_with_warmup
            self.scheduler = get_cosine_schedule_with_warmup(
                self.optimizer,
                num_warmup_steps=warmup_steps,
                num_training_steps=total_training_steps,
            )
        except ImportError:
            self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                self.optimizer,
                T_max=epochs,
                eta_min=1e-6,
            )

        history = {
            "epoch": [],
            "train_loss": [],
            "train_acc": [],
            "val_loss": [],
            "val_acc": [],
            "val_f1": [],
            "val_non_hold_prec": [],
            "val_dir_acc": [],
        }

        best_val_f1 = -1.0

        if verbose:
            print(f"[TRAINER] Institutional MOMENT Fine-Tuning ({epochs} epochs on {self.device}):")
            print(f"  AMP FP16 Enabled     : {self.use_amp}")
            print(f"  Gradient Accumulation: {self.accumulation_steps} (Effective batch x{self.accumulation_steps})")
            summary = self.model.parameter_summary() if hasattr(self.model, "parameter_summary") else {}
            if summary:
                print(f"  Model Type           : {summary.get('model_type', 'MOMENT')}")
                print(f"  Trainable LoRA params: {summary.get('trainable_parameters', 0):,} / {summary.get('total_parameters', 0):,} ({summary.get('trainable_percentage', 0)}%)")

        for epoch in range(1, epochs + 1):
            t0 = time.time()
            train_metrics = self.train_epoch(train_loader)
            val_metrics = self.evaluate(val_loader)
            t1 = time.time()

            history["epoch"].append(epoch)
            history["train_loss"].append(train_metrics["loss"])
            history["train_acc"].append(train_metrics["accuracy"])
            history["val_loss"].append(val_metrics["loss"])
            history["val_acc"].append(val_metrics["accuracy"])
            history["val_f1"].append(val_metrics["macro_f1"])
            history["val_non_hold_prec"].append(val_metrics["non_hold_precision"])
            history["val_dir_acc"].append(val_metrics["directional_accuracy"])

            current_lr = self.optimizer.param_groups[0]["lr"]
            if verbose:
                vram_str = f"{torch.cuda.memory_allocated() / (1024*1024):.0f}MB" if self.device == "cuda" else "N/A"
                print(
                    f"  Epoch {epoch:2d}/{epochs:2d} ({t1 - t0:.1f}s, VRAM: {vram_str}) | "
                    f"Train Loss: {train_metrics['loss']:.4f} Acc: {train_metrics['accuracy']:.3f} | "
                    f"Val Loss: {val_metrics['loss']:.4f} Acc: {val_metrics['accuracy']:.3f} "
                    f"F1: {val_metrics['macro_f1']:.3f} | "
                    f"Signal Prec: {val_metrics['non_hold_precision']*100:.1f}% DirAcc: {val_metrics['directional_accuracy']*100:.1f}% | LR: {current_lr:.2e}"
                )

            # Simpan model terbaik berdasarkan validation Macro F1
            if val_metrics["macro_f1"] > best_val_f1:
                best_val_f1 = val_metrics["macro_f1"]
                torch.save(
                    {
                        "epoch": epoch,
                        "model_state_dict": self.model.state_dict(),
                        "optimizer_state_dict": self.optimizer.state_dict(),
                        "val_metrics": val_metrics,
                        "config": getattr(self.model, "config", None),
                    },
                    best_checkpoint_file,
                )
                if verbose:
                    print(f"    >>> Best Checkpoint Saved! (Val Macro F1 = {best_val_f1:.4f}, Signal Prec = {val_metrics['non_hold_precision']*100:.1f}%)")

        return {
            "history": history,
            "best_val_f1": best_val_f1,
            "checkpoint_path": str(best_checkpoint_file),
        }
