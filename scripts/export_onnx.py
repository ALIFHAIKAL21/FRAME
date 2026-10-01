"""
MOMENT-1-large PyTorch → ONNX Export Script
=============================================
Exports the trained PretrainedMOMENT15ch model to ONNX format for 
CPU-only inference on Streamlit Cloud without PyTorch dependency.

Input:  checkpoints/best_moment_15ch_pretrained_lora.pt  (1.4 GB PyTorch)
Output: checkpoints/moment_15ch_production.onnx           (~50-80 MB ONNX)

Usage:
  .venv\Scripts\python.exe scripts/export_onnx.py
"""

import sys, pathlib, time
import numpy as np
import torch
import torch.nn as nn

project_root = pathlib.Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.train_moment_15ch_pretrained import PretrainedMOMENT15ch

CHECKPOINT_PATH = project_root / "checkpoints" / "best_moment_15ch_pretrained_lora.pt"
ONNX_OUTPUT     = project_root / "checkpoints" / "moment_15ch_production.onnx"

# ==============================================================================
# 1. Load PyTorch Model
# ==============================================================================
print("=" * 70)
print("MOMENT-1-large → ONNX Export")
print("=" * 70)

print("\n[1/5] Loading PyTorch model...")
t0 = time.time()
device = torch.device("cpu")  # Export on CPU for maximum compatibility
model = PretrainedMOMENT15ch().to(device)
ckpt = torch.load(CHECKPOINT_PATH, map_location=device, weights_only=False)
model.load_state_dict(ckpt["model_state_dict"])
model.eval()
print(f"      Model loaded in {time.time()-t0:.1f}s")

# ==============================================================================
# 2. Merge LoRA weights into base model (eliminate PEFT dependency at runtime)
# ==============================================================================
print("\n[2/5] Merging LoRA adapters into base encoder weights...")
try:
    model.encoder = model.encoder.merge_and_unload()
    print("      LoRA merged successfully — no PEFT needed at runtime")
except Exception as e:
    print(f"      LoRA merge warning: {e}")
    print("      Proceeding with unmerged model (slightly larger ONNX)")

# ==============================================================================
# 3. Create dummy input and verify PyTorch output
# ==============================================================================
print("\n[3/5] Creating dummy input (B=1, C=15, L=64)...")
dummy_input = torch.randn(1, 15, 64, device=device)

with torch.no_grad():
    pytorch_output = model(dummy_input)
    pytorch_probs = torch.softmax(pytorch_output, dim=-1).numpy()[0]

print(f"      PyTorch output shape: {pytorch_output.shape}")
print(f"      PyTorch probs: {[f'{p:.4f}' for p in pytorch_probs]}")

# ==============================================================================
# 4. Export to ONNX
# ==============================================================================
print(f"\n[4/5] Exporting to ONNX: {ONNX_OUTPUT}")
t1 = time.time()

torch.onnx.export(
    model,
    dummy_input,
    str(ONNX_OUTPUT),
    export_params=True,
    opset_version=17,
    do_constant_folding=True,
    input_names=["features"],       # (B, 15, 64)
    output_names=["logits"],        # (B, 5)
    dynamic_axes={
        "features": {0: "batch_size"},
        "logits":   {0: "batch_size"}
    }
)

onnx_size_mb = ONNX_OUTPUT.stat().st_size / (1024 * 1024)
print(f"      Export completed in {time.time()-t1:.1f}s")
print(f"      ONNX file size: {onnx_size_mb:.1f} MB")

# ==============================================================================
# 5. Verify ONNX output matches PyTorch
# ==============================================================================
print("\n[5/5] Verifying ONNX output matches PyTorch...")
try:
    import onnxruntime as ort
    
    sess = ort.InferenceSession(str(ONNX_OUTPUT), providers=["CPUExecutionProvider"])
    onnx_result = sess.run(["logits"], {"features": dummy_input.numpy()})
    onnx_logits = onnx_result[0]
    
    # Softmax for comparison
    onnx_exp = np.exp(onnx_logits[0] - np.max(onnx_logits[0]))
    onnx_probs = onnx_exp / onnx_exp.sum()
    
    max_diff = np.max(np.abs(pytorch_probs - onnx_probs))
    print(f"      ONNX  probs: {[f'{p:.4f}' for p in onnx_probs]}")
    print(f"      Max abs diff: {max_diff:.8f}")
    
    if max_diff < 1e-4:
        print("      ✅ VERIFICATION PASSED — ONNX output is numerically identical to PyTorch")
    elif max_diff < 1e-2:
        print("      ⚠️  Small numerical difference (acceptable for float32 precision)")
    else:
        print("      ❌ WARNING: Large difference detected — investigate before deploying!")
        
except ImportError:
    print("      ⚠️  onnxruntime not installed — skipping verification")
    print("      Install: pip install onnxruntime")

# ==============================================================================
# Summary
# ==============================================================================
print("\n" + "=" * 70)
print("EXPORT COMPLETE")
print(f"  PyTorch checkpoint: {CHECKPOINT_PATH} ({CHECKPOINT_PATH.stat().st_size/(1024*1024):.0f} MB)")
print(f"  ONNX model:         {ONNX_OUTPUT} ({onnx_size_mb:.1f} MB)")
print(f"  Size reduction:     {(1 - onnx_size_mb / (CHECKPOINT_PATH.stat().st_size/(1024*1024))) * 100:.0f}%")
print(f"  Runtime dependency: onnxruntime (CPU only, ~15 MB pip install)")
print("=" * 70)
