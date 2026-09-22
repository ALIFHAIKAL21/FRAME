"""
XAU_DEEP_SNIPER - MOMENT-1-large End-to-End Foundation Model Architecture (TAHAP 4C)
======================================================================================
Sesuai spesifikasi BAB 5 & BAB 6:
- 5.1: Arsitektur Model Tunggal (End-to-End Feature Extractor + Classifier)
  * Struktur Input Tensor: (B x C x L) di mana B = batch_size, C = 9 channel, L = 64 bar M30
  * Kepala Klasifikasi: Linear classification head dengan dropout (0.2)
  * Output: 5 probabilitas aksi diskrit P(a_t | X) in [0, 1]^5
- 6.3: Parameter-Efficient Fine-Tuning (PEFT / LoRA)
  * Base Transformer Backbone dibekukan (frozen)
  * Low-Rank Adaptation (LoRA: r=8, alpha=16) pada modul proyeksi atensi (W_q, W_v)
  * Kepala klasifikasi dilatih penuh

PRINSIP DESAIN:
- End-to-end single pipeline (no multi-model cascade to eliminate error compounding).
- Patch Embedding berkecepatan tinggi dengan learnable positional encodings.
- Trainable parameter fraction < 2% berkat LoRA.
"""

import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any


# =============================================================================
# 1. CONFIGURATION
# =============================================================================

@dataclass
class MOMENTConfig:
    n_channels: int = 9           # C = 9 feature channels (BAB 3.2)
    seq_len: int = 64             # L = 64 bars M30 (t-63 to t)
    patch_len: int = 8            # Patch size P = 8 bars (4 jam per patch)
    patch_stride: int = 8         # Non-overlapping patches (stride = 8)
    d_model: int = 1024           # MOMENT-1-large latent dimension
    num_layers: int = 6           # Encoder layers (6 untuk performa seimbang, max 24)
    num_heads: int = 16           # Attention heads
    d_ff: int = 2816              # Feed-forward expansion dimension
    dropout: float = 0.2          # Spec BAB 5.1: dropout 0.2
    num_classes: int = 5          # 5 discrete action classes (BAB 4.2)
    use_lora: bool = True         # PEFT / LoRA (BAB 6.3)
    lora_r: int = 8               # LoRA rank r = 8
    lora_alpha: int = 16          # LoRA scaling alpha = 16
    lora_dropout: float = 0.05    # LoRA adapter dropout


# =============================================================================
# 2. LOW-RANK ADAPTATION (LoRA) MODULE
# =============================================================================

