from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ParsedBigscreenUrl:
    url: str
    room_id: str


@dataclass(frozen=True)
class CaptureStep:
    code: str
    name: str
    page: str
    action: str
    filename_label: str


@dataclass
class CaptureRecord:
    planned_slot: str
    executed_at: Optional[datetime]
    room_id: str
    step_code: str
    step_name: str
    filename: str
    status: str
    error: str = ""
    path: Optional[Path] = None
