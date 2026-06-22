@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
:: ============================================================
:: 直播-点菜 SKU 巡检 - Web GUI 启动脚本 (Windows)
:: ============================================================

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%" || exit /b 1

set "LOG_DIR=%SCRIPT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\web.log"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

:: 检查是否是打包版本
if exist "%SCRIPT_DIR%\SKU-Price-Audit-Web.exe" (
    start "SKU测价服务" /min cmd /c ""%SCRIPT_DIR%\SKU-Price-Audit-Web.exe" > "%LOG_FILE%" 2>&1"
    goto :wait_for_server
)

:: 检查是否是源码版本
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto :source_mode
)

python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python3"
    goto :source_mode
)

echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
pause
exit /b 1

:source_mode
echo 🔍 使用 Python: %PYTHON_CMD%
echo 🔍 检查依赖...
%PYTHON_CMD% -c "import flask, openpyxl, playwright, PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  依赖缺失，正在安装 requirements.txt...
    %PYTHON_CMD% -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ❌ 依赖安装失败，请查看网络或 Python 环境
        pause
        exit /b 1
    )
)

echo 🔍 检查 Playwright Chromium...
%PYTHON_CMD% -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  Chromium 未安装，正在安装...
    %PYTHON_CMD% -m playwright install chromium
    if %errorlevel% neq 0 (
        echo ❌ Chromium 安装失败，请手动运行: %PYTHON_CMD% -m playwright install chromium
        pause
        exit /b 1
    )
)

start "SKU测价服务" /min cmd /c ""%PYTHON_CMD%" "%SCRIPT_DIR%\app.py" > "%LOG_FILE%" 2>&1"
goto :wait_for_server

:wait_for_server
echo 🚀 正在启动服务...
echo 📝 启动日志: %LOG_FILE%

:: 等待服务启动（最多 15 秒）
set /a count=0
:check_loop
timeout /t 1 /nobreak >nul 2>&1
set /a count+=1
if %count% geq 15 goto :timeout

:: 检查服务是否启动
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8080' -TimeoutSec 3 -UseBasicParsing; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 goto :check_loop

:: 服务已启动，打开浏览器
echo ✅ 服务已启动，正在打开浏览器...
start http://127.0.0.1:8080

:: 创建关闭快捷方式
if not exist "%SCRIPT_DIR%\关闭服务.bat" (
    (
        echo @echo off
        echo echo 🛑 正在关闭服务...
        echo powershell -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8080/api/shutdown' -Method POST -TimeoutSec 3 ^| Out-Null } catch {}"
        echo echo ✅ 服务已关闭
        echo timeout /t 2 /nobreak ^>nul
    ) > "%SCRIPT_DIR%\关闭服务.bat"
    echo ✅ 已创建关闭服务快捷方式
)

exit /b 0

:timeout
echo ⚠️ 服务启动超时，请手动访问 http://127.0.0.1:8080
echo 如果仍无法访问，请打开日志文件查看原因:
echo %LOG_FILE%
pause
exit /b 1
