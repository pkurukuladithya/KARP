@echo off
REM Launch Laptop AI Perception Service
setlocal
cd /d "%~dp0\.."

if exist .env_laptop\Scripts\python.exe (
    set "PYTHON_EXE=.env_laptop\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [INFO] Starting KARP Laptop Vision Engine...
"%PYTHON_EXE%" laptop_vision\main.py %*
pause
