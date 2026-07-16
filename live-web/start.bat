@echo off
setlocal
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

cd /d "%~dp0"
set PYTHON_CMD=python

%PYTHON_CMD% -c "import flask, openpyxl, playwright" >nul 2>&1
if errorlevel 1 (
  echo 缺少依赖，请先安装：%PYTHON_CMD% -m pip install -r requirements.txt
  pause
  exit /b 1
)

set "LOG_DIR=%~dp0runtime\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "LOG_DATE=%%i"
set "LOG_FILE=%LOG_DIR%\live-web-%LOG_DATE%.log"

echo 直播本地工具启动中：http://127.0.0.1:8080
echo 服务日志：%LOG_FILE%
start "" "http://127.0.0.1:8080"
%PYTHON_CMD% app.py >> "%LOG_FILE%" 2>&1
