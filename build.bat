@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem ===== 找 Python =====
set "PYTHON_CMD="
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo 找不到 Python 3，請先安裝後再執行本檔。
    pause
    exit /b 1
)

rem ===== 安裝執行期依賴 + 建置工具 =====
echo 安裝 / 確認依賴中...
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 ( echo 安裝 requirements.txt 失敗。 & pause & exit /b 1 )
%PYTHON_CMD% -m pip install --upgrade pyinstaller
if errorlevel 1 ( echo 安裝 pyinstaller 失敗。 & pause & exit /b 1 )

rem ===== 建置單一 exe（icon 內嵌、保留主控台視窗方便看 log / 按 Ctrl+C 停止）=====
rem --add-data "來源;exe內路徑"：把整個 icon 資料夾打包進 exe，發佈時免帶 icon。
echo 開始建置 DailyWork.exe ...
%PYTHON_CMD% -m PyInstaller --noconfirm --onefile --console --name DailyWork --add-data "icon;icon" DailyWork.py
if errorlevel 1 ( echo 建置失敗。 & pause & exit /b 1 )

echo.
echo === 完成 ===
echo 發佈內容（單一檔，icon 已內嵌）：
echo   dist\DailyWork.exe
echo 直接把這一個 exe 交給對方，雙擊即可，不需另外附 icon 資料夾。
echo.
pause