class LoRALinear(nn.Module):
    """
    Linear layer dengan Low-Rank Adapter (LoRA).
    
    Formula:
        h = W * x + (alpha / r) * (B * A * x)
    di mana W dibekukan (requires_grad = False), dan A, B adalah matriks adaptasi.
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        r: int = 8,
        lora_alpha: int = 16,
        lora_dropout: float = 0.05,
        bias: bool = True,
    ):
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.r = r
        self.lora_alpha = lora_alpha
        self.scaling = (lora_alpha / r) if r > 0 else 1.0

        # Base linear layer (dibekukan)
        self.linear = nn.Linear(in_features, out_features, bias=bias)
        self.linear.weight.requires_grad = False
        if self.linear.bias is not None:
            self.linear.bias.requires_grad = False

        # LoRA parameters
        if r > 0:
            self.lora_A = nn.Parameter(torch.empty(r, in_features))
            self.lora_B = nn.Parameter(torch.zeros(out_features, r))
            self.lora_dropout = nn.Dropout(lora_dropout) if lora_dropout > 0 else nn.Identity()
            # Inisialisasi: Kaiming uniform untuk A, Zeros untuk B (adapter bernilai 0 di awal)
            nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            nn.init.zeros_(self.lora_B)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base_out = self.linear(x)
        if self.r > 0:
            lora_out = (self.lora_dropout(x) @ self.lora_A.T) @ self.lora_B.T
            return base_out + (self.scaling * lora_out)
        return base_out


# =============================================================================
# 3. PATCH EMBEDDING LAYER
# =============================================================================

class PatchEmbedding(nn.Module):
    """
    Memetakan deret waktu input (B, C, L) menjadi sequence token (B, num_patches, d_model).
    
    Setiap patch merepresentasikan segmen waktu patch_len bar dari seluruh C channel.
    Dimensi fitur per patch = C * patch_len (e.g. 9 * 8 = 72).
    """

    def __init__(self, config: MOMENTConfig):
        super().__init__()
        self.patch_len = config.patch_len
        self.stride = config.patch_stride
        self.n_channels = config.n_channels
        self.d_model = config.d_model

        # Jumlah patch sepanjang sequence L:
        # N_p = (L - P) // S + 1 = (64 - 8) // 8 + 1 = 8
        self.num_patches = (config.seq_len - self.patch_len) // self.stride + 1
        patch_dim = self.n_channels * self.patch_len

        # Linear projection patch -> d_model
        self.projection = nn.Linear(patch_dim, self.d_model)
        # Learnable positional embeddings
        self.pos_embedding = nn.Parameter(torch.randn(1, self.num_patches, self.d_model) * 0.02)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Input: (B, C, L) e.g. (B, 9, 64)
        Output: (B, num_patches, d_model) e.g. (B, 8, 1024)
        """
        B, C, L = x.shape
        P = self.patch_len
        S = self.stride

        # Unfold sequence menjadi patch: (B, C, num_patches, patch_len)
        patches = x.unfold(dimension=-1, size=P, step=S)
        # Permute ke: (B, num_patches, C, patch_len)
        patches = patches.permute(0, 2, 1, 3).contiguous()
        # Flatten C dan patch_len: (B, num_patches, C * patch_len)
        patches = patches.view(B, self.num_patches, C * P)

        # Proyeksi ke d_model + positional encoding
        embeddings = self.projection(patches) + self.pos_embedding
        return self.dropout(embeddings)


# =============================================================================
# 4. MULTI-HEAD ATTENTION DENGAN LORA (W_q, W_v)
# =============================================================================

class LoRAMultiHeadAttention(nn.Module):
    """
    Multi-Head Attention dengan LoRA adapters pada W_q dan W_v (BAB 6.3).
    """

    def __init__(self, config: MOMENTConfig):
        super().__init__()
        self.d_model = config.d_model
        self.num_heads = config.num_heads
        self.head_dim = config.d_model // config.num_heads
        assert self.head_dim * self.num_heads == self.d_model, "d_model harus kelipatan num_heads"

        r = config.lora_r if config.use_lora else 0
        alpha = config.lora_alpha
        lora_drop = config.lora_dropout

        # LoRA pada Query (W_q) dan Value (W_v)
        self.q_proj = LoRALinear(self.d_model, self.d_model, r=r, lora_alpha=alpha, lora_dropout=lora_drop)
        self.k_proj = nn.Linear(self.d_model, self.d_model)  # Frozen
        self.k_proj.weight.requires_grad = False
        if self.k_proj.bias is not None:
            self.k_proj.bias.requires_grad = False

        self.v_proj = LoRALinear(self.d_model, self.d_model, r=r, lora_alpha=alpha, lora_dropout=lora_drop)
        self.out_proj = nn.Linear(self.d_model, self.d_model)  # Frozen
        self.out_proj.weight.requires_grad = False
        if self.out_proj.bias is not None:
            self.out_proj.bias.requires_grad = False

        self.dropout = nn.Dropout(config.dropout)
        self.scale = 1.0 / math.sqrt(self.head_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, N, D = x.shape

        q = self.q_proj(x).view(B, N, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, N, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, N, self.num_heads, self.head_dim).transpose(1, 2)

        # Scaled Dot-Product Attention
        attn_scores = (q @ k.transpose(-2, -1)) * self.scale
        attn_probs = F.softmax(attn_scores, dim=-1)
        attn_probs = self.dropout(attn_probs)

        attn_out = attn_probs @ v  # (B, H, N, head_dim)
        attn_out = attn_out.transpose(1, 2).contiguous().view(B, N, D)
        return self.out_proj(attn_out)


# =============================================================================
# 5. TRANSFORMER ENCODER BLOCK
# =============================================================================

class TransformerBlock(nn.Module):
    def __init__(self, config: MOMENTConfig):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.d_model)
        self.attn = LoRAMultiHeadAttention(config)

        self.ln2 = nn.LayerNorm(config.d_model)
        # Gated MLP (seperti T5)
        self.fc1 = nn.Linear(config.d_model, config.d_ff)
        self.fc2 = nn.Linear(config.d_ff, config.d_model)
        self.dropout = nn.Dropout(config.dropout)
        self.activation = nn.GELU()

        # Freeze base MLP weights
        self.fc1.weight.requires_grad = False
        self.fc2.weight.requires_grad = False
        if self.fc1.bias is not None:
            self.fc1.bias.requires_grad = False
        if self.fc2.bias is not None:
            self.fc2.bias.requires_grad = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Pre-LN residual
        x = x + self.attn(self.ln1(x))
        x = x + self.dropout(self.fc2(self.activation(self.fc1(self.ln2(x)))))
        return x


