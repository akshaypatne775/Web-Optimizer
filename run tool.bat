@echo off
setlocal

cd /d "%~dp0"

set "ENV_NAME=venv"
set "CONDA_BAT="

call :resolve_conda
if errorlevel 1 (
    echo [ERROR] Miniconda/Anaconda was not detected.
    echo [INFO] Run installl.bat after installing Miniconda.
    echo.
    pause
    exit /b 1
)

call "%CONDA_BAT%" run -n %ENV_NAME% python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Conda environment "%ENV_NAME%" not found.
    echo [INFO] Please run installl.bat first.
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

call "%CONDA_BAT%" activate %ENV_NAME%
if errorlevel 1 (
    echo [ERROR] Failed to activate Conda environment "%ENV_NAME%".
    echo.
    pause
    exit /b 1
)

python "web_optimizer_tool.py"
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

:resolve_conda
for %%P in (
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%ProgramData%\miniconda3\condabin\conda.bat"
    "%ProgramData%\anaconda3\condabin\conda.bat"
) do (
    if exist %%~P (
        set "CONDA_BAT=%%~P"
        goto :conda_found
    )
)

for /f "delims=" %%I in ('where conda 2^>nul') do (
    if /i "%%~nxI"=="conda.bat" (
        set "CONDA_BAT=%%~fI"
        goto :conda_found
    )
)

for /f "delims=" %%I in ('where conda.exe 2^>nul') do (
    if exist "%%~dpI..\condabin\conda.bat" (
        set "CONDA_BAT=%%~dpI..\condabin\conda.bat"
        goto :conda_found
    )
)

exit /b 1

:conda_found
exit /b 0
