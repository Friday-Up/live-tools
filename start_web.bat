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

:: 检查是否是打包版本（存在 _internal 目录或 SKU-Price-Audit-Web.exe）
if exist "%SCRIPT_DIR%\_internal" (
    set "PYTHON_CMD=%SCRIPT_DIR%\SKU-Price-Audit-Web.exe"
    echo ✅ 检测到打包版本
) else if exist "%SCRIPT_DIR%\SKU-Price-Audit-Web.exe" (
    set "PYTHON_CMD=%SCRIPT_DIR%\SKU-Price-Audit-Web.exe"
    echo ✅ 检测到打包版本
) else (
    :: 源码版本，检查 Python
    python --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=python"
        echo ℹ️  源码版本，使用系统 Python
    ) else (
        python3 --version >nul 2>&1
        if %errorlevel% equ 0 (
            set "PYTHON_CMD=python3"
            echo ℹ️  源码版本，使用系统 Python3
        ) else (
            echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
            pause
            exit /b 1
        )
    )
)

echo 📁 工作目录: %SCRIPT_DIR%
echo.

:: 检查依赖（仅源码版本）
echo "%PYTHON_CMD%" | findstr /C:"SKU-Price-Audit-Web.exe" >nul
if %errorlevel% equ 0 (
    echo ✅ 打包版本，依赖已内置
) else (
    echo 🔍 检查依赖...
    %PYTHON_CMD% -c "import flask, openpyxl, playwright" >nul 2>&1
    if %errorlevel% neq 0 (
        echo ⚠️  依赖未安装，正在安装...
        %PYTHON_CMD% -m pip install -r requirements.txt -q
        if %errorlevel% neq 0 (
            echo ❌ 依赖安装失败
            pause
            exit /b 1
        )
        echo ✅ 依赖安装完成
    ) else (
        echo ✅ 依赖已安装
    )
)

echo.
echo ============================================================
echo 🌐 正在启动 Web 服务...
echo ============================================================
echo.
echo 服务启动后，将自动打开浏览器
echo 如未自动打开，请手动访问: http://localhost:8080
echo.

:: 启动 Flask 服务
"%PYTHON_CMD%"

endlocal
