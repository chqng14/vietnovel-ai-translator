@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
title VietNovel AI Translator - Setup and Run

:menu
cls
echo ============================================================
echo          VIETNOVEL AI TRANSLATOR - SETUP AND RUN
echo ============================================================
echo.
echo [1] Install Google Translate mode (lightweight, no GPU)
echo [2] Install full AI mode for NVIDIA CUDA
echo [3] Run the application
echo [4] View the quick-start guide
echo [5] Exit
echo.
choice /c 12345 /n /m "Select an option [1-5]: "

if errorlevel 5 goto :end
if errorlevel 4 goto :guide
if errorlevel 3 goto :run
if errorlevel 2 goto :install_gpu
if errorlevel 1 goto :install_library

:ensure_venv
if exist ".venv\Scripts\python.exe" (
    set "APP_PYTHON=.venv\Scripts\python.exe"
    exit /b 0
)

echo.
echo Creating a Python virtual environment in .venv...
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] Could not create the Python virtual environment.
    echo Install Python from https://www.python.org/downloads/
    echo Make sure "Add Python to PATH" is enabled during installation.
    pause
    exit /b 1
)

set "APP_PYTHON=.venv\Scripts\python.exe"
exit /b 0

:install_library
call :ensure_venv
if errorlevel 1 goto :menu
echo.
echo Updating pip...
"%APP_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :install_error
echo.
echo Installing Google Translate mode...
"%APP_PYTHON%" -m pip install -r requirements-library.txt
if errorlevel 1 goto :install_error
echo.
echo [SUCCESS] Lightweight mode is ready.
echo Select option [3], then choose "Google Translate" in the web interface.
pause
goto :menu

:install_gpu
call :ensure_venv
if errorlevel 1 goto :menu
echo.
echo Updating pip...
"%APP_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :install_error
echo.
echo Installing PyTorch for CUDA 12.6...
"%APP_PYTHON%" -m pip install torch --index-url https://download.pytorch.org/whl/cu126
if errorlevel 1 goto :install_error
echo.
echo Installing the remaining dependencies...
"%APP_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :install_error
echo.
echo [SUCCESS] Full AI and Google Translate modes are ready.
pause
goto :menu

:run
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo The application is not installed. Select option [1] or [2] first.
    pause
    goto :menu
)
set "DEFAULT_TRANSLATION_PROVIDER="
".venv\Scripts\python.exe" -c "import torch, transformers" >nul 2>nul
if errorlevel 1 (
    set "DEFAULT_TRANSLATION_PROVIDER=deep-translator/google"
    echo.
    echo Local AI dependencies were not found.
    echo Google Translate will be selected as the default engine.
)
echo.
echo The application is running at http://localhost:8000
echo Press Ctrl+C to stop the server and return to this menu.
echo.
start "" "http://localhost:8000"
".venv\Scripts\python.exe" app.py
pause
goto :menu

:guide
cls
echo ============================================================
echo                      QUICK-START GUIDE
echo ============================================================
echo.
echo 1. Select [1] for Google Translate without an NVIDIA GPU.
echo 2. Select [2] for local AI models with an NVIDIA GPU.
echo 3. Select [3] to open the app at http://localhost:8000.
echo 4. Paste a novel chapter URL or enter text directly.
echo 5. Select a translation engine:
echo    - Google Translate: requires Internet, does not require a GPU.
echo    - NiuTrans/DeepSeek: runs locally, downloads a model, and prefers a GPU.
echo 6. Start translating, monitor progress, then export TXT, Markdown, or EPUB.
echo.
echo Note: do not open static/index.html with Live Server.
echo Always start the application with option [3] in this menu.
echo.
pause
goto :menu

:install_error
echo.
echo [ERROR] Installation failed. Check your Internet connection and Python version.
pause
goto :menu

:end
endlocal
