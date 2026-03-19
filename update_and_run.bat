@echo off
setlocal

chcp 65001 >nul
title CULT_BOT update and run

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ================================
echo Обновление CULT_BOT из GitHub
echo ================================
echo.

if not exist ".git" (
    echo [ОШИБКА] В этой папке нет git-репозитория.
    pause
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Git не найден в PATH.
    pause
    exit /b 1
)

if exist "venv\Scripts\python.exe" (
    set "PYTHON_CMD=venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo [ОШИБКА] Python не найден. Установи Python 3 или создай venv.
            pause
            exit /b 1
        )
        set "PYTHON_CMD=python"
    )
)

git pull --ff-only origin main
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось обновить файлы из GitHub.
    echo Проверь наличие локальных изменений, активную ветку и доступ к origin/main.
    pause
    exit /b 1
)

%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось обновить pip.
    pause
    exit /b 1
)

%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Не удалось установить зависимости.
    pause
    exit /b 1
)

%PYTHON_CMD% bot.py
set "BOT_EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%BOT_EXIT_CODE%"=="0" (
    echo [ОШИБКА] bot.py завершился с кодом %BOT_EXIT_CODE%.
) else (
    echo [OK] bot.py завершился без ошибок.
)

pause
exit /b %BOT_EXIT_CODE%
