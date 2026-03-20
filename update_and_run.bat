@echo off
setlocal EnableExtensions

chcp 65001 >nul
title CULT_BOT update and run

set "SCRIPT_DIR=%~dp0"
set "PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"
cd /d "%SCRIPT_DIR%"

echo ================================
echo Updating CULT_BOT from GitHub
echo ================================
echo.

if not exist ".git" (
    echo [ERROR] Git repository was not found in this folder.
    pause
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git was not found in PATH.
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
            echo [ERROR] Python 3 was not found. Install Python or create a venv.
            pause
            exit /b 1
        )
        set "PYTHON_CMD=python"
    )
)

git pull --ff-only origin main
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to update files from GitHub.
    echo Check local changes, the active branch, and origin/main availability.
    pause
    exit /b 1
)

call %PYTHON_CMD% -m pip install --upgrade pip -i %PIP_MIRROR%
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
)

call %PYTHON_CMD% -m pip install -r requirements.txt -i %PIP_MIRROR%
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

call %PYTHON_CMD% bot.py
set "BOT_EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%BOT_EXIT_CODE%"=="0" (
    echo [ERROR] bot.py exited with code %BOT_EXIT_CODE%.
) else (
    echo [OK] bot.py exited successfully.
)

pause
exit /b %BOT_EXIT_CODE%
