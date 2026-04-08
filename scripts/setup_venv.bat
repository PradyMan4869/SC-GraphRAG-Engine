@echo off
REM ============================================================
REM  Setup script for GraphRAG - Indian Supreme Court Judgments
REM  Run from the project root: scripts\setup_venv.bat
REM  Requires: Python 3.13, CUDA 12.8+
REM ============================================================

cd /d "%~dp0.."

echo [1/4] Creating virtual environment with Python 3.13...
py -3.13 -m venv venv
call venv\Scripts\activate

echo [2/4] Upgrading pip...
python -m pip install --upgrade pip

echo [3/4] Installing PyTorch with CUDA 12.8 (Blackwell/RTX 5050 support)...
pip install "torch==2.11.0+cu128" --index-url https://download.pytorch.org/whl/cu128

echo [4/4] Installing remaining dependencies...
pip install -r requirements.txt

echo.
echo Setup complete! Activate with: venv\Scripts\activate
echo Verify GPU:
echo   python -c "import torch; print(torch.cuda.get_device_name(0))"
echo.
echo LLM Backend: Open LM Studio, load Qwen3-VL-8B-Instruct-Q4_K_M, start server on port 1234.
