@echo off
chcp 65001 >nul
title Geo Photo Locator
echo ====================================================
echo   Запуск Geo Photo Locator...
echo ====================================================
echo.

:: 1. Перевірка наявності Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ПОМИЛКА] Python не встановлено! Завантажте його з python.org
    pause
    exit /b
)

:: 2. Створення віртуального середовища, якщо його немає
if not exist venv (
    echo [1/4] Створення віртуального середовища...
    python -m venv venv
)

:: 3. Активація venv та встановлення залежностей
echo [2/4] Встановлення бібліотек...
call venv\Scripts\activate.bat
pip install -r requirements.txt >nul 2>&1

:: 4. Запуск скрипта підготовки (завантаження geo-sleuth)
echo [3/4] Перевірка інструментів geo-sleuth...
python setup_env.py

:: 5. Запуск сервера
echo [4/4] Запуск веб-сервера...
echo.
echo Сервер доступний за адресою: http://127.0.0.1:5000
echo Щоб зупинити, натисніть Ctrl+C
echo.
python app.py
pause