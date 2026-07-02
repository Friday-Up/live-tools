"""测试数据校验。"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from room_creator.models import RoomCreateRow
from room_creator.validator import find_duplicates, validate_row


class TestValidateRow(unittest.TestCase):
    def test_valid_row(self):
        row = RoomCreateRow(
            row_index=2,
            title="直播间一号",
            start_time=datetime.now() + timedelta(hours=1),
        )
        self.assertEqual(validate_row(row), [])

    def test_title_too_short(self):
        row = RoomCreateRow(
            row_index=2,
            title="直播",
            start_time=datetime.now() + timedelta(hours=1),
        )
        errors = validate_row(row)
        self.assertTrue(any("长度不足" in e for e in errors))

    def test_title_too_long(self):
        row = RoomCreateRow(
            row_index=2,
            title="这是一个非常长的直播间标题啊啊啊",
            start_time=datetime(2026, 7, 1, 20, 0, 0),
        )
        errors = validate_row(row)
        self.assertTrue(any("超过" in e for e in errors))

    def test_invalid_live_form(self):
        row = RoomCreateRow(
            row_index=2,
            title="直播间一号",
            start_time=datetime(2026, 7, 1, 20, 0, 0),
            live_form="彩排",
        )
        errors = validate_row(row)
        self.assertTrue(any("直播形式" in e for e in errors))

    def test_invalid_direction(self):
        row = RoomCreateRow(
            row_index=2,
            title="直播间一号",
            start_time=datetime(2026, 7, 1, 20, 0, 0),
            live_direction="全屏",
        )
        errors = validate_row(row)
        self.assertTrue(any("画面方向" in e for e in errors))

    def test_start_time_in_past(self):
        row = RoomCreateRow(
            row_index=2,
            title="直播间一号",
            start_time=datetime(2020, 1, 1, 20, 0, 0),
        )
        errors = validate_row(row)
        self.assertTrue(any("开播时间" in e and "当前" in e for e in errors))


class TestFindDuplicates(unittest.TestCase):
    def test_finds_duplicate(self):
        rows = [
            RoomCreateRow(row_index=2, title="直播间一号", start_time=datetime(2026, 7, 1, 20, 0, 0)),
            RoomCreateRow(row_index=3, title="直播间一号", start_time=datetime(2026, 7, 1, 20, 0, 0)),
            RoomCreateRow(row_index=4, title="直播间二号", start_time=datetime(2026, 7, 1, 20, 0, 0)),
        ]
        duplicates = find_duplicates(rows)
        self.assertEqual(duplicates, {3})


if __name__ == "__main__":
    unittest.main()
