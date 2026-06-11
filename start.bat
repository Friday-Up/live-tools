@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
:: ============================================================
:: 直播-点菜 SKU 巡检 - 一键启动脚本 (Windows)
:: ============================================================

:: 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%" || exit /b 1

echo ============================================================
echo 🚀 直播-点菜 SKU 巡检 - 测价工具
echo ============================================================
echo.

:: 检查是否是打包版本（存在 SKU-Price-Audit.exe）
if exist "%SCRIPT_DIR%\SKU-Price-Audit.exe" (
    set "USE_EXE=1"
    echo ✅ 检测到打包版本
) else (
    set "USE_EXE=0"
    echo ℹ️  源码版本，需要 Python 环境
)

echo 📁 工作目录: %SCRIPT_DIR%
echo.

if "%USE_EXE%"=="0" (
    python --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
        pause
        exit /b 1
    )

    echo 🔍 检查依赖...
    python -c "import openpyxl, playwright, PIL" >nul 2>&1
    if !errorlevel! neq 0 (
        echo ⚠️  依赖缺失，正在安装 requirements.txt...
        python -m pip install -r requirements.txt
        if !errorlevel! neq 0 (
            echo ❌ 依赖安装失败，请检查网络或 Python 环境
            pause
            exit /b 1
        )
    )

    echo 🔍 检查 Playwright Chromium...
    python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>&1
    if !errorlevel! neq 0 (
        echo ⚠️  Chromium 未安装，正在安装...
        python -m playwright install chromium
        if !errorlevel! neq 0 (
            echo ❌ Chromium 安装失败，请手动运行: python -m playwright install chromium
            pause
            exit /b 1
        )
    )
    echo ✅ 环境检查通过
    echo.
)

:: 列出 input 目录下的 xlsx 文件
set "INPUT_DIR=input"
if not exist "%INPUT_DIR%" (
    echo ❌ 错误：input/ 目录不存在
    pause
    exit /b 1
)

:: 获取文件列表
echo ============================================================
echo 📁 请选择要处理的表格文件
echo ============================================================

set FILE_COUNT=0
for %%f in ("%INPUT_DIR%\*.xlsx") do (
    set /a FILE_COUNT+=1
    set "FILE_!FILE_COUNT!=%%f"
    echo   [!FILE_COUNT!] %%~nxf
)

if %FILE_COUNT% equ 0 (
    echo ❌ 错误：input/ 目录下没有找到 .xlsx 文件
    pause
    exit /b 1
)

echo ------------------------------------------------------------

:: 选择文件
:select_file
set /p FILE_INDEX="请输入编号（1-%FILE_COUNT%）："

if "%FILE_INDEX%"=="" goto select_file

:: 验证输入
set /a TEST=%FILE_INDEX% 2>nul
if %TEST% equ %FILE_INDEX% (
    if %FILE_INDEX% geq 1 if %FILE_INDEX% leq %FILE_COUNT% (
        goto file_selected
    )
)

echo ❌ 请输入 1-%FILE_COUNT% 之间的数字
goto select_file

:file_selected
:: 获取选中的文件
set SELECTED_FILE=!FILE_%FILE_INDEX%!
echo ✅ 已选择: %SELECTED_FILE%
echo.

:: 设置价格门槛
echo ============================================================
echo 💰 设置价格门槛
echo ============================================================
echo 提示：低于门槛价的商品将被标记为"不符合上菜"
echo.

:input_threshold
set /p THRESHOLD_INPUT="请输入价格门槛（直接回车使用默认值 6.0）："

:: 如果用户直接回车，使用默认值
if "%THRESHOLD_INPUT%"=="" (
    set "THRESHOLD=6.0"
) else (
    set "THRESHOLD=%THRESHOLD_INPUT%"
)

powershell -NoProfile -Command "try { $v=[double]'%THRESHOLD%'; if ($v -lt 0) { exit 1 } else { exit 0 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 请输入有效的非负数字（如：6.0 或 20）
    goto :input_threshold
)

echo.
echo ✅ 本次价格门槛：¥%THRESHOLD%
echo.

echo ============================================================
echo 🎉 正在启动程序...
echo ============================================================
echo.

:: 启动主程序
if "%USE_EXE%"=="1" (
    :: 打包版本：直接运行 EXE
    "%SCRIPT_DIR%\SKU-Price-Audit.exe" -f "%SELECTED_FILE%" -t %THRESHOLD%
) else (
    :: 源码版本：使用 Python 运行
    python main.py -f "%SELECTED_FILE%" -t %THRESHOLD%
)

:: 程序结束后提示
echo.
echo ============================================================
echo 💡 提示:
echo    • 程序执行完毕
echo    • 登录态已保存，下次运行无需重新登录
echo    • 结果文件保存在 output/ 目录
echo ============================================================
echo.
pause
endlocal
