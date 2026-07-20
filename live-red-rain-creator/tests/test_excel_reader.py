import os
import tempfile
import unittest
from datetime import datetime

from openpyxl import Workbook

from red_rain_creator.excel_reader import inspect_workbook, read_rows, read_rows_with_errors


class ExcelReaderTest(unittest.TestCase):
    def _workbook(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["活动名称", "开始时间", "结束时间", "红包发放方式", "红包ID", "中奖概率"])
        sheet.append(["晚场红包雨", "2099-07-20 20:00:00", "2099-07-20 20:10:00", "普通发放", "123456", 50])
        sheet.append(["会员红包雨", datetime(2099, 7, 20, 21), datetime(2099, 7, 20, 21, 10), "按人群策略发放", "654321", None])
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        workbook.save(path)
        workbook.close()
        return path

    def test_inspects_and_reads_rows(self):
        path = self._workbook()
        try:
            mapping, headers = inspect_workbook(path)
            self.assertTrue(mapping.is_valid())
            self.assertEqual(headers[0], "活动名称")
            rows = read_rows(path, mapping)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0].win_probability, 50)
            self.assertIsNone(rows[1].win_probability)
            self.assertEqual(rows[1].issue_method, "按人群策略发放")
        finally:
            os.unlink(path)

    def test_collects_bad_rows_without_aborting_valid_rows(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["活动名称", "开始时间", "结束时间", "红包发放方式", "红包ID", "中奖概率"])
        sheet.append(["坏行", "not-a-time", "2099-07-20 20:10:00", "普通发放", "bad", 50])
        sheet.append(["正常行", "2099-07-20 21:00:00", "2099-07-20 21:10:00", "普通发放", "good", 50])
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        workbook.save(path)
        workbook.close()
        try:
            mapping, _ = inspect_workbook(path)
            rows, rejected = read_rows_with_errors(path, mapping)

            self.assertEqual([row.activity_name for row in rows], ["正常行"])
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0].row_index, 2)
            self.assertEqual(rejected[0].status, "跳过")
            self.assertIn("开始时间格式无法识别", rejected[0].error)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
