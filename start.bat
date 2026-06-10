@echo off
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

:: 检查 Python 是否安装（优先使用打包内置的 Python）
if exist "%SCRIPT_DIR%\_internal\python.exe" (
    set "PYTHON_CMD=%SCRIPT_DIR%\_internal\python.exe"
    goto :python_found
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python3"
    goto :python_found
)

echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
echo    下载地址：https://www.python.org/downloads/
pause
exit /b 1

:python_found
echo ✅ 使用 Python: %PYTHON_CMD%
echo 📁 工作目录: %SCRIPT_DIR%
echo.

:: 检查依赖是否安装（如果不是打包版本）
if "%PYTHON_CMD%"=="%SCRIPT_DIR%\_internal\python.exe" (
    echo ✅ 打包版本，依赖已内置
) else (
    echo 🔍 检查依赖...
    %PYTHON_CMD% -c "import openpyxl, playwright" >nul 2>&1
    if %errorlevel% neq 0 (
        echo ⚠️  依赖未安装，正在安装...
        %PYTHON_CMD% -m pip install -r requirements.txt -q
        if %errorlevel% neq 0 (
            echo ❌ 依赖安装失败，请手动运行: pip install -r requirements.txt
            pause
            exit /b 1
        )
        echo ✅ 依赖安装完成
    ) else (
        echo ✅ 依赖已安装
    )

    :: 检查 Playwright 浏览器是否安装
    echo 🔍 检查 Playwright 浏览器...
    %PYTHON_CMD% -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(headless=True).close(); p.stop()" >nul 2>&1
    if %errorlevel% neq 0 (
        echo ⚠️  Playwright 浏览器未安装，正在安装...
        %PYTHON_CMD% -m playwright install chromium
        if %errorlevel% neq 0 (
            echo ❌ 浏览器安装失败，请手动运行: playwright install chromium
            pause
            exit /b 1
        )
        echo ✅ 浏览器安装完成
    ) else (
        echo ✅ 浏览器已安装
    )
)

echo.

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

set /p THRESHOLD_INPUT="请输入价格门槛（直接回车使用默认值 6.0）："

:: 如果用户直接回车，使用默认值
if "%THRESHOLD_INPUT%"=="" (
    set "THRESHOLD=6.0"
) else (
    set "THRESHOLD=%THRESHOLD_INPUT%"
)

echo.
echo ✅ 本次价格门槛：¥%THRESHOLD%
echo.

echo ============================================================
echo 🎉 环境检查完成，正在启动程序...
echo ============================================================
echo.

:: 启动主程序
%PYTHON_CMD% main.py -f "%SELECTED_FILE%" -t %THRESHOLD%

:: 程序结束后提示
echo.
echo ============================================================
echo 💡 提示:
echo    • 程序执行完毕，浏览器窗口已关闭
echo    • 登录态已保存，下次运行无需重新登录
echo    • 结果文件保存在 output/ 目录
echo ============================================================
echo.
pause
