from __future__ import annotations

"""Parse promotion binding values from business spreadsheet cells."""

from dataclasses import dataclass
from enum import Enum
import re


class IssueType(str, Enum):
    INVALID_CODE = "INVALID_CODE"
    MULTIPLE_KEYS = "MULTIPLE_KEYS"
    MULTIPLE_PROMO_IDS = "MULTIPLE_PROMO_IDS"
    KEY_PROMO_CONFLICT = "KEY_PROMO_CONFLICT"


@dataclass(frozen=True)
class ParsedCode:
    keys: list[str]
    promo_ids: list[str]
    issues: list[IssueType]


KEY_RE = re.compile(r"vender[_\s-]*BA\s*#\s*([A-Za-z0-9]{32})", re.IGNORECASE)
PROMO_ID_RE = re.compile(r"(?<!\d)(\d{10,})(?!\d)")


def _normalize_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _extract_keys(text: str) -> tuple[list[str], str]:
    keys = []
    remaining_parts = []
    last_end = 0

    for match in KEY_RE.finditer(text):
        keys.append(f"vender_BA#{match.group(1)}")
        start, end = match.span()
        remaining_parts.append(text[last_end:start])
        last_end = end

    remaining_parts.append(text[last_end:])
    return keys, " ".join(remaining_parts)


def parse_code_cell(value) -> ParsedCode:
    text = _normalize_cell(value)
    if not text:
        return ParsedCode(keys=[], promo_ids=[], issues=[])

    keys, text_without_keys = _extract_keys(text)
    promo_ids = PROMO_ID_RE.findall(text_without_keys)

    issues = []
    if len(keys) > 1:
        issues.append(IssueType.MULTIPLE_KEYS)
    if len(promo_ids) > 1:
        issues.append(IssueType.MULTIPLE_PROMO_IDS)
    if keys and promo_ids:
        issues.append(IssueType.KEY_PROMO_CONFLICT)
    if not keys and not promo_ids:
        issues.append(IssueType.INVALID_CODE)

    return ParsedCode(keys=keys, promo_ids=promo_ids, issues=issues)
