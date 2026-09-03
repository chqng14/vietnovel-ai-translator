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
echo [1] Install or repair Google Translate mode (no GPU)
echo [2] Install AI dependencies and download models
echo [3] Run the application
echo [4] View the quick-start guide
echo [5] Uninstall models or dependencies
echo [6] Exit
echo.
choice /c 123456 /n /m "Select an option [1-6]: "

if errorlevel 6 goto :end
if errorlevel 5 goto :uninstall_menu
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
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import deep_translator,fastapi,uvicorn,sse_starlette,aiofiles,bs4,requests,lxml,cssselect,ebooklib,multipart,pydantic" >nul 2>nul
    if not errorlevel 1 (
        echo.
        echo [READY] Google Translate mode is already installed in .venv.
        echo Select option [3] to run the application.
        pause
        goto :menu
    )
)
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
"%APP_PYTHON%" -c "import torch,transformers,accelerate,deep_translator,fastapi,uvicorn,sse_starlette,aiofiles,bs4,requests,lxml,cssselect,ebooklib,multipart,pydantic" >nul 2>nul
if errorlevel 1 goto :install_ai_dependencies
echo.
echo [READY] AI dependencies are already installed in .venv.
goto :model_menu

:install_ai_dependencies
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
echo [SUCCESS] AI dependencies are ready.

:model_menu
cls
echo ============================================================
echo                    DOWNLOAD AN AI MODEL
echo ============================================================
echo.
echo [1] Qwen3-0.6B - lightweight, about 1.4 GB (default)
echo [2] NiuTrans LMT-60-1.7B - better translation quality
echo [3] Back to main menu
echo.
echo Downloaded models are kept in the Hugging Face cache.
echo You can download multiple models and choose between them in the app.
echo Qwen3-0.6B remains the default whenever it is installed.
echo.
choice /c 123 /n /m "Select a model [1-3]: "
if errorlevel 3 goto :menu
if errorlevel 2 goto :select_niutrans
if errorlevel 1 goto :select_qwen

:select_qwen
set "SELECTED_MODEL=Qwen/Qwen3-0.6B"
set "SELECTED_MODEL_LABEL=Qwen3-0.6B"
goto :download_model

:select_niutrans
set "SELECTED_MODEL=NiuTrans/LMT-60-1.7B"
set "SELECTED_MODEL_LABEL=NiuTrans LMT-60-1.7B"
goto :download_model

:download_model
echo.
echo Downloading %SELECTED_MODEL_LABEL%...
echo Existing files in the cache will be reused.
"%APP_PYTHON%" -c "from huggingface_hub import snapshot_download; snapshot_download('%SELECTED_MODEL%')"
if errorlevel 1 goto :model_download_error
if exist ".venv\default_provider.txt" del /q ".venv\default_provider.txt"
echo.
echo [SUCCESS] %SELECTED_MODEL_LABEL% is downloaded.
echo Qwen3-0.6B is the default whenever it is available.
echo Download another model here, or select [4] to return to the main menu.
pause
goto :model_menu

:model_download_error
echo.
echo [ERROR] Model download failed. Existing cached files were kept.
echo Check the Internet connection and available disk space.
pause
goto :model_menu

:uninstall_menu
cls
echo ============================================================
echo                  UNINSTALL AND FREE SPACE
echo ============================================================
echo.
echo [1] Remove Qwen3-0.6B model cache
echo [2] Remove NiuTrans LMT-60-1.7B model cache
echo [3] Uninstall AI Python packages (keep model caches)
echo [4] Uninstall deep-translator (keep the web application)
echo [5] Remove the entire .venv (keep model caches)
echo [6] Back to main menu
echo.
choice /c 123456 /n /m "Select an option [1-6]: "
if errorlevel 6 goto :menu
if errorlevel 5 goto :remove_venv
if errorlevel 4 goto :remove_deep_translator
if errorlevel 3 goto :remove_ai_packages
if errorlevel 2 goto :remove_niutrans
if errorlevel 1 goto :remove_qwen

