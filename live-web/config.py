"""Configuration for the unified live local web tool."""

import os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
LIVE_USAGE_EVENT_ENDPOINT = os.environ.get(
    "LIVE_USAGE_EVENT_ENDPOINT",
    "http://114.67.72.156/AllSpark/api/live-tools/events",
)
LIVE_USAGE_EVENT_TOKEN = os.environ.get(
    "LIVE_USAGE_EVENT_TOKEN",
    "live-tools-analytics-2026",
)
LIVE_USAGE_EVENT_ENABLED = os.environ.get("LIVE_USAGE_EVENT_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}
LIVE_USAGE_EVENT_TIMEOUT_SECONDS = float(os.environ.get("LIVE_USAGE_EVENT_TIMEOUT_SECONDS", "2.0"))
LIVE_TOOLS_APP_VERSION = "0.5.3"
LIVE_TOOLS_UPDATE_MANIFEST_URL = os.environ.get(
    "LIVE_TOOLS_UPDATE_MANIFEST_URL",
    "https://github.com/Friday-Up/live-tools/releases/latest/download/live-tools-update.json",
)
