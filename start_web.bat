@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
:: ============================================================
:: 直播-点菜 SKU 巡检 - Web GUI 启动脚本 (Windows)
:: ============================================================

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%" || exit /b 1

echo ============================================================
echo 🚀 直播-点菜 SKU 巡检 - Web 版
echo ============================================================
echo.

:: 检查是否是打包版本（存在 SKU-Price-Audit-Web.exe）
if exist "%SCRIPT_DIR%\SKU-Price-Audit-Web.exe" (
    set "RUN_CMD=%SCRIPT_DIR%\SKU-Price-Audit-Web.exe"
    echo ✅ 检测到打包版本
    goto :start_app
)

:: 检查是否是源码版本
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "RUN_CMD=python app.py"
    echo ℹ️  源码版本，使用系统 Python
    goto :start_app
)

python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "RUN_CMD=python3 app.py"
    echo ℹ️  源码版本，使用系统 Python3
    goto :start_app
)

echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
pause
exit /b 1

:start_app
echo 📁 工作目录: %SCRIPT_DIR%
echo.
echo ============================================================
echo 🌐 正在启动 Web 服务...
echo ============================================================
echo.
echo 服务启动后，将自动打开浏览器
echo 如未自动打开，请手动访问: http://localhost:8080
echo.

:: 启动 Flask 服务
%RUN_CMD%

:: 如果程序异常退出，暂停显示错误
echo.
echo ⚠️ 程序已退出
echo.
pause
endlocal
