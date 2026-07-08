from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True)
class PlannedSlot:
    label: str
    run_at: datetime
    status: str


def build_hour_options(start_hour=0, end_hour=23):
    return ["%02d:00" % hour for hour in range(start_hour, end_hour + 1)]


def build_planned_slots(capture_date, hour_labels, now=None):
    current = now or datetime.now()
    slots = []
    for label in hour_labels:
        hour, minute = [int(part) for part in label.split(":", 1)]
        run_at = datetime.combine(capture_date, time(hour=hour, minute=minute))
        status = "missed" if run_at < current else "pending"
        slots.append(PlannedSlot(label=label, run_at=run_at, status=status))
    return slots
