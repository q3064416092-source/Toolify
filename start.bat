@echo off
chcp 65001 >nul
title Toolify Server

echo ========================================
echo   Toolify - Function Calling Middleware
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo [INFO] Python detected
python --version
echo.

REM Check if config.yaml exists
if not exist "config.yaml" (
    echo [WARNING] config.yaml not found
    echo [INFO] Creating config.yaml from config.example.yaml...
    if exist "config.example.yaml" (
        copy "config.example.yaml" "config.yaml" >nul
        echo [SUCCESS] config.yaml created
        echo [ACTION] Please edit config.yaml with your API keys and settings
        echo.
        pause
        notepad config.yaml
        echo.
        echo [INFO] After saving config.yaml, press any key to start server...
        pause >nul
    ) else (
        echo [ERROR] config.example.yaml not found
        pause
        exit /b 1
    )
)

echo [INFO] Configuration file found
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo [INFO] Virtual environment not found, creating...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created
    echo.
)

REM Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)

REM Check if dependencies are installed
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
    echo [SUCCESS] Dependencies installed
    echo.
)

echo [INFO] Starting Toolify server...
echo [INFO] Admin interface: http://localhost:8000/admin
echo [INFO] API endpoint: http://localhost:8000/v1
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

REM Start the server
python main.py

REM If server exits
echo.
echo [INFO] Server stopped
pause
