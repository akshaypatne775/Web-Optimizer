@echo off
setlocal

cd /d "%~dp0"

echo ===============================================
echo   Droid Survair - Master Suite Setup
echo ===============================================
echo.

set "ENV_NAME=venv"
set "CONDA_ROOT="
set "CONDA_PATH="
set "ANACONDA_TOS_ACKNOWLEDGEMENT=yes"
set "NON_INTERACTIVE=1"

call :resolve_conda_root
if errorlevel 1 (
    echo [ERROR] Miniconda/Anaconda was not detected.
    echo [INFO] Install Miniconda, reopen terminal, and re-run installl.bat.
    echo [INFO] Download: https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

set "PATH=%CONDA_ROOT%\condabin;%CONDA_ROOT%\Scripts;%CONDA_ROOT%;%CONDA_ROOT%\Library\bin;%PATH%"
set "CONDA_PATH=%CONDA_ROOT%\condabin\conda.bat"
set "ACTIVATE_BAT=%CONDA_ROOT%\Scripts\activate.bat"

echo [INFO] Conda root detected:
echo        %CONDA_ROOT%
echo [INFO] Initializing Conda shell context...
call "%ACTIVATE_BAT%" base >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to initialize Conda with:
    echo [ERROR] Command failed: call "%ACTIVATE_BAT%" base
    pause
    exit /b 1
)
echo [INFO] Conda shell initialized successfully.
echo.

call :attempt_tos_accept

conda env list | findstr /R /C:"^[ ]*%ENV_NAME%[ ]" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Creating Conda environment "%ENV_NAME%" with Python 3.10...
    set "CREATE_LOG=%TEMP%\droid_portal_conda_create.log"
    echo [INFO] Running: call conda create -n %ENV_NAME% python=3.10 -y
    call conda create -n %ENV_NAME% python=3.10 -y >"%CREATE_LOG%" 2>&1
    if errorlevel 1 (
        findstr /I "CondaToSNonInteractiveError" "%CREATE_LOG%" >nul 2>&1
        if not errorlevel 1 (
            echo [ERROR] Conda Terms of Service must be accepted before non-interactive install.
            echo [INFO] Run these one-time commands in terminal:
            echo        conda tos accept --override-channels
            echo        conda tos accept
            echo [INFO] Then re-run installl.bat
            echo.
            echo [ERROR] Command failed: call conda create -n %ENV_NAME% python=3.10 -y
            type "%CREATE_LOG%"
            pause
            exit /b 1
        )
        echo [ERROR] Failed to create Conda environment.
        echo [ERROR] Command failed: call conda create -n %ENV_NAME% python=3.10 -y
        type "%CREATE_LOG%"
        pause
        exit /b 1
    )
) else (
    echo [INFO] Conda environment "%ENV_NAME%" already exists.
)

echo [INFO] Installing geospatial core libraries (conda-forge)...
set "INSTALL_LOG=%TEMP%\droid_portal_conda_install.log"
echo [INFO] Running: call conda install -n %ENV_NAME% -c conda-forge gdal rasterio -y
call conda install -n %ENV_NAME% -c conda-forge gdal rasterio -y >"%INSTALL_LOG%" 2>&1
if errorlevel 1 (
    findstr /I "CondaToSNonInteractiveError" "%INSTALL_LOG%" >nul 2>&1
    if not errorlevel 1 (
        echo [ERROR] Conda Terms of Service must be accepted before non-interactive install.
        echo [INFO] Run these one-time commands in terminal:
        echo        conda tos accept --override-channels
        echo        conda tos accept
        echo [INFO] Then re-run installl.bat
        echo.
        echo [ERROR] Command failed: call conda install -n %ENV_NAME% -c conda-forge gdal rasterio -y
        type "%INSTALL_LOG%"
        pause
        exit /b 1
    )
    echo [ERROR] Failed to install GDAL/Rasterio via Conda.
    echo [ERROR] Command failed: call conda install -n %ENV_NAME% -c conda-forge gdal rasterio -y
    type "%INSTALL_LOG%"
    pause
    exit /b 1
)

echo [INFO] Upgrading pip in "%ENV_NAME%"...
echo [INFO] Running: call conda run -n %ENV_NAME% python -m pip install --upgrade pip
call conda run -n %ENV_NAME% python -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip in Conda environment.
    echo [ERROR] Command failed: call conda run -n %ENV_NAME% python -m pip install --upgrade pip
    pause
    exit /b 1
)

echo [INFO] Installing remaining Python packages via pip...
echo [INFO] Running: call conda run -n %ENV_NAME% python -m pip install -r requirements.txt
call conda run -n %ENV_NAME% python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    echo [ERROR] Command failed: call conda run -n %ENV_NAME% python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Droid Survair environment is ready.
echo [INFO] Launch the tool with: run tool.bat
echo.
pause
exit /b 0

:resolve_conda_root
for %%P in (
    "C:\ProgramData\miniconda3"
    "C:\ProgramData\anaconda3"
    "%ProgramData%\miniconda3"
    "%ProgramData%\anaconda3"
    "%USERPROFILE%\miniconda3"
    "%USERPROFILE%\anaconda3"
    "%LOCALAPPDATA%\miniconda3"
    "%LOCALAPPDATA%\anaconda3"
) do (
    if exist "%%~P\Scripts\activate.bat" if exist "%%~P\condabin\conda.bat" (
        set "CONDA_ROOT=%%~P"
        goto :conda_found
    )
)

