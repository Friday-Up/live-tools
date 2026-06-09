#!/bin/bash
# ============================================================
# 直播-点菜 SKU 巡检 - 一键启动脚本 (macOS/Linux)
# ============================================================

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "============================================================"
echo "🚀 直播-点菜 SKU 巡检 - 测价工具"
echo "============================================================"
echo ""

# 检查 Python 是否安装
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ 错误：未找到 Python，请先安装 Python 3.8+"
    echo "   下载地址：https://www.python.org/downloads/"
    read -n 1 -s -r -p "按任意键退出..."
    echo ""
    exit 1
fi

echo "✅ 使用 Python: $PYTHON_CMD"
echo "📁 工作目录: $SCRIPT_DIR"
echo ""

# 检查依赖是否安装
echo "🔍 检查依赖..."
$PYTHON_CMD -c "import openpyxl, playwright" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  依赖未安装，正在安装..."
    $PYTHON_CMD -m pip install -r requirements.txt -q
    if [ $? -ne 0 ]; then
        echo "❌ 依赖安装失败，请手动运行: pip install -r requirements.txt"
        read -n 1 -s -r -p "按任意键退出..."
        echo ""
        exit 1
    fi
    echo "✅ 依赖安装完成"
else
    echo "✅ 依赖已安装"
fi

# 检查 Playwright 浏览器是否安装
echo "🔍 检查 Playwright 浏览器..."
$PYTHON_CMD -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(headless=True).close(); p.stop()" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Playwright 浏览器未安装，正在安装..."
    $PYTHON_CMD -m playwright install chromium
    if [ $? -ne 0 ]; then
        echo "❌ 浏览器安装失败，请手动运行: playwright install chromium"
        read -n 1 -s -r -p "按任意键退出..."
        echo ""
        exit 1
    fi
    echo "✅ 浏览器安装完成"
else
    echo "✅ 浏览器已安装"
fi

echo ""

# 列出 input 目录下的 xlsx 文件
INPUT_DIR="input"
if [ ! -d "$INPUT_DIR" ]; then
    echo "❌ 错误：input/ 目录不存在"
    read -n 1 -s -r -p "按任意键退出..."
    echo ""
    exit 1
fi

# 获取所有 xlsx 文件
FILES=()
while IFS= read -r file; do
    FILES+=("$file")
done < <(ls -1 "$INPUT_DIR"/*.xlsx 2>/dev/null | sort)

if [ ${#FILES[@]} -eq 0 ]; then
    echo "❌ 错误：input/ 目录下没有找到 .xlsx 文件"
    read -n 1 -s -r -p "按任意键退出..."
    echo ""
    exit 1
fi

# 选择文件
echo "============================================================"
echo "📁 请选择要处理的表格文件"
echo "============================================================"
for i in "${!FILES[@]}"; do
    filename=$(basename "${FILES[$i]}")
    echo "  [$((i+1))] $filename"
done
echo "------------------------------------------------------------"

while true; do
    read -p "请输入编号（1-${#FILES[@]}）：" file_index
    if [[ "$file_index" =~ ^[0-9]+$ ]] && [ "$file_index" -ge 1 ] && [ "$file_index" -le ${#FILES[@]} ]; then
        SELECTED_FILE="${FILES[$((file_index-1))]}"
        echo "✅ 已选择: $(basename "$SELECTED_FILE")"
        break
    else
        echo "❌ 请输入 1-${#FILES[@]} 之间的数字"
    fi
done

echo ""

# 设置价格门槛
echo "============================================================"
echo "💰 设置价格门槛"
echo "============================================================"
echo "提示：低于门槛价的商品将被标记为\"不符合上菜\""
echo ""

while true; do
    read -p "请输入价格门槛（直接回车使用默认值 6.0）：" threshold_input

    # 如果用户直接回车，使用默认值
    if [ -z "$threshold_input" ]; then
        THRESHOLD="6.0"
        break
    fi

    # 验证输入是否为有效数字
    if echo "$threshold_input" | grep -Eq '^[0-9]+(\.[0-9]+)?$'; then
        THRESHOLD="$threshold_input"
        break
    else
        echo "❌ 请输入有效的数字（如：10.0 或 20）"
    fi
done

echo ""
echo "✅ 本次价格门槛：¥$THRESHOLD"
echo ""

echo "============================================================"
echo "🎉 环境检查完成，正在启动程序..."
echo "============================================================"
echo ""

# 启动主程序
$PYTHON_CMD main.py -f "$SELECTED_FILE" -t "$THRESHOLD"

# 程序结束后提示
echo ""
echo "============================================================"
echo "💡 提示:"
echo "   • 程序执行完毕，浏览器窗口已关闭"
echo "   • 登录态已保存，下次运行无需重新登录"
echo "   • 结果文件保存在 output/ 目录"
echo "============================================================"
echo ""
read -n 1 -s -r -p "按任意键退出..."
echo ""
