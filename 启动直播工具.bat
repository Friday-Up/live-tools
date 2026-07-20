@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%" || exit /b 1

set "LOG_DIR=%SCRIPT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\web.log"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

set "UPDATE_TRANSACTION=%SCRIPT_DIR%runtime\update-transaction.json"
if exist "%UPDATE_TRANSACTION%" (
    if not exist "%SCRIPT_DIR%Live-Tools-Updater.exe" (
        echo 检测到未完成更新，但恢复程序不存在。请重新下载完整安装包。
        pause
        exit /b 1
    )
    echo 检测到上次更新未完成，正在自动恢复...
    "%SCRIPT_DIR%Live-Tools-Updater.exe" --recover --install-dir "%SCRIPT_DIR%" --transaction-file "%UPDATE_TRANSACTION%"
    if %errorlevel% neq 0 (
        echo 自动恢复失败，请查看 %TEMP%\Live-Tools-Updater.log
        pause
        exit /b 1
    )
)

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/api/health' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
    echo 直播工具已在运行，正在打开页面...
    start http://127.0.0.1:8080
    exit /b 0
)

if exist "%SCRIPT_DIR%\Live-Tools-Web.exe" (
    start "直播工具服务" /min cmd /c ""%SCRIPT_DIR%\Live-Tools-Web.exe" > "%LOG_FILE%" 2>&1"
    goto :wait_for_server
)

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

echo 未找到 Python。源码运行需要先安装 Python；打包版本请确认 Live-Tools-Web.exe 存在。
pause
exit /b 1

:source_mode
echo 使用 Python: %PYTHON_CMD%
%PYTHON_CMD% -c "import flask, openpyxl, playwright, PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo 依赖缺失，正在安装...
    %PYTHON_CMD% -m pip install -r "live-web\requirements.txt"
    %PYTHON_CMD% -m pip install -r "live-sku-price-audit\requirements.txt"
    %PYTHON_CMD% -m pip install -r "live-promotion-binding\requirements.txt"
    %PYTHON_CMD% -m pip install -r "product-selection-agent\requirements.txt"
    if %errorlevel% neq 0 (
        echo 依赖安装失败，请检查网络或 Python 环境。
        pause
        exit /b 1
    )
)

%PYTHON_CMD% -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>&1
if %errorlevel% neq 0 (
    echo Chromium 未安装，正在安装...
    %PYTHON_CMD% -m playwright install chromium
    if %errorlevel% neq 0 (
        echo Chromium 安装失败，请手动运行: %PYTHON_CMD% -m playwright install chromium
        pause
        exit /b 1
    )
)

start "直播工具服务" /min cmd /c ""%PYTHON_CMD%" "%SCRIPT_DIR%\live-web\app.py" > "%LOG_FILE%" 2>&1"
goto :wait_for_server

:wait_for_server
echo 正在启动直播工具...
echo 启动日志: %LOG_FILE%

set /a count=0
:check_loop
timeout /t 1 /nobreak >nul 2>&1
set /a count+=1
if %count% geq 15 goto :timeout

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8080' -TimeoutSec 3 -UseBasicParsing; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 goto :check_loop

echo 服务已启动，正在打开浏览器...
start http://127.0.0.1:8080

if not exist "%SCRIPT_DIR%\关闭服务.bat" (
    (
        echo @echo off
        echo echo 正在关闭服务...
        echo powershell -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8080/api/shutdown' -Method POST -TimeoutSec 3 ^| Out-Null } catch {}"
        echo echo 服务已关闭
        echo timeout /t 2 /nobreak ^>nul
    ) > "%SCRIPT_DIR%\关闭服务.bat"
)

exit /b 0

:timeout
echo 服务启动超时，请手动访问 http://127.0.0.1:8080
echo 如果仍无法访问，请打开日志文件查看原因:
echo %LOG_FILE%
pause
exit /b 1
