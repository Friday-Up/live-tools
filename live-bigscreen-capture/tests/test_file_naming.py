import unittest
from datetime import datetime

from bigscreen_capture.file_naming import screenshot_filename, zip_filename


class FileNamingTest(unittest.TestCase):
    def test_screenshot_filename_uses_required_format(self):
        name = screenshot_filename(
            room_id="46794566",
            captured_at=datetime(2026, 7, 8, 19, 0, 0),
            step_code="02",
            label="渠道流量饼状图_在线",
        )

        self.assertEqual(
            name,
            "蓝屏数据截图_46794566__20260708_190000_02_渠道流量饼状图_在线.png",
        )

    def test_zip_filename_uses_date(self):
        self.assertEqual(
            zip_filename("46794566", datetime(2026, 7, 8, 19, 0, 0)),
            "蓝屏数据截图_46794566__20260708.zip",
        )


if __name__ == "__main__":
    unittest.main()