:remove_qwen
set "SELECTED_MODEL=Qwen/Qwen3-0.6B"
set "SELECTED_MODEL_LABEL=Qwen3-0.6B"
goto :remove_model_cache

:remove_niutrans
set "SELECTED_MODEL=NiuTrans/LMT-60-1.7B"
set "SELECTED_MODEL_LABEL=NiuTrans LMT-60-1.7B"
goto :remove_model_cache

:remove_model_cache
call :ensure_venv
if errorlevel 1 goto :uninstall_menu
echo.
echo This removes the cached files for %SELECTED_MODEL_LABEL%.
choice /c YN /n /m "Continue [Y/N]? "
if errorlevel 2 goto :uninstall_menu
"%APP_PYTHON%" -c "import os,shutil; from pathlib import Path; model='%SELECTED_MODEL%'; base=Path(os.environ.get('HF_HOME',str(Path.home()/'.cache'/'huggingface'))); root=Path(os.environ.get('HF_HUB_CACHE') or os.environ.get('HUGGINGFACE_HUB_CACHE') or base/'hub'); target=root/('models--'+model.replace('/','--')); print('Removing:',target) if target.exists() else print('Model cache was not found:',target); shutil.rmtree(target) if target.exists() else None"
if errorlevel 1 goto :uninstall_error
if exist ".venv\default_provider.txt" del /q ".venv\default_provider.txt"
echo [SUCCESS] Model cache removal completed.
pause
goto :uninstall_menu

:remove_ai_packages
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [READY] The project virtual environment does not exist.
    pause
    goto :uninstall_menu
)
echo.
echo This removes PyTorch, Transformers, Accelerate and related AI packages.
echo Downloaded model caches will be kept.
choice /c YN /n /m "Continue [Y/N]? "
if errorlevel 2 goto :uninstall_menu
".venv\Scripts\python.exe" -m pip uninstall -y torch torchvision torchaudio transformers accelerate bitsandbytes tokenizers safetensors huggingface-hub
if exist ".venv\default_provider.txt" del /q ".venv\default_provider.txt"
echo.
echo [SUCCESS] AI Python packages were removed.
pause
goto :uninstall_menu

:remove_deep_translator
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [READY] The project virtual environment does not exist.
    pause
    goto :uninstall_menu
)
echo.
choice /c YN /n /m "Uninstall deep-translator [Y/N]? "
if errorlevel 2 goto :uninstall_menu
".venv\Scripts\python.exe" -m pip uninstall -y deep-translator
echo.
echo [SUCCESS] deep-translator was removed.
pause
goto :uninstall_menu

:remove_venv
if not exist ".venv" (
    echo.
    echo [READY] The .venv directory does not exist.
    pause
    goto :uninstall_menu
)
echo.
echo This removes every Python package installed for this project.
echo Hugging Face model caches are not removed by this option.
choice /c YN /n /m "Remove .venv [Y/N]? "
if errorlevel 2 goto :uninstall_menu
rmdir /s /q ".venv"
if exist ".venv" goto :uninstall_error
echo.
echo [SUCCESS] The project virtual environment was removed.
pause
goto :uninstall_menu

:uninstall_error
echo.
echo [ERROR] Uninstall did not complete. Close the running application and retry.
pause
goto :uninstall_menu

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
echo 2. Select [2], choose an AI model, and wait for its download to finish.
echo 3. Select [3] to open the app at http://localhost:8000.
echo 4. Paste a novel chapter URL or enter text directly.
echo 5. Select a translation engine:
echo    - Google Translate: requires Internet, does not require a GPU.
echo    - Qwen3/NiuTrans: runs locally and prefers an NVIDIA GPU.
echo    - If multiple models are downloaded, choose one from the web dropdown.
echo 6. Start translating, monitor progress, then export TXT, Markdown, or EPUB.
echo 7. Select [5] from the main menu to remove models or dependencies.
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
