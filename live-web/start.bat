@echo off
setlocal

cd /d "%~dp0"
set PYTHON_CMD=python

%PYTHON_CMD% -c "import flask, openpyxl" >nul 2>&1
if errorlevel 1 (
  echo 缺少依赖，请先安装：%PYTHON_CMD% -m pip install -r requirements.txt
  pause
  exit /b 1
)

start "" "http://127.0.0.1:8080"
%PYTHON_CMD% app.py
