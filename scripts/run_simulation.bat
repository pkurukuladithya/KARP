@echo off
REM Launch complete KARP demonstration in simulation mode on Windows
setlocal
cd /d "%~dp0\.."

echo [INFO] Starting KARP Simulation Environment...
python scripts\run_simulation.py %*
pause
