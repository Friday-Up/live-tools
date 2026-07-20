"""红包雨创建数据校验。"""

from datetime import datetime
from typing import Dict, Iterable, List, Set, Tuple

from . import config
from .models import RedRainRow


def validate_row(row: RedRainRow, now: datetime = None) -> List[str]:
    errors = []
    if not row.activity_name:
        errors.append("活动名称为空")
    elif len(row.activity_name) > config.ACTIVITY_NAME_MAX_LENGTH:
        errors.append(f"活动名称超过 {config.ACTIVITY_NAME_MAX_LENGTH} 个字")
    if row.end_time <= row.start_time:
        errors.append("结束时间必须晚于开始时间")
    reference_now = now or datetime.now()
    if row.end_time <= reference_now:
        errors.append("活动结束时间必须晚于当前时间")
    if row.issue_method not in config.VALID_ISSUE_METHODS:
        errors.append("红包发放方式必须为普通发放或按人群策略发放")
    if not row.red_packet_id:
        errors.append("红包ID为空")
    if row.issue_method == config.ISSUE_METHOD_NORMAL:
        if row.win_probability is None:
            errors.append("普通发放必须填写中奖概率")
        elif not config.PROBABILITY_MIN <= row.win_probability <= config.PROBABILITY_MAX:
            errors.append("中奖概率必须为 1～100 的整数")
    elif row.issue_method == config.ISSUE_METHOD_AUDIENCE and row.win_probability is not None:
        errors.append("按人群策略发放时中奖概率应留空")
    return errors


def find_duplicates(rows: Iterable[RedRainRow]) -> Set[int]:
    seen = set()
    duplicates = set()
    for row in rows:
        key = (
            row.activity_name,
            row.start_time,
            row.end_time,
            row.issue_method,
            row.red_packet_id,
            row.win_probability,
        )
        if key in seen:
            duplicates.add(row.row_index)
        else:
            seen.add(key)
    return duplicates


def find_duplicate_red_packet_ids(rows: Iterable[RedRainRow]) -> Set[int]:
    seen = set()
    duplicates = set()
    for row in rows:
        if row.red_packet_id in seen:
            duplicates.add(row.row_index)
        elif row.red_packet_id:
            seen.add(row.red_packet_id)
    return duplicates


def find_overlaps(rows: Iterable[RedRainRow]) -> Set[int]:
    ordered = sorted(rows, key=lambda item: (item.start_time, item.end_time, item.row_index))
    overlaps = set()
    for index, current in enumerate(ordered):
        for candidate in ordered[index + 1 :]:
            if candidate.start_time >= current.end_time:
                break
            if candidate.end_time > current.start_time:
                overlaps.add(current.row_index)
                overlaps.add(candidate.row_index)
    return overlaps
