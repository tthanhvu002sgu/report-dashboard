@echo off
title MT5 Quantitative Strategy Analyzer
echo ==========================================================
echo 🚀 DONG BO & KHOI DONG HE THONG PHAN TICH CHIEN LUOC MT5
echo ==========================================================
echo.

:: Kiem tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python chua duoc cai dat hoac chua duoc them vao Path!
    echo Vui long tai va cai dat Python tai: https://www.python.org/
    pause
    exit /b
)

echo [+] Dang cai dat/cap nhat cac thu vien can thiet...
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo [WARNING] Co loi xay ra khi cai dat thu vien. Dang thu chay thiet lap don gian...
    python -m pip install fastapi uvicorn pandas openpyxl jinja2
)

echo.
echo [+] Dang khoi chay may chu Dashboard...
echo [INFO] Ban co the truy cap Dashboard tai: http://localhost:8000
echo [INFO] Hoac su dung IP cua VPS tu thiet bi khac: http://[VPS_IP]:8000
echo.
echo Nhap Ctrl+C trong cua so nay de tat may chu.
echo ==========================================================
python app.py
pause
