@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_CMD="
set "PYTHONW_CMD="

rem PYTHONW_CMD runs the GUI without a console window.
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    set "PYTHONW_CMD=pyw -3"
) else (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
        set "PYTHONW_CMD=pythonw"
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

rem Start the GUI detached; this console window closes right away.
start "" %PYTHONW_CMD% "%~dp0DailyWork.py"
if errorlevel 1 (
    echo Failed to start DailyWork.py with %PYTHONW_CMD%.
    echo.
    pause
    exit /b 1
)

exit /b 0
