import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from red_rain_creator.browser import RedRainCreatorBrowser
from red_rain_creator.models import RedRainRow


class FakePage:
    def wait_for_timeout(self, _milliseconds):
        return None


class PendingSubmissionBrowser(RedRainCreatorBrowser):
    def __init__(self, guard_file):
        super().__init__(guard_file=guard_file)
        self._page = FakePage()
        self.submit_count = 0

    def find_existing_activity(self, _row):
        return False, ""

    def open_create_dialog(self):
        return None

    def fill_form(self, _row):
        return None

    def submit(self, row):
        self.submit_count += 1
        self._mark_guard(row, "submitting")

    def close_dialog(self):
        return None

    def is_login_required(self):
        return False


class BrowserGuardTest(unittest.TestCase):
    def test_existing_match_requires_exact_start_and_end_time(self):
        browser = RedRainCreatorBrowser()
        row = RedRainRow(
            2,
            "晚场红包雨",
            datetime(2099, 1, 1, 20),
            datetime(2099, 1, 1, 20, 10),
            "普通发放",
            "123",
            50,
        )
        headers = ["序号", "活动ID", "活动名称", "活动时间", "红包ID"]
        exact_cells = ["1", "A100", "晚场红包雨", "2099-01-01 20:00:00 至 2099-01-01 20:10:00", "123"]
        other_time_cells = ["1", "A101", "晚场红包雨", "2099-01-01 20:01:00 至 2099-01-01 20:10:00", "123"]

        self.assertEqual(browser._match_activity_cells(headers, exact_cells, row), (True, "A100"))
        self.assertEqual(browser._match_activity_cells(headers, other_time_cells, row), (False, ""))

    def test_pending_submission_is_not_submitted_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            browser = PendingSubmissionBrowser(Path(temp_dir) / "guard.json")
            row = RedRainRow(
                2,
                "晚场红包雨",
                datetime(2099, 1, 1, 20),
                datetime(2099, 1, 1, 20, 10),
                "普通发放",
                "123",
                50,
            )

            first = browser.create_activity(row)
            second = browser.create_activity(row)

            self.assertEqual(first.status, "待确认")
            self.assertEqual(second.status, "待确认")
            self.assertEqual(browser.submit_count, 1)
            self.assertIn("防止重复创建", second.error)


if __name__ == "__main__":
    unittest.main()
