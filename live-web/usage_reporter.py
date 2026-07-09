from __future__ import annotations

"""Best-effort reporter for live local tool usage events."""

import getpass
import json
import logging
import threading
import uuid
from datetime import datetime
from urllib import request as urllib_request

from config import (
    LIVE_TOOLS_APP_VERSION,
    LIVE_USAGE_EVENT_ENABLED,
    LIVE_USAGE_EVENT_ENDPOINT,
    LIVE_USAGE_EVENT_TIMEOUT_SECONDS,
    LIVE_USAGE_EVENT_TOKEN,
)

LOGGER = logging.getLogger(__name__)


class LiveToolUsageReporter:
    def __init__(
        self,
        endpoint: str,
        token: str,
        enabled: bool = True,
        app_name: str = "live-tools",
        app_version: str = LIVE_TOOLS_APP_VERSION,
        user_name: str | None = None,
        session_id: str | None = None,
        timeout_seconds: float = LIVE_USAGE_EVENT_TIMEOUT_SECONDS,
        id_factory=None,
        now_func=None,
        urlopen=None,
    ):
        self.endpoint = endpoint
        self.token = token
        self.enabled = bool(enabled)
        self.app_name = app_name
        self.app_version = app_version
        self.user_name = user_name or getpass.getuser()
        self.session_id = session_id or uuid.uuid4().hex
        self.timeout_seconds = timeout_seconds
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self.now_func = now_func or (lambda: datetime.now().astimezone())
        self.urlopen = urlopen or urllib_request.urlopen

    def build_event(
        self,
        tool_code: str,
        action: str,
        task_id: str | None = None,
        item_count: int | None = None,
        success_count: int | None = None,
        fail_count: int | None = None,
        duration_ms: int | None = None,
        status: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        event_time = self.now_func()
        if event_time.tzinfo is None:
            event_time = event_time.astimezone()

        event = {
            "event_id": str(self.id_factory()),
            "event_time": event_time.isoformat(timespec="seconds"),
            "app_name": self.app_name,
            "app_version": self.app_version,
            "tool_code": tool_code,
            "action": action,
            "user_name": self.user_name,
            "session_id": self.session_id,
        }
        optional_fields = {
            "task_id": task_id,
            "item_count": item_count,
            "success_count": success_count,
            "fail_count": fail_count,
            "duration_ms": duration_ms,
            "status": status,
            "extra": extra,
        }
        for key, value in optional_fields.items():
            if value is not None:
                event[key] = value
        return event

    def send_event(self, **kwargs) -> bool:
        if not self.enabled or not self.endpoint or not self.token:
            return False

        payload = {"events": [self.build_event(**kwargs)]}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib_request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer %s" % self.token,
            },
        )
        try:
            with self.urlopen(request, timeout=self.timeout_seconds) as response:
                response.read()
            return True
        except Exception as exc:
            LOGGER.warning("report live tool usage event failed: %s", exc)
            return False

    def report_async(self, **kwargs):
        if not self.enabled or not self.endpoint or not self.token:
            return
        thread = threading.Thread(target=self.send_event, kwargs=kwargs, daemon=True)
        thread.start()


def create_usage_reporter(enabled: bool = LIVE_USAGE_EVENT_ENABLED) -> LiveToolUsageReporter:
    return LiveToolUsageReporter(
        endpoint=LIVE_USAGE_EVENT_ENDPOINT,
        token=LIVE_USAGE_EVENT_TOKEN,
        enabled=enabled,
    )
