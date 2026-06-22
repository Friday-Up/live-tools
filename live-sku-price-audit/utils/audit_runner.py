"""
批量测价任务编排。

这个模块只处理任务状态流：逐个 SKU 执行、登录失效后重试当前 SKU、
以及在两个 SKU 之间响应停止请求。Web 和命令行都复用这里，避免两套逻辑漂移。
"""

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple


SkuRow = Tuple[int, str]
Result = dict


@dataclass
class BatchResult:
    results: List[Result]
    stopped: bool = False
    login_failed: bool = False


def run_sku_batch(
    sku_data: Iterable[SkuRow],
    crawl_func: Callable[[int, str], Result],
    recover_login_func: Callable[[], bool],
    stop_event,
    on_item_start: Optional[Callable[[int, int, int, str], None]] = None,
    on_result: Optional[Callable[[Result], None]] = None,
    on_login_required: Optional[Callable[[int, str, Result], None]] = None,
    max_login_retries: int = 1,
) -> BatchResult:
    rows = list(sku_data)
    results: List[Result] = []
    stopped = False
    login_failed = False

    for position, (row_index, sku) in enumerate(rows, 1):
        if stop_event.is_set():
            stopped = True
            break

        login_attempts = 0

        while True:
            if stop_event.is_set():
                stopped = True
                break

            if on_item_start:
                on_item_start(position, len(rows), row_index, sku)

            result = crawl_func(row_index, sku)

            if result.get("status") == "stopped":
                stopped = True
                break

            if result.get("status") == "need_login":
                if on_login_required:
                    on_login_required(row_index, sku, result)

                if login_attempts >= max_login_retries:
                    result["row_index"] = row_index
                    results.append(result)
                    login_failed = True
                    if on_result:
                        on_result(result)
                    break

                login_attempts += 1
                if not recover_login_func():
                    result["row_index"] = row_index
                    results.append(result)
                    login_failed = True
                    if on_result:
                        on_result(result)
                    break

                continue

            result["row_index"] = row_index
            results.append(result)
            if on_result:
                on_result(result)
            break

        if stopped or login_failed:
            break

    if stop_event.is_set():
        stopped = True

    return BatchResult(results=results, stopped=stopped, login_failed=login_failed)
