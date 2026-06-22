from __future__ import annotations

"""Promotion binding generation service."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from promotion_binding.code_parser import IssueType, parse_code_cell
from promotion_binding.report_writer import IssueRecord, write_report
from promotion_binding.template_writer import BindingRecord, BindingType, write_upload_template
from promotion_binding.workbook_reader import BusinessRow, ColumnMapping, read_business_rows


@dataclass(frozen=True)
class GenerationResult:
    success_count: int
    coupon_key_count: int
    promo_id_count: int
    skipped_empty_count: int
    invalid_count: int
    duplicate_count: int
    output_template_path: Path
    report_path: Path


def generate_binding_files(
    business_file: str | Path,
    template_file: str | Path,
    output_dir: str | Path,
    generated_at: datetime | None = None,
    column_mapping: ColumnMapping | None = None,
) -> GenerationResult:
    business_file = Path(business_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_business_rows(business_file, column_mapping=column_mapping)
    candidates: list[BindingRecord] = []
    issue_records: list[IssueRecord] = []
    skipped_empty_count = 0

    for row in rows:
        if not row.raw_code:
            skipped_empty_count += 1
            issue_records.append(
                _issue(
                    row,
                    "EMPTY_CODE",
                    "券码/价码为空",
                    "无需绑定则忽略；需要绑定则补充专享券KEY或专享价促销ID",
                )
            )
            continue

        parsed = parse_code_cell(row.raw_code)
        if parsed.issues:
            issue_type = parsed.issues[0].value
            issue_records.append(_issue(row, issue_type, _message_for_issue(issue_type), _action_for_issue(issue_type)))
            continue

        if parsed.keys:
            candidates.append(
                BindingRecord(
                    sku=row.sku,
                    binding_type=BindingType.COUPON_KEY,
                    binding_value=parsed.keys[0],
                    source_row=row.source_row,
                    product_name=row.product_name,
                )
            )
        elif parsed.promo_ids:
            candidates.append(
                BindingRecord(
                    sku=row.sku,
                    binding_type=BindingType.PROMO_ID,
                    binding_value=parsed.promo_ids[0],
                    source_row=row.source_row,
                    product_name=row.product_name,
                )
            )

    binding_records, duplicate_count, conflict_issues = _dedupe_and_find_conflicts(candidates, rows)
    issue_records.extend(conflict_issues)

    timestamp = _filename_timestamp(generated_at)
    output_template_path = output_dir / f"京东绑券上传模板_{timestamp}_.xlsx"
    report_path = output_dir / f"异常报告_{timestamp}_.xlsx"

    write_upload_template(template_file, output_template_path, binding_records)

    coupon_key_count = sum(1 for record in binding_records if record.binding_type == BindingType.COUPON_KEY)
    promo_id_count = sum(1 for record in binding_records if record.binding_type == BindingType.PROMO_ID)
    invalid_count = sum(
        1
        for issue in issue_records
        if issue.issue_type not in {"DUPLICATE_BINDING", "EMPTY_CODE"}
    )

    write_report(
        output_path=report_path,
        summary={
            "可绑定条数": len(binding_records),
            "专享券KEY条数": coupon_key_count,
            "专享价促销ID条数": promo_id_count,
            "空值跳过": skipped_empty_count,
            "异常条数": invalid_count,
            "重复条数": duplicate_count,
        },
        binding_records=binding_records,
        issue_records=issue_records,
    )

    return GenerationResult(
        success_count=len(binding_records),
        coupon_key_count=coupon_key_count,
        promo_id_count=promo_id_count,
        skipped_empty_count=skipped_empty_count,
        invalid_count=invalid_count,
        duplicate_count=duplicate_count,
        output_template_path=output_template_path,
        report_path=report_path,
    )


def _dedupe_and_find_conflicts(
    candidates: list[BindingRecord],
    source_rows: list[BusinessRow],
) -> tuple[list[BindingRecord], int, list[IssueRecord]]:
    rows_by_source = {row.source_row: row for row in source_rows}
    grouped: dict[str, list[BindingRecord]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.sku].append(candidate)

    output: list[BindingRecord] = []
    issues: list[IssueRecord] = []
    duplicate_count = 0

    for sku, records in grouped.items():
        identities = {(record.binding_type, record.binding_value) for record in records}
        if len(identities) > 1:
            first = records[0]
            raw_values = "；".join(
                _raw_row_summary(record, rows_by_source.get(record.source_row))
                for record in records
            )
            issues.append(
                IssueRecord(
                    source_row=first.source_row,
                    sku=sku,
                    raw_code=raw_values,
                    issue_type="SKU_BINDING_CONFLICT",
                    message="同一个SKU出现多个不同绑定值",
                    action="人工确认保留哪一个绑定值后重新生成",
                    product_name=first.product_name,
                )
            )
            continue

        first = records[0]
        output.append(first)
        for duplicate in records[1:]:
            duplicate_count += 1
            row = rows_by_source.get(duplicate.source_row)
            issues.append(
                IssueRecord(
                    source_row=duplicate.source_row,
                    sku=duplicate.sku,
                    raw_code=row.raw_code if row else duplicate.binding_value,
                    issue_type="DUPLICATE_BINDING",
                    message="重复SKU和绑定值，已只保留第一条",
                    action=f"已保留原始第 {first.source_row} 行；本行无需上传",
                    product_name=row.product_name if row else duplicate.product_name,
                    kept_source_row=first.source_row,
                )
            )

    output.sort(key=lambda record: record.source_row)
    return output, duplicate_count, issues


def _issue(row: BusinessRow, issue_type: str, message: str, action: str) -> IssueRecord:
    return IssueRecord(
        source_row=row.source_row,
        sku=row.sku,
        raw_code=row.raw_code,
        issue_type=issue_type,
        message=message,
        action=action,
        product_name=row.product_name,
    )


def _raw_row_summary(record: BindingRecord, row: BusinessRow | None) -> str:
    raw_code = row.raw_code if row else record.binding_value
    return f"第{record.source_row}行 {raw_code}"


def _filename_timestamp(generated_at: datetime | None = None) -> str:
    current = generated_at or datetime.now()
    return current.strftime("%Y%m%d-%H%M%S")


def _message_for_issue(issue_type: str) -> str:
    return {
        IssueType.INVALID_CODE.value: "未识别到专享券KEY或专享价促销ID",
        IssueType.MULTIPLE_KEYS.value: "同一单元格出现多个专享券KEY",
        IssueType.MULTIPLE_PROMO_IDS.value: "同一单元格出现多个专享价促销ID",
        IssueType.KEY_PROMO_CONFLICT.value: "同一单元格同时出现专享券KEY和专享价促销ID",
    }.get(issue_type, "券码/价码内容异常")


def _action_for_issue(issue_type: str) -> str:
    return {
        IssueType.INVALID_CODE.value: "人工确认后重填",
        IssueType.MULTIPLE_KEYS.value: "人工确认保留一个KEY后重填",
        IssueType.MULTIPLE_PROMO_IDS.value: "人工确认保留一个促销ID后重填",
        IssueType.KEY_PROMO_CONFLICT.value: "按官方模板限制拆分或保留一种权益",
    }.get(issue_type, "人工确认")
