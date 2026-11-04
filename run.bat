@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo 먼저 install.bat 을 실행하세요.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "app.py"
echo 실행했습니다. 트레이에 대기하며, F12 를 누를 때만 캡처가 시작됩니다.
timeout /t 2 >nul
