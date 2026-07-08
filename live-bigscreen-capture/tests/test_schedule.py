import unittest
from datetime import date, datetime

from bigscreen_capture.schedule import build_hour_options, build_planned_slots


class BigscreenScheduleTest(unittest.TestCase):
    def test_build_hour_options_returns_whole_hours(self):
        options = build_hour_options(start_hour=12, end_hour=23)

        self.assertEqual(options[0], "12:00")
        self.assertEqual(options[-1], "23:00")
        self.assertEqual(len(options), 12)

    def test_build_planned_slots_marks_past_slots(self):
        now = datetime(2026, 7, 8, 18, 35, 0)

        slots = build_planned_slots(
            capture_date=date(2026, 7, 8),
            hour_labels=["18:00", "19:00"],
            now=now,
        )

        self.assertEqual(slots[0].label, "18:00")
        self.assertEqual(slots[0].status, "missed")
        self.assertEqual(slots[1].label, "19:00")
        self.assertEqual(slots[1].status, "pending")


if __name__ == "__main__":
    unittest.main()
