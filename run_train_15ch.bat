@echo off
echo ========================================================
echo LAUNCHING HIGH-SPEED 15-CHANNEL MOMENT TRAINING (CUDA)
echo ========================================================
cd /d c:\Ngoding\xau_deep_sniper
call .venv\Scripts\activate.bat
python scripts\train_moment_15ch_fast.py --batch-size 128 --epochs 12 --warmup-epochs 1 --patience 3 --lr 0.00025 --lora-r 32 --lora-alpha 64
pause
