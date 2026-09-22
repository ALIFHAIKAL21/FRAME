"""
XAU_DEEP_SNIPER - Class-Balanced Focal Loss Module (TAHAP 4B)
==============================================================
Sesuai spesifikasi BAB 6.2:
- Penanganan Ketimpangan Kelas (Class-Balanced Focal Loss)
  FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
- Parameter pemfokus gamma = 2.0 meredam gradien dari sampel mudah
  (sideways pasar yang dominan).
- Bobot alpha_t memprioritaskan momentum kelas 1, 2, 3, dan 4.

PRINSIP DESAIN:
- Numerik stabil dengan F.cross_entropy.
- Dukungan device agnostic (CPU / CUDA / MPS).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Optional, Union

DEFAULT_GAMMA: float = 2.0


class ClassBalancedFocalLoss(nn.Module):
    """
    Class-Balanced Focal Loss untuk klasifikasi momentum 5 kelas.
    
    Parameters
    ----------
    alpha : list atau torch.Tensor, optional
        Tensor bobot penyeimbang per kelas (shape: [num_classes]).
    gamma : float
        Focusing parameter (default 2.0).
    reduction : str
        'mean', 'sum', atau 'none'.
    """

    def __init__(
        self,
        alpha: Optional[Union[List[float], torch.Tensor]] = None,
        gamma: float = DEFAULT_GAMMA,
        reduction: str = "mean",
    ):
        super().__init__()
        self.gamma = gamma
        self.reduction = reduction

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
            Nilai Focal Loss.
        """
        # ce_loss = -log(p_t)
        ce_loss = F.cross_entropy(logits, targets, reduction="none")

        # p_t = exp(-ce_loss)
        pt = torch.exp(-ce_loss)

        # focal_term = (1 - p_t)^gamma
        focal_term = torch.pow(1.0 - pt, self.gamma)

        if self.alpha is not None:
            alpha_t = self.alpha[targets]
            loss = alpha_t * focal_term * ce_loss
        else:
            loss = focal_term * ce_loss

        if self.reduction == "mean":
            return loss.mean()
        elif self.reduction == "sum":
            return loss.sum()
        return loss
