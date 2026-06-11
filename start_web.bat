@echo off
:: ============================================================
:: 直播-点菜 SKU 巡检 - Web GUI 启动脚本 (Windows)
:: ============================================================

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%" || exit /b 1

:: 生成唯一文件名避免冲突
set "VBS_FILE=%TEMP%\start_hidden_%RANDOM%.vbs"

:: 检查是否是打包版本
if exist "%SCRIPT_DIR%\SKU-Price-Audit-Web.exe" (
    echo Set WshShell = CreateObject("WScript.Shell") > "%VBS_FILE%"
    echo WshShell.Run """%SCRIPT_DIR%\SKU-Price-Audit-Web.exe""", 0, False >> "%VBS_FILE%"
    cscript //nologo "%VBS_FILE%"
    del "%VBS_FILE%"
    goto :wait_for_server
)

:: 检查是否是源码版本
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo Set WshShell = CreateObject("WScript.Shell") > "%VBS_FILE%"
    echo WshShell.Run "python ""%SCRIPT_DIR%\app.py""", 0, False >> "%VBS_FILE%"
    cscript //nologo "%VBS_FILE%"
    del "%VBS_FILE%"
    goto :wait_for_server
)

python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    echo Set WshShell = CreateObject("WScript.Shell") > "%VBS_FILE%"
    echo WshShell.Run "python3 ""%SCRIPT_DIR%\app.py""", 0, False >> "%VBS_FILE%"
    cscript //nologo "%VBS_FILE%"
    del "%VBS_FILE%"
    goto :wait_for_server
)

echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
pause
exit /b 1

:wait_for_server
echo 🚀 正在启动服务...

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
pause
exit /b 1
