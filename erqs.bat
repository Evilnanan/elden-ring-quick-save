@echo off
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Please install Python and add it to PATH.
    pause
    exit /b 1
)

python -c "import keyboard" >nul 2>&1
if %errorlevel% neq 0 (
    echo keyboard library not found. Please run:
    echo   pip install keyboard
    pause
    exit /b 1
)

start "" pythonw "%~dp0main.py"