for /f "delims=" %%I in ('where conda 2^>nul') do (
    if /i "%%~nxI"=="conda.bat" (
        if exist "%%~dpI..\Scripts\activate.bat" (
            set "CONDA_ROOT=%%~dpI.."
            goto :conda_found
        )
    )
)

for /f "delims=" %%I in ('where conda.exe 2^>nul') do (
    if exist "%%~dpI..\Scripts\activate.bat" if exist "%%~dpI..\condabin\conda.bat" (
        set "CONDA_ROOT=%%~dpI.."
        goto :conda_found
    )
)

:fallback_programdata
if exist "C:\ProgramData\miniconda3\Scripts\activate.bat" if exist "C:\ProgramData\miniconda3\condabin\conda.bat" (
    set "CONDA_ROOT=C:\ProgramData\miniconda3"
    goto :conda_found
)

if exist "C:\ProgramData\anaconda3\Scripts\activate.bat" if exist "C:\ProgramData\anaconda3\condabin\conda.bat" (
    set "CONDA_ROOT=C:\ProgramData\anaconda3"
    goto :conda_found
)

for /f "delims=" %%I in ('where conda.exe 2^>nul') do (
    if exist "%%~dpI" (
        for %%R in ("%%~dpI..") do (
            if exist "%%~fR\Scripts\activate.bat" if exist "%%~fR\condabin\conda.bat" (
                set "CONDA_ROOT=%%~fR"
            )
        )
        if defined CONDA_ROOT (
            goto :conda_found
        )
    )
)

for /f "delims=" %%I in ('where conda.bat 2^>nul') do (
    if exist "%%~dpI" (
        for %%R in ("%%~dpI..") do (
            if exist "%%~fR\Scripts\activate.bat" if exist "%%~fR\condabin\conda.bat" (
                set "CONDA_ROOT=%%~fR"
            )
        )
        if defined CONDA_ROOT (
            goto :conda_found
        )
    )
)

for %%P in (
    "%ProgramData%\miniconda3\condabin\conda.bat"
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\miniconda3\condabin\conda.bat"
) do (
    if exist "%%~P" (
        for %%R in ("%%~dpP..") do set "CONDA_ROOT=%%~fR"
        if exist "%CONDA_ROOT%\Scripts\activate.bat" if exist "%CONDA_ROOT%\condabin\conda.bat" (
            goto :conda_found
        )
        set "CONDA_ROOT="
    )
)

for %%P in (
    "%ProgramData%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
) do (
    if exist "%%~P" (
        for %%R in ("%%~dpP..") do set "CONDA_ROOT=%%~fR"
        if exist "%CONDA_ROOT%\Scripts\activate.bat" if exist "%CONDA_ROOT%\condabin\conda.bat" (
            goto :conda_found
        )
        set "CONDA_ROOT="
    )
)

if exist "C:\ProgramData\miniconda3\condabin\conda.exe" if exist "C:\ProgramData\miniconda3\Scripts\activate.bat" (
    set "CONDA_ROOT=C:\ProgramData\miniconda3"
    goto :conda_found
)

for /f "delims=" %%I in ('where conda.exe 2^>nul') do (
    for %%R in ("%%~dpI..") do (
        if exist "%%~fR\Scripts\activate.bat" if exist "%%~fR\condabin\conda.bat" (
            set "CONDA_ROOT=%%~fR"
            goto :conda_found
        )
    )
)

for /f "delims=" %%I in ('where conda.bat 2^>nul') do (
    for %%R in ("%%~dpI..") do (
        if exist "%%~fR\Scripts\activate.bat" if exist "%%~fR\condabin\conda.bat" (
            set "CONDA_ROOT=%%~fR"
            goto :conda_found
        )
    )
)

for /f "delims=" %%I in ('where conda 2^>nul') do (
    if /i "%%~nxI"=="conda.exe" (
        for %%R in ("%%~dpI..") do (
            if exist "%%~fR\Scripts\activate.bat" if exist "%%~fR\condabin\conda.bat" (
                set "CONDA_ROOT=%%~fR"
                goto :conda_found
            )
        )
    ) else if /i "%%~nxI"=="conda.bat" (
        for %%R in ("%%~dpI..") do (
            if exist "%%~fR\Scripts\activate.bat" if exist "%%~fR\condabin\conda.bat" (
                set "CONDA_ROOT=%%~fR"
                goto :conda_found
            )
        )
    )
)

if exist "C:\ProgramData\miniconda3\condabin\conda.bat" (
    set "CONDA_ROOT=C:\ProgramData\miniconda3"
    if exist "%CONDA_ROOT%\Scripts\activate.bat" (
        goto :conda_found
    )
)

exit /b 1

:conda_found
exit /b 0

:attempt_tos_accept
echo [INFO] Checking Conda Terms of Service status...
call conda tos accept --override-channels --yes >nul 2>&1
if errorlevel 1 (
    call conda tos accept --yes >nul 2>&1
)
if errorlevel 1 (
    echo [WARNING] Automatic ToS acceptance could not be confirmed.
    echo [INFO] If setup fails with CondaToSNonInteractiveError, run once:
    echo        conda tos accept --override-channels
    echo        conda tos accept
    echo.
)
exit /b 0
