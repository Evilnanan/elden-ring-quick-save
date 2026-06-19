@echo off
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Please install Python and add it to PATH.
    pause
    exit /b 1
)

start "" python "%~dp0main.py"
