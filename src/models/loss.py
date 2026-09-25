"""
XAU_DEEP_SNIPER - Class-Balanced Focal Loss & Directional Auxiliary Loss (TAHAP 4B & ITERASI 2)
=============================================================================================
Sesuai spesifikasi BAB 6.2 & Rencana Peningkatan Arsitektur (Iterasi 2):
1. Class-Balanced Focal Loss:
   FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
   - Parameter pemfokus gamma = 2.5 meredam gradien dari sampel mudah (sideways pasar yang dominan).
   - Bobot alpha_t melindungi kelas HOLD (alpha_0 >= 1.0) dan memprioritaskan momentum kelas 1, 2, 3, dan 4.

2. Directional Auxiliary Loss (L_dir):
   - Mencegah fenomena Directional Inversion (akurasi arah sub-50%).
   - Untuk setiap sampel non-HOLD (y in {1, 2, 3, 4}):
     P_BUY = P(class 1) + P(class 2)
     P_SELL = P(class 3) + P(class 4)
     q_BUY = P_BUY / (P_BUY + P_SELL + eps)
     L_dir = - [ d * log(q_BUY) + (1 - d) * log(1 - q_BUY) ]
     di mana d = 1.0 jika target in [1, 2], d = 0.0 jika target in [3, 4].
   - L_total = L_focal + lambda_dir * L_dir

PRINSIP DESAIN:
- Numerik stabil, tidak menghasilkan NaN/Inf.
- Dukungan device agnostic (CPU / CUDA / MPS).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Optional, Union

DEFAULT_GAMMA: float = 2.5
DEFAULT_DIR_WEIGHT: float = 0.5


class ClassBalancedFocalLoss(nn.Module):
    """
    Class-Balanced Focal Loss untuk klasifikasi momentum 5 kelas.
    
    Parameters
    ----------
    alpha : list atau torch.Tensor, optional
        Tensor bobot penyeimbang per kelas (shape: [num_classes]).
    gamma : float
        Focusing parameter (default 2.5).
    reduction : str
        'mean', 'sum', atau 'none'.
    directional_weight : float
        Bobot untuk Directional Auxiliary Loss (default 0.0 untuk backward compatibility).
    """

    def __init__(
        self,
        alpha: Optional[Union[List[float], torch.Tensor]] = None,
        gamma: float = DEFAULT_GAMMA,
        reduction: str = "mean",
        directional_weight: float = 0.0,
    ):
        super().__init__()
        self.gamma = gamma
        self.reduction = reduction
        self.directional_weight = float(directional_weight)

        if alpha is not None:
            if isinstance(alpha, list):
                alpha_tensor = torch.tensor(alpha, dtype=torch.float32)
            else:
                alpha_tensor = alpha.clone().detach().to(dtype=torch.float32)
            self.register_buffer("alpha", alpha_tensor)
        else:
            self.alpha = None

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        logits : torch.Tensor
            Prediksi mentah sebelum softmax (shape: [B, C]).
        targets : torch.Tensor
            Label target ground truth (shape: [B]).
            
        Returns
        -------
        torch.Tensor
            Nilai Total Loss.
        """
        # 1. Focal Loss Computation
        ce_loss = F.cross_entropy(logits, targets, reduction="none")
        pt = torch.exp(-ce_loss)
        focal_term = torch.pow(1.0 - pt, self.gamma)

        if self.alpha is not None:
            alpha_t = self.alpha[targets]
            focal_loss = alpha_t * focal_term * ce_loss
        else:
            focal_loss = focal_term * ce_loss

        base_loss = focal_loss.mean() if self.reduction == "mean" else (
            focal_loss.sum() if self.reduction == "sum" else focal_loss
        )

        # 2. Directional Auxiliary Loss (jika directional_weight > 0)
        if self.directional_weight <= 0:
            return base_loss

        non_hold_mask = (targets != 0)
        if not non_hold_mask.any():
            return base_loss

        probs = F.softmax(logits, dim=-1)
        p_buy = probs[:, 1] + probs[:, 2]
        p_sell = probs[:, 3] + probs[:, 4]
        q_buy = p_buy / (p_buy + p_sell + 1e-7)
        q_buy = torch.clamp(q_buy, 1e-6, 1.0 - 1e-6)

        target_dir = ((targets == 1) | (targets == 2)).float()
        dir_bce = -(target_dir * torch.log(q_buy) + (1.0 - target_dir) * torch.log(1.0 - q_buy))

        dir_loss = (dir_bce * non_hold_mask.float()).sum() / (non_hold_mask.float().sum() + 1e-7)
        return base_loss + self.directional_weight * dir_loss


class DirectionalFocalLoss(ClassBalancedFocalLoss):
    """
    Subclass ClassBalancedFocalLoss yang secara default mengaktifkan
    Directional Auxiliary Loss (directional_weight = 0.5, gamma = 2.5).
    """

    def __init__(
        self,
        alpha: Optional[Union[List[float], torch.Tensor]] = None,
        gamma: float = DEFAULT_GAMMA,
        reduction: str = "mean",
        directional_weight: float = DEFAULT_DIR_WEIGHT,
    ):
        super().__init__(
            alpha=alpha,
            gamma=gamma,
            reduction=reduction,
            directional_weight=directional_weight,
        )
