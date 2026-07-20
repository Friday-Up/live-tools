"""红包雨创建数据模型。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional


@dataclass
class RedRainRow:
    row_index: int
    activity_name: str
    start_time: datetime
    end_time: datetime
    issue_method: str
    red_packet_id: str
    win_probability: Optional[int] = None


@dataclass
class RedRainResult:
    row_index: int
    activity_name: str
    start_time: Any
    end_time: Any
    issue_method: str
    red_packet_id: str
    win_probability: Optional[int]
    status: str = "失败"
    activity_id: str = ""
    error: str = ""

    @classmethod
    def from_row(cls, row: RedRainRow, **kwargs):
        return cls(
            row_index=row.row_index,
            activity_name=row.activity_name,
            start_time=row.start_time,
            end_time=row.end_time,
            issue_method=row.issue_method,
            red_packet_id=row.red_packet_id,
            win_probability=row.win_probability,
            **kwargs,
        )


@dataclass
class BatchResult:
    results: List[RedRainResult] = field(default_factory=list)
    created_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    existed_count: int = 0
    pending_count: int = 0
    stopped_by_user: bool = False
    error: str = ""
