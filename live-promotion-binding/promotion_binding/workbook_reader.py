from __future__ import annotations

"""Read business submission workbooks for promotion binding generation."""

from dataclasses import dataclass
from pathlib import Path
import re

from openpyxl import load_workbook


@dataclass(frozen=True)
class BusinessRow:
    source_row: int
    sku: str
    raw_code: str
    product_name: str = ""


def normalize_header(value) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"[\s\u00a0]+", "", text).strip()


def format_cell_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _find_column(headers: list, candidates: list[str]) -> int | None:
    normalized_headers = [normalize_header(header) for header in headers]
    for index, header in enumerate(normalized_headers):
        for candidate in candidates:
            if normalize_header(candidate) in header:
                return index + 1
    return None


def read_business_rows(file_path: str | Path) -> list[BusinessRow]:
    wb = load_workbook(file_path, data_only=True, read_only=True)
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    sku_col = _find_column(headers, ["上播·SKU ID", "上播·SKUID"])
    code_col = _find_column(headers, ["券码/价码"])
    product_name_col = _find_column(headers, ["商品名称"])

    missing = []
    if sku_col is None:
        missing.append("上播·SKU ID")
    if code_col is None:
        missing.append("券码/价码")
    if missing:
        header_text = "、".join(str(header) for header in headers if header)
        raise ValueError(f"未找到必需列: {', '.join(missing)}；当前表头: {header_text or '空'}")

    rows: list[BusinessRow] = []
    for row_index in range(2, ws.max_row + 1):
        sku = format_cell_value(ws.cell(row_index, sku_col).value)
        if not sku:
            continue
        raw_code = format_cell_value(ws.cell(row_index, code_col).value)
        product_name = format_cell_value(ws.cell(row_index, product_name_col).value) if product_name_col else ""
        rows.append(
            BusinessRow(
                source_row=row_index,
                sku=sku,
                raw_code=raw_code,
                product_name=product_name,
            )
        )

    return rows
