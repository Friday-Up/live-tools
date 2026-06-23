"""
批量测价任务编排。

这个模块只处理任务状态流：逐个 SKU 执行、登录失效后重试当前 SKU、
以及在两个 SKU 之间响应停止请求。Web 和命令行都复用这里，避免两套逻辑漂移。
"""

from dataclasses import dataclass
import queue
import threading
from typing import Callable, Iterable, List, Optional, Sequence, Tuple


SkuRow = Tuple[int, str]
Result = dict
JOIN_POLL_SECONDS = 0.05
STOP_JOIN_GRACE_SECONDS = 0.05


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


def run_sku_batch_on_page(
    sku_data: Iterable[SkuRow],
    crawl_func: Callable[[object, int, str], Result],
    recover_login_func: Callable[[], bool],
    stop_event,
    page: object,
    on_item_start: Optional[Callable[[int, int, int, str], None]] = None,
    on_result: Optional[Callable[[Result], None]] = None,
    on_login_required: Optional[Callable[[int, str, Result], None]] = None,
    max_login_retries: int = 1,
) -> BatchResult:
    """
    Run SKU checks against one page in the current thread.

    Playwright's sync API is greenlet-bound to the thread that owns the page, so
    real browser pages must not be passed into the threaded runner.
    """
    return run_sku_batch(
        sku_data=sku_data,
        crawl_func=lambda row_index, sku: crawl_func(page, row_index, sku),
        recover_login_func=recover_login_func,
        stop_event=stop_event,
        on_item_start=on_item_start,
        on_result=on_result,
        on_login_required=on_login_required,
        max_login_retries=max_login_retries,
    )


def run_sku_batch_concurrent(
    sku_data: Iterable[SkuRow],
    crawl_func: Callable[[object, int, str], Result],
    recover_login_func: Callable[[], bool],
    stop_event,
    pages: Sequence[object],
    on_item_start: Optional[Callable[[int, int, int, str], None]] = None,
    on_result: Optional[Callable[[Result], None]] = None,
    on_login_required: Optional[Callable[[int, str, Result], None]] = None,
    max_login_retries: int = 1,
) -> BatchResult:
    """
    Run thread-safe page-like workers concurrently.

    Do not pass Playwright sync Page objects here; they must stay on their owner
    thread. Use run_sku_batch_on_page for the current sync browser path.
    """
    rows = list(sku_data)
    if not pages:
        raise ValueError("pages must contain at least one page")

    jobs: queue.Queue[Tuple[int, int, str]] = queue.Queue()
    for position, (row_index, sku) in enumerate(rows, 1):
        jobs.put((position, row_index, sku))

    results: List[Result] = []
    state_lock = threading.Lock()
    callback_lock = threading.Lock()
    login_lock = threading.Lock()
    login_gate = threading.Event()
    login_gate.set()
    stopped = False
    login_failed = False
    login_recovery_count = 0

    def get_state():
        with state_lock:
            return stopped, login_failed, login_recovery_count

    def set_stopped():
        nonlocal stopped
        with state_lock:
            stopped = True

    def set_login_failed():
        nonlocal login_failed
        with state_lock:
            login_failed = True

    def record_result(row_index: int, result: Result):
        result["row_index"] = row_index
        with state_lock:
            results.append(result)
        if on_result:
            with callback_lock:
                on_result(result)

    def recover_login(observed_recovery_count: int) -> bool:
        nonlocal login_recovery_count

        login_gate.clear()
        try:
            with login_lock:
                with state_lock:
                    if login_failed:
                        return False
                    if login_recovery_count > observed_recovery_count:
                        return True

                if not recover_login_func():
                    set_login_failed()
                    return False

                with state_lock:
                    login_recovery_count += 1
                return True
        finally:
            login_gate.set()

    def worker(page):
        while True:
            login_gate.wait()

            current_stopped, current_login_failed, _ = get_state()
            if stop_event.is_set() or current_stopped or current_login_failed:
                return

            try:
                position, row_index, sku = jobs.get_nowait()
            except queue.Empty:
                return

            try:
                login_attempts = 0
                while True:
                    current_stopped, current_login_failed, observed_recovery_count = get_state()
                    if stop_event.is_set() or current_stopped or current_login_failed:
                        set_stopped()
                        return

                    if on_item_start:
                        with callback_lock:
                            on_item_start(position, len(rows), row_index, sku)

                    result = crawl_func(page, row_index, sku)

                    if result.get("status") == "stopped":
                        set_stopped()
                        return

                    if result.get("status") == "need_login":
                        if on_login_required:
                            with callback_lock:
                                on_login_required(row_index, sku, result)

                        if login_attempts >= max_login_retries:
                            record_result(row_index, result)
                            set_login_failed()
                            return

                        login_attempts += 1
                        if not recover_login(observed_recovery_count):
                            record_result(row_index, result)
                            return

                        continue

                    record_result(row_index, result)
                    break
            finally:
                jobs.task_done()

    threads = [threading.Thread(target=worker, args=(page,)) for page in pages]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if stop_event.is_set():
        set_stopped()

    with state_lock:
        return BatchResult(results=results, stopped=stopped, login_failed=login_failed)


def _page_factory_result(factory_result):
    if isinstance(factory_result, tuple):
        if len(factory_result) == 3:
            return factory_result
        if len(factory_result) == 2:
            return factory_result[0], factory_result[1], None
        if len(factory_result) == 1:
            return factory_result[0], None, None
    return factory_result, None, None


