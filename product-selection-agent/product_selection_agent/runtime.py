"""单次选品运行的日志和取消上下文。"""
from __future__ import annotations

import threading
from collections.abc import Callable


class SelectionCancelled(RuntimeError):
    """用户请求停止当前选品任务。"""


class RunContext:
    def __init__(
        self,
        log_callback: Callable[[str], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._log_callback = log_callback
        self.stop_event = stop_event or threading.Event()

    def log(self, message: str) -> None:
        text = str(message)
        if self._log_callback is None:
            print(text)
        else:
            self._log_callback(text)

    def check_cancelled(self) -> None:
        if self.stop_event.is_set():
            raise SelectionCancelled("选品任务已停止")
