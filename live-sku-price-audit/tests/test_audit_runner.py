import threading
import unittest

from utils.audit_runner import (
    run_sku_batch,
    run_sku_batch_concurrent,
    run_sku_batch_on_page,
    run_sku_batch_with_page_factory,
)


class AuditRunnerTests(unittest.TestCase):
    def test_retries_same_sku_after_login_recovery_without_recording_stale_result(self):
        calls = []

        def crawl(row_index, sku):
            calls.append((row_index, sku))
            if len(calls) == 1:
                return {"sku": sku, "status": "need_login", "message": "need login"}
            return {"sku": sku, "status": "success", "price": 5.5, "message": "ok"}

        login_calls = []

        result = run_sku_batch(
            sku_data=[(2, "100264886683")],
            crawl_func=crawl,
            recover_login_func=lambda: login_calls.append("login") or True,
            stop_event=threading.Event(),
        )

        self.assertEqual(calls, [(2, "100264886683"), (2, "100264886683")])
        self.assertEqual(login_calls, ["login"])
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0]["status"], "success")
        self.assertEqual(result.results[0]["row_index"], 2)

    def test_stops_between_skus(self):
        stop_event = threading.Event()
        calls = []

        def crawl(row_index, sku):
            calls.append(sku)
            stop_event.set()
            return {"sku": sku, "status": "success", "price": 10, "message": "ok"}

        result = run_sku_batch(
            sku_data=[(2, "sku-1"), (3, "sku-2")],
            crawl_func=crawl,
            recover_login_func=lambda: True,
            stop_event=stop_event,
        )

        self.assertEqual(calls, ["sku-1"])
        self.assertTrue(result.stopped)
        self.assertEqual(len(result.results), 1)

    def test_concurrent_runner_starts_one_sku_per_page(self):
        all_started = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        started = []
        result_holder = []

        def crawl(page, row_index, sku):
            with lock:
                started.append((page, row_index, sku))
                if len(started) == 3:
                    all_started.set()
            release.wait(timeout=2)
            return {"sku": sku, "status": "success", "price": 10, "message": "ok"}

        thread = threading.Thread(
            target=lambda: result_holder.append(
                run_sku_batch_concurrent(
                    sku_data=[(2, "sku-1"), (3, "sku-2"), (4, "sku-3")],
                    crawl_func=crawl,
                    recover_login_func=lambda: True,
                    stop_event=threading.Event(),
                    pages=["page-1", "page-2", "page-3"],
                )
            )
        )
        thread.start()
        try:
            self.assertTrue(all_started.wait(timeout=1))
        finally:
            release.set()
        thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(started), 3)
        self.assertEqual({page for page, _, _ in started}, {"page-1", "page-2", "page-3"})
        self.assertEqual(
            sorted((row_index, sku) for _, row_index, sku in started),
            [(2, "sku-1"), (3, "sku-2"), (4, "sku-3")],
        )
        self.assertEqual(len(result_holder[0].results), 3)
        self.assertEqual(
            sorted((result["row_index"], result["sku"]) for result in result_holder[0].results),
            [(2, "sku-1"), (3, "sku-2"), (4, "sku-3")],
        )

    def test_concurrent_runner_retries_same_sku_after_login_recovery(self):
        calls = []
        login_calls = []

        def crawl(page, row_index, sku):
            calls.append((page, row_index, sku))
            if len(calls) == 1:
                return {"sku": sku, "status": "need_login", "message": "need login"}
            return {"sku": sku, "status": "success", "price": 5.5, "message": "ok"}

        result = run_sku_batch_concurrent(
            sku_data=[(2, "100264886683")],
            crawl_func=crawl,
            recover_login_func=lambda: login_calls.append("login") or True,
            stop_event=threading.Event(),
            pages=["page-1"],
        )

        self.assertEqual(calls, [("page-1", 2, "100264886683"), ("page-1", 2, "100264886683")])
        self.assertEqual(login_calls, ["login"])
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0]["status"], "success")
        self.assertEqual(result.results[0]["row_index"], 2)

    def test_concurrent_runner_keeps_workers_running_until_queue_is_empty(self):
        calls = []
        lock = threading.Lock()

        def crawl(page, row_index, sku):
            with lock:
                calls.append((page, row_index, sku))
            return {"sku": sku, "status": "success", "price": 10, "message": "ok"}

        result = run_sku_batch_concurrent(
            sku_data=[(2, "sku-1"), (3, "sku-2"), (4, "sku-3"), (5, "sku-4"), (6, "sku-5")],
            crawl_func=crawl,
            recover_login_func=lambda: True,
            stop_event=threading.Event(),
            pages=["page-1", "page-2", "page-3"],
        )

        self.assertEqual(len(calls), 5)
        self.assertEqual(len(result.results), 5)
        self.assertEqual(
            sorted((result["row_index"], result["sku"]) for result in result.results),
            [(2, "sku-1"), (3, "sku-2"), (4, "sku-3"), (5, "sku-4"), (6, "sku-5")],
        )

    def test_page_factory_runner_creates_resources_inside_workers(self):
        all_started = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        created = []
        closed = []
        calls = []

        def page_factory(worker_index):
            with lock:
                page = f"page-{worker_index}-{len(created)}"
                created.append((worker_index, page))

            def close_page():
                with lock:
                    closed.append(page)

            return page, close_page

        def crawl(page, row_index, sku):
            with lock:
                calls.append((page, row_index, sku))
                if len(calls) == 3:
                    all_started.set()
            release.wait(timeout=2)
            return {"sku": sku, "status": "success", "price": 10, "message": "ok"}

        thread_result = []
        thread = threading.Thread(
            target=lambda: thread_result.append(
                run_sku_batch_with_page_factory(
                    sku_data=[(2, "sku-1"), (3, "sku-2"), (4, "sku-3")],
                    crawl_func=crawl,
                    recover_login_func=lambda: True,
                    stop_event=threading.Event(),
                    page_factory=page_factory,
                    worker_count=3,
                )
            )
        )
        thread.start()
        try:
            self.assertTrue(all_started.wait(timeout=1))
        finally:
            release.set()
        thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(created), 3)
        self.assertEqual(len(closed), 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(thread_result[0].results), 3)

    def test_page_factory_runner_recreates_page_after_login_recovery(self):
        lock = threading.Lock()
        created = []
        closed = []
        calls = []
        login_calls = []

        def page_factory(worker_index):
            with lock:
                page = f"page-{len(created)}"
                created.append(page)

            def close_page():
                with lock:
                    closed.append(page)

            return page, close_page

        def crawl(page, row_index, sku):
            calls.append((page, sku))
            if len(calls) == 1:
                return {"sku": sku, "status": "need_login", "message": "need login"}
            return {"sku": sku, "status": "success", "price": 8, "message": "ok"}

        result = run_sku_batch_with_page_factory(
            sku_data=[(2, "sku-1")],
            crawl_func=crawl,
            recover_login_func=lambda: login_calls.append("login") or True,
            stop_event=threading.Event(),
            page_factory=page_factory,
            worker_count=1,
        )

        self.assertEqual(login_calls, ["login"])
        self.assertEqual(calls, [("page-0", "sku-1"), ("page-1", "sku-1")])
        self.assertEqual(created, ["page-0", "page-1"])
        self.assertEqual(closed, ["page-0", "page-1"])
        self.assertEqual(result.results[0]["status"], "success")

    def test_page_factory_runner_uses_worker_login_recovery_callback(self):
        created = []
        closed = []
        recoveries = []
        global_recoveries = []
        calls = []

        def page_factory(worker_index):
            page = f"page-{len(created)}"
            created.append(page)

            def close_page():
                closed.append(page)

            def recover_page_login():
                recoveries.append(page)
                return True

            return page, close_page, recover_page_login

        def crawl(page, row_index, sku):
            calls.append(page)
            if len(calls) == 1:
                return {"sku": sku, "status": "need_login", "message": "need login"}
            return {"sku": sku, "status": "success", "price": 8, "message": "ok"}

        result = run_sku_batch_with_page_factory(
            sku_data=[(2, "sku-1")],
            crawl_func=crawl,
            recover_login_func=lambda: global_recoveries.append("global") or False,
            stop_event=threading.Event(),
            page_factory=page_factory,
            worker_count=1,
        )

        self.assertEqual(recoveries, ["page-0"])
        self.assertEqual(global_recoveries, [])
        self.assertEqual(calls, ["page-0", "page-1"])
        self.assertEqual(created, ["page-0", "page-1"])
        self.assertEqual(closed, ["page-0", "page-1"])
        self.assertEqual(result.results[0]["status"], "success")

    def test_page_factory_runner_reopens_idle_worker_after_shared_login_recovery(self):
        lock = threading.Lock()
        created = []
        closed = []
        worker_generations = {}
        calls = []
        initial_pages_ready = threading.Event()
        recovery_started = threading.Event()
        after_processed = threading.Event()

        def page_factory(worker_index):
            with lock:
                generation = worker_generations.get(worker_index, 0)
                worker_generations[worker_index] = generation + 1
                page = f"page-{worker_index}-{generation}"
                created.append((worker_index, page))
                if len(created) >= 2:
                    initial_pages_ready.set()

            def close_page():
                with lock:
                    closed.append(page)

            return page, close_page

        def recover_login():
            recovery_started.set()
            return True

        def crawl(page, row_index, sku):
            with lock:
                calls.append((sku, page))
                login_call_count = sum(1 for item_sku, _ in calls if item_sku == "sku-login")

            if sku == "sku-login" and login_call_count == 1:
                self.assertTrue(initial_pages_ready.wait(timeout=2))
                return {"sku": sku, "status": "need_login", "message": "need login"}
            if sku == "sku-login":
                after_processed.wait(timeout=2)
                return {"sku": sku, "status": "success", "price": 8, "message": "ok"}
            if sku == "sku-idle":
                self.assertTrue(recovery_started.wait(timeout=2))
                return {"sku": sku, "status": "success", "price": 9, "message": "ok"}
            if sku == "sku-after":
                after_processed.set()
                return {"sku": sku, "status": "success", "price": 10, "message": "ok"}
            raise AssertionError(f"unexpected sku: {sku}")

        result = run_sku_batch_with_page_factory(
            sku_data=[(2, "sku-login"), (3, "sku-idle"), (4, "sku-after")],
            crawl_func=crawl,
            recover_login_func=recover_login,
            stop_event=threading.Event(),
            page_factory=page_factory,
            worker_count=2,
        )

        self.assertEqual(len(result.results), 3)
        after_page = next(page for sku, page in calls if sku == "sku-after")
        self.assertFalse(after_page.endswith("-0"))
        self.assertIn(after_page.rsplit("-", 1)[0] + "-0", closed)

    def test_page_factory_runner_does_not_create_extra_workers(self):
        created = []

        def page_factory(worker_index):
            created.append(worker_index)
            return f"page-{worker_index}", lambda: None

        result = run_sku_batch_with_page_factory(
            sku_data=[(2, "sku-1")],
            crawl_func=lambda page, row_index, sku: {
                "sku": sku,
                "status": "success",
                "price": 8,
                "message": "ok",
            },
            recover_login_func=lambda: True,
            stop_event=threading.Event(),
            page_factory=page_factory,
            worker_count=3,
        )

        self.assertEqual(created, [0])
        self.assertEqual(len(result.results), 1)

    def test_page_factory_runner_returns_promptly_when_stop_requested_during_blocked_crawl(self):
        stop_event = threading.Event()
        crawl_started = threading.Event()
        release_crawl = threading.Event()
        result_holder = []

        def crawl(page, row_index, sku):
            crawl_started.set()
            release_crawl.wait(timeout=2)
            return {"sku": sku, "status": "success", "price": 8, "message": "ok"}

        runner_thread = threading.Thread(
            target=lambda: result_holder.append(
                run_sku_batch_with_page_factory(
                    sku_data=[(2, "sku-1")],
                    crawl_func=crawl,
                    recover_login_func=lambda: True,
                    stop_event=stop_event,
                    page_factory=lambda worker_index: (f"page-{worker_index}", lambda: None),
                    worker_count=1,
                )
            )
        )
        runner_thread.start()
        self.assertTrue(crawl_started.wait(timeout=1))

        stop_event.set()
        try:
            runner_thread.join(timeout=0.3)
            self.assertFalse(runner_thread.is_alive())
            self.assertTrue(result_holder[0].stopped)
            self.assertEqual(result_holder[0].results, [])
        finally:
            release_crawl.set()
            runner_thread.join(timeout=2)

    def test_page_factory_runner_surfaces_worker_start_errors(self):
        def page_factory(worker_index):
            raise RuntimeError("browser failed")

        with self.assertRaisesRegex(RuntimeError, "browser failed"):
            run_sku_batch_with_page_factory(
                sku_data=[(2, "sku-1")],
                crawl_func=lambda page, row_index, sku: {
                    "sku": sku,
                    "status": "success",
                    "price": 8,
                    "message": "ok",
                },
                recover_login_func=lambda: True,
                stop_event=threading.Event(),
                page_factory=page_factory,
                worker_count=3,
            )

    def test_page_bound_runner_uses_same_page_serially_and_preserves_login_retry(self):
        calls = []
        login_calls = []

        def crawl(page, row_index, sku):
            calls.append((page, row_index, sku))
            if len(calls) == 1:
                return {"sku": sku, "status": "need_login", "message": "need login"}
            return {"sku": sku, "status": "success", "price": 5.5, "message": "ok"}

        result = run_sku_batch_on_page(
            sku_data=[(2, "sku-1"), (3, "sku-2")],
            crawl_func=crawl,
            recover_login_func=lambda: login_calls.append("login") or True,
            stop_event=threading.Event(),
            page="sync-playwright-page",
        )

        self.assertEqual(
            calls,
            [
                ("sync-playwright-page", 2, "sku-1"),
                ("sync-playwright-page", 2, "sku-1"),
                ("sync-playwright-page", 3, "sku-2"),
            ],
        )
        self.assertEqual(login_calls, ["login"])
        self.assertEqual(len(result.results), 2)
        self.assertEqual([item["row_index"] for item in result.results], [2, 3])


if __name__ == "__main__":
    unittest.main()