def run_sku_batch_with_page_factory(
    sku_data: Iterable[SkuRow],
    crawl_func: Callable[[object, int, str], Result],
    recover_login_func: Callable[[], bool],
    stop_event,
    page_factory: Callable[[int], object],
    worker_count: int = 3,
    on_item_start: Optional[Callable[[int, int, int, str], None]] = None,
    on_result: Optional[Callable[[Result], None]] = None,
    on_login_required: Optional[Callable[[int, str, Result], None]] = None,
    max_login_retries: int = 1,
) -> BatchResult:
    """
    Run SKU checks concurrently with each worker creating its page in its own thread.

    This is the path for Playwright sync pages: a Page must be created and used
    in the same thread, so callers provide a factory instead of pre-created pages.
    """
    rows = list(sku_data)
    if worker_count <= 0:
        raise ValueError("worker_count must be greater than 0")
    if not rows:
        return BatchResult(results=[])

    worker_count = min(worker_count, len(rows))

    jobs: queue.Queue[Tuple[int, int, str]] = queue.Queue()
    for position, (row_index, sku) in enumerate(rows, 1):
        jobs.put((position, row_index, sku))

    results: List[Result] = []
    state_lock = threading.Lock()
    callback_lock = threading.Lock()
    login_lock = threading.Lock()
    login_gate = threading.Event()
    login_gate.set()
    stopped = False
    login_failed = False
    login_recovery_count = 0
    worker_errors = []

    def get_state():
        with state_lock:
            return stopped, login_failed, login_recovery_count

    def set_stopped():
        nonlocal stopped
        with state_lock:
            stopped = True

    def set_login_failed():
        nonlocal login_failed
        with state_lock:
            login_failed = True

    def record_worker_error(exc: Exception):
        with state_lock:
            worker_errors.append(exc)

    def record_result(row_index: int, result: Result):
        result["row_index"] = row_index
        with state_lock:
            results.append(result)
        if on_result:
            with callback_lock:
                on_result(result)

    def recover_login(observed_recovery_count: int, page_recover_login_func: Optional[Callable[[], bool]] = None) -> bool:
        nonlocal login_recovery_count

        login_gate.clear()
        try:
            with login_lock:
                with state_lock:
                    if login_failed:
                        return False
                    if login_recovery_count > observed_recovery_count:
                        return True

                recovery_func = page_recover_login_func or recover_login_func
                if not recovery_func():
                    set_login_failed()
                    return False

                with state_lock:
                    login_recovery_count += 1
                return True
        finally:
            login_gate.set()

    def worker(worker_index: int):
        page = None
        cleanup = None
        recover_page_login = None
        seen_login_recovery_count = 0

        def close_page():
            nonlocal page, cleanup, recover_page_login
            if cleanup:
                try:
                    cleanup()
                except Exception:
                    pass
            page = None
            cleanup = None
            recover_page_login = None

        def open_page():
            nonlocal page, cleanup, recover_page_login
            factory_result = page_factory(worker_index)
            page, cleanup, recover_page_login = _page_factory_result(factory_result)

        try:
            try:
                open_page()
                with state_lock:
                    seen_login_recovery_count = login_recovery_count

                while True:
                    login_gate.wait()

                    current_stopped, current_login_failed, current_recovery_count = get_state()
                    if stop_event.is_set() or current_stopped or current_login_failed:
                        return
                    if current_recovery_count > seen_login_recovery_count:
                        close_page()
                        open_page()
                        seen_login_recovery_count = current_recovery_count

                    try:
                        position, row_index, sku = jobs.get_nowait()
                    except queue.Empty:
                        return

                    try:
                        login_attempts = 0
                        while True:
                            current_stopped, current_login_failed, observed_recovery_count = get_state()
                            if stop_event.is_set() or current_stopped or current_login_failed:
                                set_stopped()
                                return

                            if on_item_start:
                                with callback_lock:
                                    on_item_start(position, len(rows), row_index, sku)

                            result = crawl_func(page, row_index, sku)
                            if stop_event.is_set():
                                set_stopped()
                                return

                            if result.get("status") == "stopped":
                                set_stopped()
                                return

                            if result.get("status") == "need_login":
                                if on_login_required:
                                    with callback_lock:
                                        on_login_required(row_index, sku, result)

                                if login_attempts >= max_login_retries:
                                    record_result(row_index, result)
                                    set_login_failed()
                                    return

                                login_attempts += 1
                                if recover_page_login is None:
                                    close_page()
                                if not recover_login(observed_recovery_count, recover_page_login):
                                    record_result(row_index, result)
                                    return
                                close_page()
                                open_page()
                                _, _, seen_login_recovery_count = get_state()
                                continue

                            record_result(row_index, result)
                            break
                    finally:
                        jobs.task_done()
            except Exception as exc:
                record_worker_error(exc)
                set_stopped()
        finally:
            close_page()

    threads = [
        threading.Thread(target=worker, args=(worker_index,), daemon=True)
        for worker_index in range(worker_count)
    ]
    for thread in threads:
        thread.start()

    while True:
        alive_threads = [thread for thread in threads if thread.is_alive()]
        if not alive_threads:
            break

        if stop_event.is_set():
            set_stopped()
            for thread in alive_threads:
                thread.join(timeout=STOP_JOIN_GRACE_SECONDS)
            break

        for thread in alive_threads:
            thread.join(timeout=JOIN_POLL_SECONDS)

    if stop_event.is_set():
        set_stopped()

    with state_lock:
        if worker_errors and not stop_event.is_set():
            raise RuntimeError(f"SKU 并发 worker 出错: {worker_errors[0]}")
        return BatchResult(results=list(results), stopped=stopped, login_failed=login_failed)
