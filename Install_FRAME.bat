@echo off
title "FLOWDEV FRAME // Enterprise Installer and Setup"
color 0A
cls

echo ===================================================================
echo     FLOWDEV FRAME - QUANTITATIVE DESKTOP TERMINAL INSTALLER
echo ===================================================================
echo.
echo [1/4] Checking Python Virtual Environment...
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at %~dp0.venv!
    echo Please ensure Python virtual environment is installed.
    pause
    exit /b 1
)
echo [OK] Virtual environment verified.

echo.
echo [2/4] Generating High-Resolution Application Icon...
"%~dp0.venv\Scripts\python.exe" "%~dp0assets\generate_icon.py"

echo.
echo [3/4] Packaging Native Desktop Executable (FRAME.exe)...
set CSC_EXE=%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC_EXE%" set CSC_EXE=%SystemRoot%\Microsoft.NET\Framework\v4.0.30319\csc.exe

if exist "%CSC_EXE%" (
    echo Compiling native GUI executable FRAME.exe...
    "%CSC_EXE%" /nologo /target:winexe /win32icon:"%~dp0assets\frame_icon.ico" /reference:System.Windows.Forms.dll /out:"%~dp0FRAME.exe" "%~dp0src\frame_launcher.cs"
    if exist "%~dp0FRAME.exe" (
        echo [OK] FRAME.exe successfully compiled.
    ) else (
        echo [WARN] Compilation failed, falling back to Python script launcher.
    )
) else (
    echo [INFO] Microsoft .NET compiler not found, using Python launcher.
)

echo.
echo [4/4] Creating Windows Desktop & Start Menu Shortcuts...
"%~dp0.venv\Scripts\python.exe" "%~dp0create_desktop_shortcut.py"

echo.
echo ===================================================================
echo   [INSTALL COMPLETED] FLOWDEV FRAME IS READY!
echo   Double-click the 'FRAME' icon on your Desktop to launch.
echo ===================================================================
echo.
pause
