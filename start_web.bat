@echo off
:: ============================================================
:: 直播-点菜 SKU 巡检 - Web GUI 启动脚本 (Windows)
:: 后台运行，不显示终端窗口
:: ============================================================

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%" || exit /b 1

:: 检查是否是打包版本
if exist "%SCRIPT_DIR%\SKU-Price-Audit-Web.exe" (
    :: 后台运行 EXE，隐藏窗口
    start "" /B "%SCRIPT_DIR%\SKU-Price-Audit-Web.exe"
    goto :wait_for_server
)

:: 检查是否是源码版本
python --version >nul 2>&1
if %errorlevel% equ 0 (
    start "" /B python "%SCRIPT_DIR%\app.py"
    goto :wait_for_server
)

python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    start "" /B python3 "%SCRIPT_DIR%\app.py"
    goto :wait_for_server
)

echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
pause
exit /b 1

:wait_for_server
echo 🚀 正在启动服务...

:: 等待服务启动（最多 10 秒）
set /a count=0
:check_loop
ping -n 2 127.0.0.1 >nul 2>&1
set /a count+=1
if %count% geq 10 goto :timeout

:: 检查服务是否启动
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8080' -TimeoutSec 1 -UseBasicParsing; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 goto :check_loop

:: 服务已启动，打开浏览器
echo ✅ 服务已启动，正在打开浏览器...
start http://127.0.0.1:8080

:: 创建关闭快捷方式（可选）
if not exist "%SCRIPT_DIR%\关闭服务.bat" (
    (
        echo @echo off
        echo echo 🛑 正在关闭服务...
        echo powershell -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8080/api/shutdown' -Method POST -TimeoutSec 2 | Out-Null } catch {}"
        echo echo ✅ 服务已关闭
        echo timeout /t 2 /nobreak >nul
    ) > "%SCRIPT_DIR%\关闭服务.bat"
)

exit /b 0

:timeout
echo ⚠️ 服务启动超时，请手动访问 http://127.0.0.1:8080
pause
exit /b 1
