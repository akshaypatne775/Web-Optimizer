@echo off
setlocal

cd /d "%~dp0"

echo ===============================================
echo   Droid Survair - Web Optimizer Setup
echo ===============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv. Ensure Python is installed and on PATH.
        pause
        exit /b 1
    )
)

echo [INFO] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
)

echo [INFO] Installing required packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Setup complete.
echo You can now run: run tool.bat
echo.
pause
exit /b 0
