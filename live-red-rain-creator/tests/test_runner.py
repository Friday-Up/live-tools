import unittest
import threading
from datetime import datetime

from red_rain_creator.browser import LoginRequiredError
from red_rain_creator.models import RedRainResult, RedRainRow
from red_rain_creator.runner import BatchRunner


class FakeBrowser:
    def __init__(self):
        self.rows = []

    def create_activity(self, row):
        self.rows.append(row)
        status = "已存在" if row.red_packet_id == "old" else "待确认" if row.red_packet_id == "pending" else "成功"
        return RedRainResult.from_row(row, status=status, activity_id="A1")


class LoginFlakyBrowser(FakeBrowser):
    def create_activity(self, row):
        self.rows.append(row)
        if len(self.rows) == 1:
            raise LoginRequiredError("京东登录态已失效")
        return RedRainResult.from_row(row, status="成功", activity_id="A2")


class RunnerTest(unittest.TestCase):
    def test_counts_created_and_existing(self):
        rows = [
            RedRainRow(2, "第一场红包雨", datetime(2099, 1, 1, 20), datetime(2099, 1, 1, 20, 10), "普通发放", "new", 50),
            RedRainRow(3, "第二场红包雨", datetime(2099, 1, 1, 21), datetime(2099, 1, 1, 21, 10), "普通发放", "old", 50),
        ]
        result = BatchRunner(FakeBrowser()).run_batch(rows)
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.existed_count, 1)

    def test_stop_marks_unprocessed_rows_as_skipped(self):
        stop_event = threading.Event()
        stop_event.set()
        browser = FakeBrowser()
        runner = BatchRunner(browser, stop_event=stop_event)
        rows = [
            RedRainRow(2, "红包雨A", datetime(2099, 1, 1, 20), datetime(2099, 1, 1, 20, 10), "普通发放", "new-a", 50),
            RedRainRow(3, "红包雨B", datetime(2099, 1, 1, 21), datetime(2099, 1, 1, 21, 10), "普通发放", "new-b", 50),
        ]

        result = runner.run_batch(rows)

        self.assertTrue(result.stopped_by_user)
        self.assertEqual(result.skipped_count, 2)
        self.assertEqual([item.status for item in result.results], ["跳过", "跳过"])
        self.assertEqual(browser.rows, [])
        self.assertEqual(result.failed_count, 0)

    def test_recovers_login_and_retries_current_row(self):
        browser = LoginFlakyBrowser()
        login_calls = []
        runner = BatchRunner(
            browser,
            login_callback=lambda: login_calls.append("login") or True,
        )
        row = RedRainRow(2, "红包雨A", datetime(2099, 1, 1, 20), datetime(2099, 1, 1, 20, 10), "普通发放", "new-a", 50)

        result = runner.run_batch([row])

        self.assertEqual(login_calls, ["login"])
        self.assertEqual(len(browser.rows), 2)
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.failed_count, 0)

    def test_pending_is_counted_separately_from_failure(self):
        row = RedRainRow(2, "红包雨A", datetime(2099, 1, 1, 20), datetime(2099, 1, 1, 20, 10), "普通发放", "pending", 50)

        result = BatchRunner(FakeBrowser()).run_batch([row])

        self.assertEqual(result.pending_count, 1)
        self.assertEqual(result.failed_count, 0)


if __name__ == "__main__":
    unittest.main()
