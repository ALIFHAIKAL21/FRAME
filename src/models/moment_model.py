"""
XAU_DEEP_SNIPER - MOMENT-1-large End-to-End Foundation Model Architecture (TAHAP 4C)
======================================================================================
Sesuai spesifikasi BAB 5 & BAB 6:
- 5.1: Arsitektur Model Tunggal (End-to-End Feature Extractor + Classifier)
  * Struktur Input Tensor: (B x C x L) di mana B = batch_size, C = 9 channel, L = 64 bar M30
  * Kepala Klasifikasi: Linear classification head dengan dropout (0.2)
  * Output: 5 probabilitas aksi diskrit P(a_t | X) in [0, 1]^5
- 6.3: Parameter-Efficient Fine-Tuning (PEFT / LoRA)
  * Base Pretrained Backbone (AutonLab/MOMENT-1-large) dibekukan (frozen)
  * Low-Rank Adaptation (LoRA: r=8, alpha=16) pada modul proyeksi atensi (W_q, W_v)
  * Kepala klasifikasi dilatih penuh

Mendukung dua mode:
1. `PretrainedMOMENTClassifier`: Menggunakan bobot asli AutonLab/MOMENT-1-large (342M params)
   dengan adapter LoRA resmi dari Hugging Face PEFT.
2. `MOMENTClassifier`: Mode mandiri ringan untuk testing lokal cepat.
"""

import math
import pathlib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, Union


# =============================================================================
# 1. CONFIGURATION
# =============================================================================

@dataclass
class MOMENTConfig:
    n_channels: int = 15           # C = 9 feature channels (BAB 3.2)
    seq_len: int = 64             # L = 64 bars M30 (t-63 to t)
    patch_len: int = 8            # Patch size P = 8 bars (4 jam per patch)
    patch_stride: int = 8         # Non-overlapping patches (stride = 8)
    d_model: int = 1024           # MOMENT-1-large latent dimension
    num_layers: int = 6           # Standalone encoder layers (max 24)
    num_heads: int = 16           # Attention heads
    d_ff: int = 2816              # Feed-forward expansion dimension
    dropout: float = 0.2          # Spec BAB 5.1: dropout 0.2
    num_classes: int = 5          # 5 discrete action classes (BAB 4.2)
    use_lora: bool = True         # PEFT / LoRA (BAB 6.3)
    lora_r: int = 32              # LoRA rank r = 32 (Iterasi 2)
    lora_alpha: int = 64          # LoRA scaling alpha = 64
    lora_dropout: float = 0.05    # LoRA adapter dropout
    use_pretrained_backbone: bool = False  # Set True untuk AutonLab/MOMENT-1-large


# =============================================================================
# 2. PATCH EMBEDDING LAYER DENGAN DATA AUGMENTASI
# =============================================================================

class PatchEmbedding(nn.Module):
    """
    Memetakan deret waktu input (B, C, L) menjadi sequence token (B, num_patches, d_model).
    Mendukung augmentasi Gaussian jittering dan patch masking saat training.
    """

    def __init__(
        self,
        n_channels: int = 15,
        seq_len: int = 64,
        patch_len: int = 8,
        patch_stride: int = 8,
        d_model: int = 1024,
        dropout: float = 0.2,
        jitter_std: float = 0.01,
        mask_prob: float = 0.125,
    ):
        super().__init__()
        self.patch_len = patch_len
        self.stride = patch_stride
        self.n_channels = n_channels
        self.d_model = d_model
        self.jitter_std = jitter_std
        self.mask_prob = mask_prob

        # N_p = (L - P) // S + 1 = (64 - 8) // 8 + 1 = 8
        self.num_patches = (seq_len - patch_len) // patch_stride + 1
        patch_dim = n_channels * patch_len

        # Linear projection patch -> d_model
        self.projection = nn.Linear(patch_dim, d_model)
        # Learnable positional embeddings
        self.pos_embedding = nn.Parameter(torch.randn(1, self.num_patches, d_model) * 0.02)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Input: (B, C, L) e.g. (B, 9, 64)
        Output: (B, num_patches, d_model) e.g. (B, 8, 1024)
        """
        B, C, L = x.shape

        # Data Augmentasi saat training: Gaussian jittering
        if self.training and self.jitter_std > 0:
            noise = torch.randn_like(x) * self.jitter_std
            x = x + noise

        # Unfold sequence menjadi patch: (B, C, num_patches, patch_len)
        patches = x.unfold(dimension=-1, size=self.patch_len, step=self.stride)
        patches = patches.permute(0, 2, 1, 3).contiguous()
        patches = patches.view(B, self.num_patches, C * self.patch_len)

        # Proyeksi ke d_model + positional encoding
        embeddings = self.projection(patches) + self.pos_embedding

        # Data Augmentasi saat training: Temporal Patch Masking (CutOut temporal)
        if self.training and self.mask_prob > 0:
            mask = (torch.rand(B, self.num_patches, 1, device=x.device) > self.mask_prob).float()
            embeddings = embeddings * mask

        return self.dropout(embeddings)


# =============================================================================
# 3. CLASSIFICATION HEAD (BAB 5.1)
# =============================================================================

class ClassificationHead(nn.Module):
    """
    Linear classification head dengan normalisasi dropout (0.2) yang langsung
    memetakan representasi laten MOMENT ke 5 probabilitas aksi diskrit.
    """

    def __init__(self, d_model: int = 1024, num_classes: int = 5, dropout: float = 0.2):
        super().__init__()
        self.layer_norm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(d_model, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Input: (B, d_model)
        Output: Logits (B, num_classes)
        """
        x = self.layer_norm(x)
        x = self.dropout(x)
        logits = self.classifier(x)
        return logits


