#!/bin/bash

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
URL="http://127.0.0.1:8080"
PID_FILE="$SCRIPT_DIR/logs/live-tools.pid"

curl -fsS -X POST "$URL/api/shutdown" >/dev/null 2>&1 || true
sleep 2

if curl -fsS "$URL/api/health" >/dev/null 2>&1 && [[ -f "$PID_FILE" ]]; then
  APP_PID="$(tr -cd '0-9' < "$PID_FILE")"
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" >/dev/null 2>&1; then
    kill "$APP_PID" >/dev/null 2>&1 || true
  fi
fi

rm -f "$PID_FILE"
echo "直播运营工具已关闭。"
sleep 2
