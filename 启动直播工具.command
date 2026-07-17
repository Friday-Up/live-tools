#!/bin/bash

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

URL="http://127.0.0.1:8080"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/live-tools.log"
PID_FILE="$LOG_DIR/live-tools.pid"
APP="$SCRIPT_DIR/Live-Tools-Web"

mkdir -p "$LOG_DIR"

if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
  open "$URL"
  exit 0
fi

if [[ ! -f "$APP" ]]; then
  echo "未找到 Live-Tools-Web，请确认已完整解压安装包。"
  read -r -p "按回车关闭窗口..."
  exit 1
fi

chmod +x "$APP"
nohup "$APP" >> "$LOG_FILE" 2>&1 &
APP_PID=$!
echo "$APP_PID" > "$PID_FILE"

for _ in {1..30}; do
  if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
    open "$URL"
    exit 0
  fi

  if ! kill -0 "$APP_PID" >/dev/null 2>&1; then
    break
  fi

  sleep 1
done

echo "直播运营工具启动失败，请查看日志：$LOG_FILE"
open "$LOG_FILE" >/dev/null 2>&1 || true
read -r -p "按回车关闭窗口..."
exit 1
