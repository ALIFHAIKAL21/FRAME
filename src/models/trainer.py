"""
XAU_DEEP_SNIPER - MOMENT Model Training & Evaluation Engine (TAHAP 4D)
========================================================================
Sesuai spesifikasi BAB 6:
- 6.2: Class-Balanced Focal Loss
- 6.3: Optimizer AdamW dengan Cosine Annealing learning rate schedule
- Evaluasi metrik institusional: Macro Precision, Recall, F1, Loss, dan Per-Class Accuracy

PRINSIP DESAIN:
- Checkpoint manager otomatis menyimpan bobot terbaik ke checkpoints/best_moment_lora.pt.
- Gradient clipping (max_norm = 1.0) untuk kestabilan numerik backprop.
"""

import time
import pathlib
import json
import numpy as np
import torch
import torch.nn as nn
from typing import Dict, List, Optional, Tuple, Any

from .moment_model import MOMENTClassifier
from .loss import ClassBalancedFocalLoss


def compute_classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int = 5) -> Dict[str, Any]:
    """
    Menghitung metrik klasifikasi multi-kelas:
    Accuracy, Macro Precision, Macro Recall, Macro F1, dan statistik per-kelas.
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

    return {
        "accuracy": round(accuracy, 4),
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
    }


class MOMENTTrainer:
    """
    Training and Evaluation Engine untuk MOMENT Classifier.
    """

    def __init__(
        self,
        model: MOMENTClassifier,
        criterion: ClassBalancedFocalLoss,
        learning_rate: float = 1e-4,
        weight_decay: float = 0.01,
        max_grad_norm: float = 1.0,
        device: Optional[str] = None,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model.to(self.device)
        self.criterion = criterion.to(self.device)
        self.max_grad_norm = max_grad_norm

        # Filter parameter trainable (LoRA + classification head)
        trainable_params = [p for p in self.model.parameters() if p.requires_grad]
        self.optimizer = torch.optim.AdamW(
            trainable_params,
            lr=learning_rate,
            weight_decay=weight_decay,
        )

    def train_epoch(self, train_loader: torch.utils.data.DataLoader) -> Dict[str, float]:
        """Melatih model selama 1 epoch."""
        self.model.train()
        total_loss = 0.0
        all_preds = []
        all_targets = []

        for x_batch, y_batch in train_loader:
            x_batch = x_batch.to(self.device)
            y_batch = y_batch.to(self.device)

            self.optimizer.zero_grad()
            logits = self.model(x_batch)
            loss = self.criterion(logits, y_batch)

            loss.backward()
            if self.max_grad_norm > 0:
                torch.nn.utils.clip_grad_norm_(
                    [p for p in self.model.parameters() if p.requires_grad],
                    self.max_grad_norm,
                )
            self.optimizer.step()

            total_loss += loss.item() * len(y_batch)
            preds = torch.argmax(logits, dim=-1)
            all_preds.extend(preds.cpu().numpy())
            all_targets.extend(y_batch.cpu().numpy())

        avg_loss = total_loss / len(train_loader.dataset)
        metrics = compute_classification_metrics(np.array(all_targets), np.array(all_preds))
        metrics["loss"] = round(avg_loss, 4)
        return metrics

    @torch.no_grad()
    def evaluate(self, eval_loader: torch.utils.data.DataLoader) -> Dict[str, Any]:
        """Mengevaluasi model pada dataset validasi/uji."""
        self.model.eval()
        total_loss = 0.0
        all_preds = []
        all_targets = []

        for x_batch, y_batch in eval_loader:
            x_batch = x_batch.to(self.device)
            y_batch = y_batch.to(self.device)

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
        epochs: int = 5,
        checkpoint_dir: str = "checkpoints",
        checkpoint_name: str = "best_moment_lora.pt",
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """
        Menjalankan full training loop dengan Cosine Annealing scheduler dan checkpointing.
        """
        chk_path = pathlib.Path(checkpoint_dir)
        chk_path.mkdir(parents=True, exist_ok=True)
        best_checkpoint_file = chk_path / checkpoint_name

        # Cosine Annealing LR scheduler
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
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
        }

        best_val_f1 = -1.0

        if verbose:
            print(f"[TRAINER] Starting MOMENT Fine-Tuning ({epochs} epochs on {self.device}):")
            summary = self.model.parameter_summary()
            print(f"  Trainable params : {summary['trainable_parameters']:,} / {summary['total_parameters']:,} ({summary['trainable_percentage']}%)")

        for epoch in range(1, epochs + 1):
            t0 = time.time()
            train_metrics = self.train_epoch(train_loader)
            val_metrics = self.evaluate(val_loader)
            scheduler.step()
            t1 = time.time()

            history["epoch"].append(epoch)
            history["train_loss"].append(train_metrics["loss"])
            history["train_acc"].append(train_metrics["accuracy"])
            history["val_loss"].append(val_metrics["loss"])
            history["val_acc"].append(val_metrics["accuracy"])
            history["val_f1"].append(val_metrics["macro_f1"])

            if verbose:
                lr_current = scheduler.get_last_lr()[0]
                print(
                    f"  Epoch {epoch:2d}/{epochs:2d} ({t1 - t0:.1f}s) | "
                    f"Train Loss: {train_metrics['loss']:.4f} Acc: {train_metrics['accuracy']:.3f} | "
                    f"Val Loss: {val_metrics['loss']:.4f} Acc: {val_metrics['accuracy']:.3f} "
                    f"F1: {val_metrics['macro_f1']:.3f} | LR: {lr_current:.2e}"
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
                        "config": self.model.config,
                    },
                    best_checkpoint_file,
                )
                if verbose:
                    print(f"    >>> Checkpoint saved (Best Val F1 = {best_val_f1:.4f})")

        return {
            "history": history,
            "best_val_f1": best_val_f1,
            "checkpoint_path": str(best_checkpoint_file),
        }
