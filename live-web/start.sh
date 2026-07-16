#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_CMD="${PYTHON_CMD:-python3}"

if ! "$PYTHON_CMD" -c "import flask, openpyxl, playwright, PIL" >/dev/null 2>&1; then
  echo "缺少依赖，请先安装：$PYTHON_CMD -m pip install -r requirements.txt"
  exit 1
fi

URL="http://127.0.0.1:8080"
mkdir -p runtime/logs
LOG_FILE="$SCRIPT_DIR/runtime/logs/live-web-$(date +%Y%m%d).log"
if command -v open >/dev/null 2>&1; then
  (sleep 1 && open "$URL") >/dev/null 2>&1 &
fi

echo "直播本地工具启动中：$URL"
echo "服务日志：$LOG_FILE"
"$PYTHON_CMD" app.py 2>&1 | tee -a "$LOG_FILE"
