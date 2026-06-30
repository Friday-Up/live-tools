"""数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RoomCreateRow:
    """一行待创建的直播间数据。"""

    row_index: int  # Excel 中的原始行号（1-based）
    title: str
    start_time: datetime
    cover: str = ""
    live_form: str = "正式直播"
    live_direction: str = "竖屏"
    live_location: str = "不显示地点"
    live_category: str = "多品类"


@dataclass
class RoomCreateResult:
    """单个直播间的创建结果。"""

    row_index: int
    title: str
    start_time: datetime
    live_form: str
    live_direction: str
    live_location: str
    live_category: str
    success: bool = False
    error: Optional[str] = None


@dataclass
class BatchResult:
    """批次创建结果。"""

    results: list[RoomCreateResult] = field(default_factory=list)
    created_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    stopped_by_limit: bool = False
    stopped_by_user: bool = False
    error: Optional[str] = None
