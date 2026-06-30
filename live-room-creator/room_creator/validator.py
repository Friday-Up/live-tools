"""校验每一行数据是否满足京东直播后台要求。"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .models import RoomCreateRow


def _normalize_category(value: str) -> str:
    return config.CATEGORY_OPTION_MAP.get(value, value)


def validate_row(row: RoomCreateRow) -> list[str]:
    """返回该行所有校验错误信息；无错误返回空列表。"""
    errors: list[str] = []

    if not row.title:
        errors.append("直播标题为空")
    elif len(row.title) < config.TITLE_MIN_LENGTH:
        errors.append(f"直播标题长度不足 {config.TITLE_MIN_LENGTH} 个字符")
    elif len(row.title) > config.TITLE_MAX_LENGTH:
        errors.append(f"直播标题超过 {config.TITLE_MAX_LENGTH} 个字符")

    if not row.start_time:
        errors.append("开播时间为空")
    else:
        now = datetime.now()
        if row.start_time <= now + timedelta(minutes=1):
            errors.append("开播时间必须至少晚于当前时间 1 分钟")
        if row.start_time > now + timedelta(days=30):
            errors.append("开播时间不能超过当前时间 30 天")

    if row.live_form not in config.VALID_LIVE_FORMS:
        errors.append(f"直播形式必须是 {' / '.join(config.VALID_LIVE_FORMS)}")

    if row.live_direction not in config.VALID_LIVE_DIRECTIONS:
        errors.append(f"画面方向必须是 {' / '.join(config.VALID_LIVE_DIRECTIONS)}")

    if row.live_location not in config.VALID_LIVE_LOCATIONS:
        errors.append(f"直播地点必须是 {' / '.join(config.VALID_LIVE_LOCATIONS)}")

    normalized_category = _normalize_category(row.live_category)
    if normalized_category not in config.VALID_LIVE_CATEGORIES:
        errors.append(f"直播品类暂只支持 {' / '.join(config.VALID_LIVE_CATEGORIES)}")

    return errors


def find_duplicates(rows: list[RoomCreateRow]) -> set[int]:
    """返回重复（标题+开播时间）的原始行号集合。"""
    seen: dict[tuple[str, str], int] = {}
    duplicates: set[int] = set()
    for row in rows:
        key = (row.title, row.start_time.strftime("%Y-%m-%d %H:%M:%S"))
        if key in seen:
            duplicates.add(row.row_index)
        else:
            seen[key] = row.row_index
    return duplicates
