@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_CMD="

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo Python was not found.
    echo Please install Python 3 and run this file again.
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import cv2, numpy, mss, pyautogui" >nul 2>nul
if errorlevel 1 (
    echo Required Python packages are missing.
    echo Run this command first:
    echo.
    echo %PYTHON_CMD% -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if /I "%~1"=="--check" (
    echo Startup check passed.
    exit /b 0
)

echo Starting DailyWork.py
echo Press Ctrl+C in this window to stop.
echo.

%PYTHON_CMD% "%~dp0DailyWork.py"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo DailyWork.py exited with error code %EXIT_CODE%.
    echo.
    pause
)

exit /b %EXIT_CODE%