# =============================================================================
# 4. PRETRAINED MOMENT-1-LARGE CLASSIFIER (PRODUKSI RISET ASLI)
# =============================================================================

class PretrainedMOMENTClassifier(nn.Module):
    """
    Implementasi Resmi Foundation Model AutonLab/MOMENT-1-large (342M Parameters)
    dengan LoRA adapters pada W_q dan W_v di seluruh 24 layer atensi.
    """

    def __init__(
        self,
        weights_path: Optional[str] = None,
        num_classes: int = 5,
        n_channels: int = 15,
        dropout: float = 0.2,
        lora_r: int = 32,
        lora_alpha: int = 64,
        lora_dropout: float = 0.05,
        target_modules: Optional[list] = None,
    ):
        self.n_channels = n_channels
        super().__init__()
        import safetensors.torch
        from transformers import T5Config, T5EncoderModel
        from peft import LoraConfig, get_peft_model
        from huggingface_hub import hf_hub_download

        self.num_classes = num_classes
        self.d_model = 1024

        # 1. Unduh / muat weights AutonLab/MOMENT-1-large jika belum ada
        if weights_path is None:
            weights_path = hf_hub_download("AutonLab/MOMENT-1-large", "model.safetensors")

        # 2. Inisialisasi T5EncoderModel dengan konfigurasi flan-t5-large
        t5_cfg = T5Config.from_pretrained("google/flan-t5-large")
        base_encoder = T5EncoderModel(t5_cfg)

        # 3. Muat bobot resmi pretrained MOMENT-1-large
        state_dict = safetensors.torch.load_file(weights_path, device="cpu")
        base_encoder.load_state_dict(state_dict, strict=False)

        # 4. Pasang Deep LoRA Adapters pada seluruh Proyeksi Atensi (q, k, v, o)
        if target_modules is None:
            target_modules = ["q", "k", "v", "o"]

        lora_config = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            target_modules=target_modules,
            lora_dropout=lora_dropout,
            bias="none",
        )
        self.encoder = get_peft_model(base_encoder, lora_config)

        # 5. Patch Embedding khusus 12 Channel XAU/USD (MA Cross, SMI, SMC)
        self.patch_embed = PatchEmbedding(
            n_channels=n_channels,
            seq_len=64,
            patch_len=8,
            patch_stride=8,
            d_model=self.d_model,
            dropout=dropout,
        )

        # 6. Linear Classification Head
        self.head = ClassificationHead(
            d_model=self.d_model,
            num_classes=num_classes,
            dropout=dropout,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Input: (B, 9, 64) -> Output: (B, 5) logits
        """
        # Patch embedding: (B, 9, 64) -> (B, 8, 1024)
        tokens = self.patch_embed(x)

        # Forward pass melalui 24 layer T5 Encoder dengan LoRA
        encoder_outputs = self.encoder(inputs_embeds=tokens)
        hidden_states = encoder_outputs.last_hidden_state  # (B, 8, 1024)

        # Mean pooling sepanjang patch
        latent = hidden_states.mean(dim=1)  # (B, 1024)

        # Classification Head: (B, 1024) -> (B, 5)
        logits = self.head(latent)
        return logits

    @torch.no_grad()
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        self.eval()
        logits = self.forward(x)
        return F.softmax(logits, dim=-1)

    @torch.no_grad()
    def predict(self, x: torch.Tensor) -> torch.Tensor:
        probs = self.predict_proba(x)
        return torch.argmax(probs, dim=-1)

    def parameter_summary(self) -> Dict[str, Any]:
        total_params = sum(p.numel() for p in self.parameters())
        trainable_params = sum(p.numel() for p in self.parameters() if p.requires_grad)
        frozen_params = total_params - trainable_params
        trainable_pct = (trainable_params / total_params * 100) if total_params > 0 else 0.0

        return {
            "model_type": "PretrainedMOMENT-1-large (Carnegie Mellon University)",
            "total_parameters": total_params,
            "trainable_parameters": trainable_params,
            "frozen_parameters": frozen_params,
            "trainable_percentage": round(trainable_pct, 3),
            "d_model": self.d_model,
            "num_classes": self.num_classes,
        }


# =============================================================================
# 5. STANDALONE MOMENT CLASSIFIER (UNTUK TESTING CEPAT & UNIT TESTS)
# =============================================================================

class LoRALinear(nn.Module):
    def __init__(self, in_features: int, out_features: int, r: int = 8, lora_alpha: int = 16, lora_dropout: float = 0.05, bias: bool = True):
        super().__init__()
        self.linear = nn.Linear(in_features, out_features, bias=bias)
        self.linear.weight.requires_grad = False
        if self.linear.bias is not None:
            self.linear.bias.requires_grad = False
        self.r = r
        self.scaling = (lora_alpha / r) if r > 0 else 1.0
        if r > 0:
            self.lora_A = nn.Parameter(torch.empty(r, in_features))
            self.lora_B = nn.Parameter(torch.zeros(out_features, r))
            self.lora_dropout = nn.Dropout(lora_dropout) if lora_dropout > 0 else nn.Identity()
            nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            nn.init.zeros_(self.lora_B)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = self.linear(x)
        if self.r > 0:
            lora = (self.lora_dropout(x) @ self.lora_A.T) @ self.lora_B.T
            return base + (self.scaling * lora)
        return base


class LoRAMultiHeadAttention(nn.Module):
    def __init__(self, config: MOMENTConfig):
        super().__init__()
        self.d_model = config.d_model
        self.num_heads = config.num_heads
        self.head_dim = config.d_model // config.num_heads
        r = config.lora_r if config.use_lora else 0
        self.q_proj = LoRALinear(self.d_model, self.d_model, r=r, lora_alpha=config.lora_alpha, lora_dropout=config.lora_dropout)
        self.k_proj = nn.Linear(self.d_model, self.d_model)
        self.k_proj.weight.requires_grad = False
        self.v_proj = LoRALinear(self.d_model, self.d_model, r=r, lora_alpha=config.lora_alpha, lora_dropout=config.lora_dropout)
        self.out_proj = nn.Linear(self.d_model, self.d_model)
        self.out_proj.weight.requires_grad = False
        self.dropout = nn.Dropout(config.dropout)
        self.scale = 1.0 / math.sqrt(self.head_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, N, D = x.shape
        q = self.q_proj(x).view(B, N, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, N, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, N, self.num_heads, self.head_dim).transpose(1, 2)
        attn_scores = (q @ k.transpose(-2, -1)) * self.scale
        attn_probs = self.dropout(F.softmax(attn_scores, dim=-1))
        attn_out = (attn_probs @ v).transpose(1, 2).contiguous().view(B, N, D)
        return self.out_proj(attn_out)


class TransformerBlock(nn.Module):
    def __init__(self, config: MOMENTConfig):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.d_model)
        self.attn = LoRAMultiHeadAttention(config)
        self.ln2 = nn.LayerNorm(config.d_model)
        self.fc1 = nn.Linear(config.d_model, config.d_ff)
        self.fc2 = nn.Linear(config.d_ff, config.d_model)
        self.fc1.weight.requires_grad = False
        self.fc2.weight.requires_grad = False
        self.dropout = nn.Dropout(config.dropout)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.ln1(x))
        x = x + self.dropout(self.fc2(self.act(self.fc1(self.ln2(x)))))
        return x


class MOMENTClassifier(nn.Module):
    def __init__(self, config: Optional[MOMENTConfig] = None):
        super().__init__()
        self.config = config or MOMENTConfig()
        self.patch_embed = PatchEmbedding(
            n_channels=self.config.n_channels,
            seq_len=self.config.seq_len,
            patch_len=self.config.patch_len,
            patch_stride=self.config.patch_stride,
            d_model=self.config.d_model,
            dropout=self.config.dropout,
        )
        self.blocks = nn.ModuleList([TransformerBlock(self.config) for _ in range(self.config.num_layers)])
        self.norm = nn.LayerNorm(self.config.d_model)
        self.head = ClassificationHead(d_model=self.config.d_model, num_classes=self.config.num_classes, dropout=self.config.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.patch_embed(x)
        for block in self.blocks:
            h = block(h)
        h = self.norm(h)
        latent = h.mean(dim=1)
        return self.head(latent)

    @torch.no_grad()
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        self.eval()
        return F.softmax(self.forward(x), dim=-1)

    @torch.no_grad()
    def predict(self, x: torch.Tensor) -> torch.Tensor:
        return torch.argmax(self.predict_proba(x), dim=-1)

    def parameter_summary(self) -> Dict[str, Any]:
        total_params = sum(p.numel() for p in self.parameters())
        trainable_params = sum(p.numel() for p in self.parameters() if p.requires_grad)
        frozen_params = total_params - trainable_params
        trainable_pct = (trainable_params / total_params * 100) if total_params > 0 else 0.0
        return {
            "total_parameters": total_params,
            "trainable_parameters": trainable_params,
            "frozen_parameters": frozen_params,
            "trainable_percentage": round(trainable_pct, 3),
            "use_lora": self.config.use_lora,
            "lora_rank": self.config.lora_r,
            "d_model": self.config.d_model,
            "num_layers": self.config.num_layers,
            "num_classes": self.config.num_classes,
        }
