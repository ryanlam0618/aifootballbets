@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo  Od dsHarvester 批量爬蟲 - 首次運行設置
echo ========================================
echo.

REM 獲取腳本所在目錄
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM 檢查 Python 是否安裝
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 未找到 Python，請先安裝 Python 3.12+
    echo 下載地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 檢查是否有 OddsHarvester 文件夾
if not exist "OddsHarvester" (
    echo [錯誤] 未找到 OddsHarvester 文件夾
    echo 請確保 OddsHarvester 文件夾在同目錄下
    pause
    exit /b 1
)

REM 設置路徑
set "ODDS_HARVESTER=%SCRIPT_DIR%OddsHarvester"
set "VENV_PATH=%ODDS_HARVESTER%\.venv"

REM 創建虛擬環境（如果不存在）
if not exist "%VENV_PATH%\Scripts\python.exe" (
    echo [INFO] 創建虛擬環境...
    python -m venv "%VENV_PATH%"
    if errorlevel 1 (
        echo [錯誤] 創建虛擬環境失敗
        pause
        exit /b 1
    )
)

REM 安裝依賴
echo [INFO] 安裝依賴...
call "%VENV_PATH%\Scripts\pip.exe" install --upgrade pip
call "%VENV_PATH%\Scripts\pip.exe" install beautifulsoup4 boto3 lxml playwright pytz

REM 安裝 Playwright 瀏覽器
echo [INFO] 安裝 Playwright 瀏覽器...
call "%VENV_PATH%\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
    echo [警告] Playwright 瀏覽器安裝失敗，嘗試使用現有瀏覽器...
)

echo.
echo ========================================
echo  設置完成！
echo ========================================
echo.
echo 使用方法:
echo   python odds_batch_scraper.py --all
echo   python odds_batch_scraper.py --league england-premier-league --season 2024-2025
echo.
pause
