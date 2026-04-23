@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [WARNING] Virtual environment not found.
    echo Please run installl.bat first.
    echo.
    pause
    exit /b 1
)

if not exist "web_optimizer_tool.py" (
    echo [ERROR] web_optimizer_tool.py not found in this folder.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "web_optimizer_tool.py"
set EXIT_CODE=%ERRORLEVEL%

echo.
if "%EXIT_CODE%"=="0" (
    echo [INFO] Tool exited normally.
) else (
    echo [ERROR] Tool exited with code %EXIT_CODE%.
)
echo.
pause
exit /b %EXIT_CODE%
