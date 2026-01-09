@echo off
setlocal

:: Configuration
set "PY_VER=3.11.9"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-embed-amd64.zip"
set "BASE_DIR=%~dp0"
set "RUNTIME_DIR=%BASE_DIR%runtime\python"
set "ZIP_FILE=%BASE_DIR%python_embed.zip"
set "PYTHON_EXE=%RUNTIME_DIR%\python.exe"

:: 1. Check if Python is installed
if exist "%PYTHON_EXE%" goto :Launch

:: 2. If not installed, install it
echo [INFO] Portable Python environment not found. Initializing...

if not exist "%BASE_DIR%runtime" mkdir "%BASE_DIR%runtime"
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

echo [INFO] Downloading Python %PY_VER%...
curl -L -o "%ZIP_FILE%" "%PY_URL%"
if %errorlevel% neq 0 (
    echo [ERROR] Download failed. Please check your internet connection.
    pause
    exit /b 1
)

echo [INFO] Extracting files...
tar -xf "%ZIP_FILE%" -C "%RUNTIME_DIR%"
if %errorlevel% neq 0 (
    echo [ERROR] Usage of 'tar' failed. Trying PowerShell...
    powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%RUNTIME_DIR%' -Force"
)

if exist "%ZIP_FILE%" del "%ZIP_FILE%"

echo [INFO] Configuring environment...
:: Create ._pth file to include project root and libs folder
(
echo python311.zip
echo .
echo ../../
echo ../../libs
echo import site
) > "%RUNTIME_DIR%\python311._pth"

echo [INFO] Environment ready.

:Launch
:: 3. Launch application
echo [INFO] Starting StreamCap...
"%PYTHON_EXE%" "%BASE_DIR%main.py" %*

if %errorlevel% neq 0 (
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
