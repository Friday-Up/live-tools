"""测试批量创建任务编排。"""
from __future__ import annotations

import threading
import unittest
from datetime import datetime

from room_creator.browser import DailyLimitReachedError
from room_creator.models import RoomCreateRow, RoomCreateResult
from room_creator.runner import BatchRunner


class FakeBrowser:
    """模拟浏览器，第 2 行触发日创建上限。"""
    def __init__(self):
        self.calls = 0

    def create_room(self, row: RoomCreateRow) -> RoomCreateResult:
        self.calls += 1
        if self.calls == 2:
            raise DailyLimitReachedError("已达当日创建场次上限30场，请明日再来试试~")
        return RoomCreateResult(
            row_index=row.row_index,
            title=row.title,
            start_time=row.start_time,
            live_form=row.live_form,
            live_direction=row.live_direction,
            live_location=row.live_location,
            live_category=row.live_category,
            success=True,
        )


class TestBatchRunner(unittest.TestCase):
    def test_stops_batch_when_daily_limit_reached(self):
        browser = FakeBrowser()
        runner = BatchRunner(browser=browser, stop_event=threading.Event())

        rows = [
            RoomCreateRow(row_index=2, title="直播间一号", start_time=datetime(2026, 7, 1, 20, 0, 0)),
            RoomCreateRow(row_index=3, title="直播间二号", start_time=datetime(2026, 7, 2, 20, 0, 0)),
            RoomCreateRow(row_index=4, title="直播间三号", start_time=datetime(2026, 7, 3, 20, 0, 0)),
        ]

        result = runner.run_batch(rows)

        self.assertTrue(result.stopped_by_limit)
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(len(result.results), 3)
        self.assertTrue(result.results[0].success)
        self.assertFalse(result.results[1].success)
        self.assertIn("上限", result.results[1].error)
        self.assertFalse(result.results[2].success)
        self.assertIn("未执行", result.results[2].error)
        self.assertIn("30", result.error or "")

if __name__ == "__main__":
    unittest.main()
