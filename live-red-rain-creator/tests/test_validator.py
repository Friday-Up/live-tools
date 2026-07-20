import unittest
from datetime import datetime, timedelta

from red_rain_creator.models import RedRainRow
from red_rain_creator.validator import find_duplicate_red_packet_ids, find_overlaps, validate_row


class ValidatorTest(unittest.TestCase):
    def row(self, **overrides):
        values = {
            "row_index": 2,
            "activity_name": "晚场红包雨",
            "start_time": datetime(2099, 7, 20, 20),
            "end_time": datetime(2099, 7, 20, 20, 10),
            "issue_method": "普通发放",
            "red_packet_id": "123456",
            "win_probability": 50,
        }
        values.update(overrides)
        return RedRainRow(**values)

    def test_normal_and_audience_probability_rules(self):
        self.assertEqual(validate_row(self.row(), now=datetime(2099, 7, 1)), [])
        self.assertTrue(any("中奖概率" in item for item in validate_row(self.row(win_probability=None), now=datetime(2099, 7, 1))))
        audience = self.row(issue_method="按人群策略发放", win_probability=None)
        self.assertEqual(validate_row(audience, now=datetime(2099, 7, 1)), [])
        audience.win_probability = 10
        self.assertTrue(any("应留空" in item for item in validate_row(audience, now=datetime(2099, 7, 1))))

    def test_detects_overlap_and_duplicate_red_packet_id(self):
        first = self.row()
        second = self.row(
            row_index=3,
            activity_name="第二场红包雨",
            start_time=datetime(2099, 7, 20, 20, 5),
            end_time=datetime(2099, 7, 20, 20, 15),
            red_packet_id="123456",
        )
        self.assertEqual(find_overlaps([first, second]), {2, 3})
        self.assertEqual(find_duplicate_red_packet_ids([first, second]), {3})


if __name__ == "__main__":
    unittest.main()
