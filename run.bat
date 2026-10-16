@echo off
chcp 65001 >nul
title Bot Telegram Chung Khoan

:: Chuyen den thu muc chua file bat
cd /d "%~dp0"

echo ===================================================
echo     DANG KHOI CHAY BOT TELEGRAM CHUNG KHOAN...
echo ===================================================

:: Kiem tra neu ton tai moi truong ao .venv
if exist ".venv\Scripts\python.exe" (
    echo [OK] Phat hien moi truong ao .venv. Dang chay bot...
    echo ---------------------------------------------------
    ".venv\Scripts\python.exe" run.py
    goto end
)

:: Kiem tra neu ton tai moi truong ao venv
if exist "venv\Scripts\python.exe" (
    echo [OK] Phat hien moi truong ao venv. Dang chay bot...
    echo ---------------------------------------------------
    "venv\Scripts\python.exe" run.py
    goto end
)

:: Neu khong co venv, thu chay bang python he thong
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] Dang chay bang Python he thong...
    echo ---------------------------------------------------
    python run.py
    goto end
)

echo [LOI] Khong tim thay Python tren may tinh cua ban!
echo Vui long cai dat Python 3.10+ tu https://www.python.org/downloads/
echo Luu y tich chon "Add python.exe to PATH" khi cai dat.

:end
echo.
echo ===================================================
echo Chuong trinh da dung lai.
pause
