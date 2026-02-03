@echo off
chcp 65001 >nul
echo ============================================
echo   AI Football Analysis System - Web Interface
echo ============================================
echo.
echo Starting Streamlit...
echo.
cd /d "%~dp0"
python -m streamlit run app_streamlit.py
echo.
echo Streamlit has been closed.
pause
