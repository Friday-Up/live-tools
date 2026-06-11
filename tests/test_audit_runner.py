import threading
import unittest

from utils.audit_runner import run_sku_batch


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


if __name__ == "__main__":
    unittest.main()
