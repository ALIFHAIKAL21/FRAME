"""
XAU_DEEP_SNIPER - Class-Balanced Focal Loss & Weights (TAHAP 3C)
=================================================================
Sesuai spesifikasi BAB 6.2:
- Penanganan Ketimpangan Kelas (Class-Balanced Focal Loss)
  FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
- Parameter pemfokus gamma = 2.0 meredam gradien dari sampel mudah
  (sideways/HOLD pasar yang dominan).
- Bobot alpha_t memprioritaskan momentum kelas 1, 2, 3, dan 4.

PRINSIP DESAIN:
- Kompatibel dengan NumPy (untuk evaluasi/analisis) dan PyTorch (untuk training).
- Proteksi terhadap kelas dengan frekuensi 0 (epsilon smoothing).
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Union

NUM_CLASSES: int = 5
DEFAULT_GAMMA: float = 2.0


def compute_focal_weights(
    labels: Union[pd.Series, np.ndarray],
    num_classes: int = NUM_CLASSES,
    method: str = "inverse_frequency",
    beta: float = 0.999,
) -> Dict[str, Union[Dict[int, float], List[float]]]:
    """
    Menghitung bobot alpha_c untuk penyeimbang kelas pada Focal Loss.
    
    Parameters
    ----------
    labels : pd.Series atau np.ndarray
        Array label diskrit a in {0, 1, 2, 3, 4}.
    num_classes : int
        Jumlah kelas target (default 5).
    method : str
        'inverse_frequency' atau 'effective_samples' (Cui et al., 2019).
    beta : float
        Hyperparameter untuk method 'effective_samples' (0.99 - 0.9999).
        
    Returns
    -------
    dict
        {
            "class_counts": {0: N0, 1: N1, ...},
            "class_percentages": {0: pct0, ...},
            "alpha_weights": [alpha_0, alpha_1, ...],
            "gamma": 2.0,
            "total_samples": N
        }
    """
    if isinstance(labels, pd.Series):
        labels_arr = labels.values
    else:
        labels_arr = np.asarray(labels)
        
    total_samples = len(labels_arr)
    if total_samples == 0:
        raise ValueError("Labels array tidak boleh kosong")
        
    # Hitung frekuensi tiap kelas
    counts = {}
    percentages = {}
    for c in range(num_classes):
        cnt = int((labels_arr == c).sum())
        counts[c] = cnt
        percentages[c] = round(cnt / total_samples * 100, 3)
        
    raw_weights = np.zeros(num_classes, dtype=np.float64)
    eps = 1e-6
    
    if method == "inverse_frequency":
        # alpha_c = N_total / (C * N_c)
        for c in range(num_classes):
            cnt = counts[c]
            if cnt > 0:
                raw_weights[c] = total_samples / (num_classes * cnt)
            else:
                raw_weights[c] = 1.0  # fallback jika kelas kosong
                
    elif method == "effective_samples":
        # E_n = (1 - beta^n) / (1 - beta)
        # alpha_c = 1 / E_n
        for c in range(num_classes):
            cnt = counts[c]
            if cnt > 0:
                eff_num = (1.0 - np.power(beta, cnt)) / (1.0 - beta)
                raw_weights[c] = 1.0 / max(eff_num, eps)
            else:
                raw_weights[c] = 1.0
    else:
        raise ValueError(f"Metode bobot tidak dikenal: {method}")
        
    # Normalisasi agar rata-rata bobot = 1.0 (jumlah = num_classes)
    normalized_weights = raw_weights / raw_weights.sum() * num_classes
    alpha_list = [round(float(w), 4) for w in normalized_weights]
    
    return {
        "class_counts": counts,
        "class_percentages": percentages,
        "alpha_weights": alpha_list,
        "gamma": DEFAULT_GAMMA,
        "total_samples": total_samples,
    }


def numpy_focal_loss(
    y_true: np.ndarray,
    y_pred_probs: np.ndarray,
    alpha: Optional[List[float]] = None,
    gamma: float = DEFAULT_GAMMA,
) -> float:
    """
    Implementasi Focal Loss menggunakan NumPy murni untuk evaluasi metrik.
    
    Parameters
    ----------
    y_true : np.ndarray
        Array label integer (N,) dengan nilai 0 s.d. C-1.
    y_pred_probs : np.ndarray
        Array probabilitas (N, C) dari softmax output model.
    alpha : list of float, optional
        Bobot penyeimbang per kelas.
    gamma : float
        Focusing parameter (default 2.0).
        
    Returns
    -------
    float
        Mean focal loss value.
    """
    eps = 1e-12
    probs = np.clip(y_pred_probs, eps, 1.0 - eps)
    N, C = probs.shape
    
    if alpha is None:
        alpha_arr = np.ones(C, dtype=np.float64)
    else:
        alpha_arr = np.asarray(alpha, dtype=np.float64)
        
    # Ambil probabilitas untuk kelas target aktual
    pt = probs[np.arange(N), y_true]
    at = alpha_arr[y_true]
    
    # FL = -alpha * (1 - pt)^gamma * log(pt)
    focal_weight = at * np.power(1.0 - pt, gamma)
    loss = -focal_weight * np.log(pt)
    
    return float(np.mean(loss))
