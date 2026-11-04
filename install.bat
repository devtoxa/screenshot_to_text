@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo  Screenshot to Text  설치
echo ============================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

%PY% -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 을 찾을 수 없습니다.
    echo         python.org 에서 Python 3.10 이상을 설치하고
    echo         "Add python.exe to PATH" 를 체크하세요.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] 가상환경을 만드는 중...
    %PY% -m venv .venv
    if errorlevel 1 goto :error
) else (
    echo [1/4] 기존 가상환경을 사용합니다.
)

echo [2/4] 필요한 패키지를 설치하는 중... (처음에는 몇 분 걸립니다)
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [3/4] 한국어 인식 모델을 준비하는 중...
".venv\Scripts\python.exe" "tools\fetch_models.py"

echo [4/4] 설정 파일을 준비하는 중...
".venv\Scripts\python.exe" -c "from stc import config; config.load()"
if errorlevel 1 goto :error

echo.
echo ============================================
echo  설치 완료!
echo.
echo  run.bat 을 실행하면 트레이에 대기합니다.
echo  F12 를 누를 때만 캡처가 시작됩니다.
echo ============================================
echo.
pause
exit /b 0

:error
echo.
echo [ERROR] 설치 중 문제가 발생했습니다. 위 메시지를 확인하세요.
echo.
pause
exit /b 1
