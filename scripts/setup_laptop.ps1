# Windows Laptop Automated Environment Setup Script
# Configures Python virtual environment and checks NVIDIA GPU/CUDA availability.

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "         KARP ADAS — Laptop Environment Setup             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check Python installation
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERROR] Python is not installed or not in system PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10-3.12 (64-bit) from python.org." -ForegroundColor Yellow
    Exit 1
}

$pyVersion = & python --version
Write-Host "[INFO] Detected Python: $pyVersion" -ForegroundColor Green

# 2. Check NVIDIA GPU and CUDA
Write-Host "[INFO] Checking for NVIDIA GPU..." -ForegroundColor Cyan
$gpuInfo = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
if ($gpuInfo) {
    Write-Host "[SUCCESS] Found NVIDIA GPU: $($gpuInfo.Name)" -ForegroundColor Green
} else {
    Write-Host "[WARNING] No NVIDIA GPU detected via WMI or using integrated graphics." -ForegroundColor Yellow
    Write-Host "CPU fallback execution will be enabled automatically." -ForegroundColor Yellow
}

# 3. Create Virtual Environment
$venvPath = ".env_laptop"
if (-not (Test-Path $venvPath)) {
    Write-Host "[INFO] Creating virtual environment in $venvPath..." -ForegroundColor Cyan
    & python -m venv $venvPath
} else {
    Write-Host "[INFO] Virtual environment $venvPath already exists." -ForegroundColor Green
}

# 4. Activate and Upgrade Pip
$pipExe = "$venvPath\Scripts\pip.exe"
$pyVenvExe = "$venvPath\Scripts\python.exe"

Write-Host "[INFO] Upgrading pip, setuptools, wheel..." -ForegroundColor Cyan
& $pipExe install --upgrade pip setuptools wheel

# 5. Install PyTorch with CUDA if NVIDIA GPU is present
Write-Host "[INFO] Installing PyTorch with CUDA 12.1 support..." -ForegroundColor Cyan
& $pipExe install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 6. Install Laptop Vision Requirements
Write-Host "[INFO] Installing KARP Laptop dependencies..." -ForegroundColor Cyan
& $pipExe install -r laptop_vision\requirements.txt

# 7. Verification Test
Write-Host "`n[INFO] Verifying environment & CUDA acceleration..." -ForegroundColor Cyan
& $pyVenvExe -c "import torch; print('PyTorch Version:', torch.__version__); print('CUDA Available:', torch.cuda.is_available()); print('Device Name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU Fallback')"

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "         Setup Complete! Launch with scripts\run_laptop.bat " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
