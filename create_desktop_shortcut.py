"""
Create Windows Desktop Shortcut and Start Menu entry for FRAME
"""

import sys, pathlib, subprocess, os

project_root = pathlib.Path(__file__).resolve().parent
desktop_dir = pathlib.Path(os.environ.get("USERPROFILE", "C:\\Users\\haika")) / "Desktop"
start_menu_dir = pathlib.Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

icon_file = project_root / "assets" / "frame_icon.ico"
root_exe = project_root / "FRAME.exe"
dist_exe = project_root / "dist" / "FRAME" / "FRAME.exe"

if root_exe.exists():
    target_path = str(root_exe)
    target_args = ""
elif dist_exe.exists():
    target_path = str(dist_exe)
    target_args = ""
else:
    pythonw_exe = project_root / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw_exe.exists():
        pythonw_exe = project_root / ".venv" / "Scripts" / "python.exe"
    target_path = str(pythonw_exe)
    target_args = f'"{project_root / "FRAME.py"}"'

print(f"[SHORTCUT] Target: {target_path}")
print(f"[SHORTCUT] Icon: {icon_file}")
print(f"[SHORTCUT] Working Dir: {project_root}")

# Create desktop shortcut via PowerShell
ps_script = f"""
$WshShell = New-Object -comObject WScript.Shell

# 1. Desktop Shortcut
$DeskShortcut = $WshShell.CreateShortcut("{desktop_dir / 'FRAME.lnk'}")
$DeskShortcut.TargetPath = "{target_path}"
$DeskShortcut.Arguments = '{target_args}'
$DeskShortcut.WorkingDirectory = "{project_root}"
$DeskShortcut.IconLocation = "{icon_file}"
$DeskShortcut.Description = "FLOWDEV FRAME - Quantitative Enterprise Desktop Terminal"
$DeskShortcut.Save()

# 2. Start Menu Shortcut
if (Test-Path "{start_menu_dir}") {{
    $StartShortcut = $WshShell.CreateShortcut("{start_menu_dir / 'FRAME.lnk'}")
    $StartShortcut.TargetPath = "{target_path}"
    $StartShortcut.Arguments = '{target_args}'
    $StartShortcut.WorkingDirectory = "{project_root}"
    $StartShortcut.IconLocation = "{icon_file}"
    $StartShortcut.Description = "FLOWDEV FRAME - Quantitative Enterprise Desktop Terminal"
    $StartShortcut.Save()
}}
"""

res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
if res.returncode == 0:
    print(f"[SUCCESS] Desktop Shortcut created at: {desktop_dir / 'FRAME.lnk'}")
    if (desktop_dir / 'FRAME.lnk').exists():
        print("  -> Verified: Desktop icon exists and is ready for double-click.")
else:
    print(f"[ERROR] Failed to create shortcut: {res.stderr}")
