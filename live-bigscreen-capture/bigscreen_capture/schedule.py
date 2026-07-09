from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass(frozen=True)
class PlannedSlot:
    label: str
    run_at: datetime
    status: str


def build_hour_options(start_hour=0, end_hour=23, interval_minutes=60):
    start_total = start_hour * 60
    end_total = end_hour * 60
    options = []
    current = start_total
    while current <= end_total:
        hour, minute = divmod(current, 60)
        options.append("%02d:%02d" % (hour, minute))
        current += interval_minutes
    return options


def build_planned_slots(capture_date, hour_labels, now=None):
    current = now or datetime.now()
    slots = []
    for label in hour_labels:
        hour, minute = [int(part) for part in label.split(":", 1)]
        if hour == 24 and minute == 0:
            run_at = datetime.combine(capture_date + timedelta(days=1), time(hour=0, minute=0))
        else:
            run_at = datetime.combine(capture_date, time(hour=hour, minute=minute))
        status = "missed" if run_at < current else "pending"
        slots.append(PlannedSlot(label=label, run_at=run_at, status=status))
    return slots
