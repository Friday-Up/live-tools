"""测试 Excel 读取与列映射。"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from room_creator.excel_reader import (
    ColumnMapping,
    inspect_workbook,
    read_room_rows,
)


def _make_workbook(data: list[list], headers: list[str]) -> Path:
    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("no active sheet")
    ws.append(headers)
    for row in data:
        ws.append(row)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    wb.close()
    return Path(path)


class TestInspectWorkbook(unittest.TestCase):
    def test_recommends_required_columns(self):
        path = _make_workbook(
            [["测试直播", "2026-07-01 20:00:00"]],
            ["直播标题", "开播时间"],
        )
        mapping, headers = inspect_workbook(path)
        self.assertEqual(mapping.title_col, "直播标题")
        self.assertEqual(mapping.start_time_col, "开播时间")
        self.assertIsNone(mapping.cover_col)
        self.assertEqual(headers, ["直播标题", "开播时间"])
        path.unlink()

    def test_supports_aliases(self):
        path = _make_workbook(
            [["测试", "2026-07-01 20:00:00", "正式直播", "竖屏", "不显示地点", "多品类"]],
            ["标题", "开始时间", "形式", "方向", "地点", "品类"],
        )
        mapping, _ = inspect_workbook(path)
        self.assertEqual(mapping.title_col, "标题")
        self.assertEqual(mapping.start_time_col, "开始时间")
        self.assertEqual(mapping.live_form_col, "形式")
        self.assertEqual(mapping.live_direction_col, "方向")
        self.assertEqual(mapping.live_location_col, "地点")
        self.assertEqual(mapping.live_category_col, "品类")
        path.unlink()


class TestReadRoomRows(unittest.TestCase):
    def test_reads_rows_with_defaults(self):
        path = _make_workbook(
            [
                ["直播间一号", "2026-07-01 20:00:00"],
                ["直播间二号", "2026/07/02 21:30"],
            ],
            ["直播标题", "开播时间"],
        )
        mapping = ColumnMapping(title_col="直播标题", start_time_col="开播时间")
        rows = read_room_rows(path, mapping)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].title, "直播间一号")
        self.assertEqual(rows[0].start_time, datetime(2026, 7, 1, 20, 0, 0))
        self.assertEqual(rows[0].live_form, "正式直播")
        self.assertEqual(rows[0].live_direction, "竖屏")
        self.assertEqual(rows[1].start_time, datetime(2026, 7, 2, 21, 30, 0))
        path.unlink()

    def test_ignores_empty_rows(self):
        path = _make_workbook(
            [
                ["直播间一号", "2026-07-01 20:00:00"],
                ["", ""],
                ["直播间三号", "2026-07-03 20:00:00"],
            ],
            ["直播标题", "开播时间"],
        )
        mapping = ColumnMapping(title_col="直播标题", start_time_col="开播时间")
        rows = read_room_rows(path, mapping)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1].title, "直播间三号")
        path.unlink()

    def test_raises_on_invalid_datetime(self):
        path = _make_workbook(
            [["直播间一号", "不是时间"]],
            ["直播标题", "开播时间"],
        )
        mapping = ColumnMapping(title_col="直播标题", start_time_col="开播时间")
        with self.assertRaises(ValueError):
            read_room_rows(path, mapping)
        path.unlink()

    def test_reads_various_datetime_formats(self):
        path = _make_workbook(
            [
                ["直播间1", "2026-07-01 20:00:00"],
                ["直播间2", "2026/9/2 21:30"],
                ["直播间3", "2026年9月2日 21:30"],
                ["直播间4", "2026.09.02 21:30:00"],
            ],
            ["直播标题", "开播时间"],
        )
        mapping = ColumnMapping(title_col="直播标题", start_time_col="开播时间")
        rows = read_room_rows(path, mapping)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].start_time, datetime(2026, 7, 1, 20, 0, 0))
        self.assertEqual(rows[1].start_time, datetime(2026, 9, 2, 21, 30, 0))
        self.assertEqual(rows[2].start_time, datetime(2026, 9, 2, 21, 30, 0))
        self.assertEqual(rows[3].start_time, datetime(2026, 9, 2, 21, 30, 0))
        path.unlink()

    def test_reads_all_mapped_columns(self):
        """完整列映射下应读取直播形式/方向/地点/品类，而不是使用默认值。"""
        path = _make_workbook(
            [
                ["直播间一号", "2026-07-01 20:00:00", "", "正式直播", "竖屏", "不显示地点", "多品类"],
                ["直播间二号", "2026/7/21 20:00", "", "测试直播", "横屏", "不显示地点", "多品类"],
                ["直播间三号", "2026/7/21 20:00", "", "测试直播", "横屏", "不显示地点", "母婴"],
                ["直播间四号", "2026/7/21 20:00", "", "正式直播", "竖屏", "不显示地点", "美妆"],
            ],
            ["直播标题", "开播时间", "直播封面", "直播形式", "画面方向", "直播地点", "直播品类"],
        )
        mapping = ColumnMapping(
            title_col="直播标题",
            start_time_col="开播时间",
            cover_col="直播封面",
            live_form_col="直播形式",
            live_direction_col="画面方向",
            live_location_col="直播地点",
            live_category_col="直播品类",
        )
        rows = read_room_rows(path, mapping)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].live_form, "正式直播")
        self.assertEqual(rows[0].live_direction, "竖屏")
        self.assertEqual(rows[0].live_category, "多品类无法确定品类选此项")
        self.assertEqual(rows[1].live_form, "测试直播")
        self.assertEqual(rows[1].live_direction, "横屏")
        self.assertEqual(rows[1].live_category, "多品类无法确定品类选此项")
        self.assertEqual(rows[2].live_category, "母婴")
        self.assertEqual(rows[3].live_category, "美妆")
        path.unlink()


if __name__ == "__main__":
    unittest.main()