# =============================================================================
# 6. CLASSIFICATION HEAD (BAB 5.1)
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
        # Head dilatih penuh (trainable)
        self.classifier.weight.requires_grad = True
        if self.classifier.bias is not None:
            self.classifier.bias.requires_grad = True

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
# 7. MOMENT-1-LARGE END-TO-END CLASSIFIER
# =============================================================================

class MOMENTClassifier(nn.Module):
    """
    Model Fondasi Tunggal End-to-End untuk XAU/USD M30.
    
    Arsitektur:
    Input (B, 9, 64) -> PatchEmbedding (B, 8, 1024) -> TransformerBlocks dengan LoRA
    -> Mean Pooling (B, 1024) -> ClassificationHead -> Logits (B, 5)
    """

    def __init__(self, config: Optional[MOMENTConfig] = None):
        super().__init__()
        self.config = config or MOMENTConfig()

        # 1. Patch Embedding
        self.patch_embed = PatchEmbedding(self.config)

        # 2. Transformer Blocks dengan LoRA pada W_q dan W_v
        self.blocks = nn.ModuleList([
            TransformerBlock(self.config) for _ in range(self.config.num_layers)
        ])
        self.norm = nn.LayerNorm(self.config.d_model)

        # 3. Linear Classification Head
        self.head = ClassificationHead(
            d_model=self.config.d_model,
            num_classes=self.config.num_classes,
            dropout=self.config.dropout,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass end-to-end.
        
        Parameters
        ----------
        x : torch.Tensor
            Input tensor dengan shape (B, C, L) = (B, 9, 64).
            
        Returns
        -------
        torch.Tensor
            Logits aksi dengan shape (B, 5).
        """
        # Patch embedding: (B, 9, 64) -> (B, num_patches, d_model)
        h = self.patch_embed(x)

        # Transformer blocks
        for block in self.blocks:
            h = block(h)
        h = self.norm(h)

        # Global average pooling sepanjang dimensi patch: (B, num_patches, d_model) -> (B, d_model)
        latent = h.mean(dim=1)

        # Classification head: (B, d_model) -> (B, num_classes)
        logits = self.head(latent)
        return logits

    @torch.no_grad()
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """Mengembalikan probabilitas softmax P(a_t | X) in [0, 1]^5."""
        self.eval()
        logits = self.forward(x)
        return F.softmax(logits, dim=-1)

    @torch.no_grad()
    def predict(self, x: torch.Tensor) -> torch.Tensor:
        """Mengembalikan aksi diskrit terprediksi argmax a in {0, 1, 2, 3, 4}."""
        probs = self.predict_proba(x)
        return torch.argmax(probs, dim=-1)

    def parameter_summary(self) -> Dict[str, Any]:
        """Menghitung ringkasan parameter dan efisiensi LoRA."""
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
