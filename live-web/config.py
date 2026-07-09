"""Configuration for the unified live local web tool."""

import os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
LIVE_USAGE_EVENT_ENDPOINT = os.environ.get("LIVE_USAGE_EVENT_ENDPOINT", "")
LIVE_USAGE_EVENT_TOKEN = os.environ.get("LIVE_USAGE_EVENT_TOKEN", "")
LIVE_USAGE_EVENT_ENABLED = os.environ.get("LIVE_USAGE_EVENT_ENABLED", "").lower() in {
    "1",
    "true",
    "yes",
}
LIVE_USAGE_EVENT_TIMEOUT_SECONDS = float(os.environ.get("LIVE_USAGE_EVENT_TIMEOUT_SECONDS", "2.0"))
LIVE_TOOLS_APP_VERSION = "2026.07.09"
