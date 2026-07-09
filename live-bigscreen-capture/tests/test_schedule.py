import unittest
from datetime import date, datetime

from bigscreen_capture.schedule import build_hour_options, build_planned_slots


class BigscreenScheduleTest(unittest.TestCase):
    def test_build_hour_options_returns_half_hour_points_from_10_to_24(self):
        options = build_hour_options(start_hour=10, end_hour=24, interval_minutes=30)

        self.assertEqual(options[0], "10:00")
        self.assertEqual(options[1], "10:30")
        self.assertEqual(options[-2], "23:30")
        self.assertEqual(options[-1], "24:00")
        self.assertEqual(len(options), 29)

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

    def test_build_planned_slots_supports_half_hour_slots(self):
        now = datetime(2026, 7, 8, 10, 15, 0)

        slots = build_planned_slots(
            capture_date=date(2026, 7, 8),
            hour_labels=["10:00", "10:30"],
            now=now,
        )

        self.assertEqual(slots[0].run_at, datetime(2026, 7, 8, 10, 0, 0))
        self.assertEqual(slots[0].status, "missed")
        self.assertEqual(slots[1].run_at, datetime(2026, 7, 8, 10, 30, 0))
        self.assertEqual(slots[1].status, "pending")

    def test_build_planned_slots_treats_24_as_next_day_midnight(self):
        now = datetime(2026, 7, 8, 23, 30, 0)

        slots = build_planned_slots(
            capture_date=date(2026, 7, 8),
            hour_labels=["24:00"],
            now=now,
        )

        self.assertEqual(slots[0].label, "24:00")
        self.assertEqual(slots[0].run_at, datetime(2026, 7, 9, 0, 0, 0))
        self.assertEqual(slots[0].status, "pending")


if __name__ == "__main__":
    unittest.main()
