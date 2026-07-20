import tempfile
import unittest
from datetime import datetime

from openpyxl import load_workbook

from red_rain_creator.models import BatchResult, RedRainResult
from red_rain_creator.report_writer import write_batch_report


class ReportWriterTest(unittest.TestCase):
    def test_writes_status_and_activity_id(self):
        result = BatchResult(
            results=[
                RedRainResult(2, "晚场红包雨", datetime(2099, 1, 1, 20), datetime(2099, 1, 1, 20, 10), "普通发放", "123", 50, status="成功", activity_id="A100")
            ]
        )
        with tempfile.TemporaryDirectory() as output_dir:
            path = write_batch_report(result, output_dir)
            workbook = load_workbook(path, data_only=True)
            try:
                sheet = workbook.active
                self.assertEqual(sheet["H2"].value, "成功")
                self.assertEqual(sheet["I2"].value, "A100")
            finally:
                workbook.close()


if __name__ == "__main__":
    unittest.main()
