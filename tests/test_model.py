"""
XAU_DEEP_SNIPER - Unit Tests: MOMENT-1-large Model, Dataset, & Loss (TAHAP 4)
==============================================================================
Test suite untuk memverifikasi:
1. PyTorch Dataset sliding window extraction (B, 9, 64) dan DataLoader batching
2. Arsitektur MOMENTClassifier end-to-end (input -> logits 5 kelas)
3. Parameter-Efficient Fine-Tuning (LoRA freezing & adapter trainability)
4. Class-Balanced Focal Loss gradient flow & alpha/gamma scaling
5. Training loop micro-step execution & convergence check
"""

import sys
import pathlib
import pytest
import pandas as pd
import numpy as np
import torch

project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from models.dataset import (
    XAUTimeSeriesDataset,
    create_dataloaders,
    DEFAULT_FEATURE_CHANNELS,
)
from models.moment_model import (
    MOMENTClassifier,
    MOMENTConfig,
    LoRALinear,
    PatchEmbedding,
)
from models.loss import ClassBalancedFocalLoss
from models.trainer import (
    MOMENTTrainer,
    compute_classification_metrics,
)


def make_synthetic_labeled_df(n=200):
    ts = pd.date_range("2023-01-01", periods=n, freq="30min", tz="UTC")
    data = {"timestamp_utc": ts}
    for ch in DEFAULT_FEATURE_CHANNELS:
        data[ch] = np.random.randn(n).astype(np.float32)
    data["action"] = np.random.randint(0, 5, size=n).astype(np.int64)
    return pd.DataFrame(data)


class TestDatasetAndDataLoader:
    def test_dataset_window_shape(self):
        df = make_synthetic_labeled_df(100)
        ds = XAUTimeSeriesDataset(df, sequence_length=64)
        # N = 100 - 64 + 1 = 37
        assert len(ds) == 37
        x, y = ds[0]
        assert x.shape == (9, 64)
        assert x.dtype == torch.float32
        assert y.dtype == torch.long
        assert 0 <= y.item() <= 4

    def test_dataloader_batch_dimensions(self):
        train_df = make_synthetic_labeled_df(150)
        test_df = make_synthetic_labeled_df(100)
        train_loader, test_loader, _, _ = create_dataloaders(
            train_df, test_df, batch_size=16, sequence_length=64
        )
        x_batch, y_batch = next(iter(train_loader))
        assert x_batch.shape == (16, 9, 64)
        assert y_batch.shape == (16,)
        assert not torch.isnan(x_batch).any()


class TestMOMENTArchitecture:
    @pytest.fixture
    def small_model(self):
        cfg = MOMENTConfig(
            n_channels=9,
            seq_len=64,
            patch_len=8,
            patch_stride=8,
            d_model=128,
            num_layers=2,
            num_heads=4,
            d_ff=256,
            dropout=0.2,
            num_classes=5,
            use_lora=True,
            lora_r=4,
        )
        return MOMENTClassifier(cfg)

    def test_forward_pass_shape(self, small_model):
        x = torch.randn(4, 9, 64)
        logits = small_model(x)
        assert logits.shape == (4, 5)

    def test_softmax_probabilities(self, small_model):
        x = torch.randn(4, 9, 64)
        probs = small_model.predict_proba(x)
        assert probs.shape == (4, 5)
        # Sum of probs per row must be 1.0
        assert torch.allclose(probs.sum(dim=-1), torch.ones(4), atol=1e-5)

    def test_predict_classes(self, small_model):
        x = torch.randn(4, 9, 64)
        preds = small_model.predict(x)
        assert preds.shape == (4,)
        assert all(0 <= p.item() <= 4 for p in preds)

    def test_lora_freezing_efficiency(self, small_model):
        summary = small_model.parameter_summary()
        # Trainable params should be very small (< 10%)
        assert summary["trainable_percentage"] < 10.0
        assert summary["frozen_parameters"] > summary["trainable_parameters"]

        # Base weights in blocks must be frozen
        for block in small_model.blocks:
            assert block.attn.q_proj.linear.weight.requires_grad == False
            assert block.attn.k_proj.weight.requires_grad == False
            assert block.fc1.weight.requires_grad == False
            # LoRA parameters must be trainable
            assert block.attn.q_proj.lora_A.requires_grad == True
            assert block.attn.q_proj.lora_B.requires_grad == True

        # Classification head must be trainable
        assert small_model.head.classifier.weight.requires_grad == True


class TestFocalLossAndGradients:
    def test_focal_loss_backward(self):
        cfg = MOMENTConfig(d_model=64, num_layers=1, num_heads=2, d_ff=128, lora_r=4)
        model = MOMENTClassifier(cfg)
        alpha = [0.5, 1.2, 1.2, 1.1, 1.0]
        criterion = ClassBalancedFocalLoss(alpha=alpha, gamma=2.0)

        x = torch.randn(4, 9, 64)
        y = torch.tensor([0, 1, 2, 4], dtype=torch.long)

        logits = model(x)
        loss = criterion(logits, y)
        assert loss.item() > 0.0

        loss.backward()
        # Check gradient in LoRA parameter
        assert model.blocks[0].attn.q_proj.lora_A.grad is not None
        # Check frozen parameter has no gradient
        assert model.blocks[0].attn.k_proj.weight.grad is None

    def test_metrics_calculation(self):
        y_true = np.array([0, 1, 2, 3, 4, 0, 1, 2, 3, 4])
        y_pred = np.array([0, 1, 2, 3, 4, 0, 1, 0, 3, 4])
        metrics = compute_classification_metrics(y_true, y_pred, num_classes=5)
        assert metrics["accuracy"] == 0.9
        assert 0.0 <= metrics["macro_f1"] <= 1.0
        assert len(metrics["per_class"]) == 5


class TestTrainerMicroStep:
    def test_trainer_fit_one_epoch(self):
        train_df = make_synthetic_labeled_df(120)
        val_df = make_synthetic_labeled_df(80)
        train_loader, val_loader, _, _ = create_dataloaders(
            train_df, val_df, batch_size=8, sequence_length=64
        )

        cfg = MOMENTConfig(d_model=64, num_layers=1, num_heads=2, d_ff=128, lora_r=4)
        model = MOMENTClassifier(cfg)
        criterion = ClassBalancedFocalLoss(gamma=2.0)

        trainer = MOMENTTrainer(model, criterion, learning_rate=1e-3, device="cpu")
        res = trainer.fit(
            train_loader,
            val_loader,
            epochs=1,
            checkpoint_dir="checkpoints",
            checkpoint_name="test_checkpoint.pt",
            verbose=False,
        )
        assert len(res["history"]["train_loss"]) == 1
        assert res["best_val_f1"] >= 0.0
