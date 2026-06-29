from __future__ import annotations

"""Promotion binding generation service."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from promotion_binding.code_parser import IssueType, parse_code_cell
from promotion_binding.report_writer import IssueRecord, write_report
from promotion_binding.template_writer import BindingRecord, BindingType, write_upload_template
from promotion_binding.workbook_reader import BusinessRow, ColumnMapping, inspect_business_workbook, read_business_rows


@dataclass(frozen=True)
class GenerationResult:
    success_count: int
    coupon_key_count: int
    promo_id_count: int
    skipped_empty_count: int
    invalid_count: int
    duplicate_count: int
    selling_point_count: int
    output_template_path: Path
    report_path: Path
    selling_point_column_found: bool = False


def generate_binding_files(
    business_file: str | Path,
    template_file: str | Path,
    output_dir: str | Path,
    generated_at: datetime | None = None,
    column_mapping: ColumnMapping | None = None,
    enable_selling_point: bool = False,
) -> GenerationResult:
    business_file = Path(business_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    inspection = inspect_business_workbook(business_file)
    mapping = column_mapping or inspection.suggested_mapping

    if enable_selling_point and mapping.selling_point_col is None:
        mapping = ColumnMapping(
            sku_col=mapping.sku_col,
            code_col=mapping.code_col,
            product_name_col=mapping.product_name_col,
            selling_point_col=inspection.suggested_mapping.selling_point_col,
        )

    rows = read_business_rows(business_file, column_mapping=mapping)
    selling_point_column_found = enable_selling_point and mapping.selling_point_col is not None

    candidates: list[BindingRecord] = []
    issue_records: list[IssueRecord] = []
    skipped_empty_count = 0
    selling_point_too_long_count = 0

    for row in rows:
        has_selling_point = enable_selling_point and bool(row.selling_point)

        if not row.raw_code and not has_selling_point:
            skipped_empty_count += 1
            issue_records.append(
                _issue(
                    row,
                    "EMPTY_CODE",
                    "券码/价码和短卖点均为空" if enable_selling_point else "券码/价码为空",
                    "无需绑定则忽略；需要绑定则补充专享券KEY或专享价促销ID或短卖点",
                )
            )
            continue

        if has_selling_point and len(row.selling_point) > 22:
            selling_point_too_long_count += 1
            issue_records.append(
                _selling_point_issue(
                    row,
                    "SELLING_POINT_TOO_LONG",
                    "短卖点超过22个字符",
                    "建议缩短至22个字符以内，否则上传后不展示",
                )
            )

        if not row.raw_code:
            candidates.append(
                BindingRecord(
                    sku=row.sku,
                    binding_type=None,
                    binding_value="",
                    source_row=row.source_row,
                    product_name=row.product_name,
                    selling_point=row.selling_point,
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
                    selling_point=row.selling_point,
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
                    selling_point=row.selling_point,
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
    selling_point_count = sum(1 for record in binding_records if record.selling_point)
    invalid_count = sum(
        1
        for issue in issue_records
        if issue.issue_type not in {"DUPLICATE_BINDING", "EMPTY_CODE", "SELLING_POINT_TOO_LONG"}
    )

    write_report(
        output_path=report_path,
        summary={
            "可绑定条数": len(binding_records),
            "专享券KEY条数": coupon_key_count,
            "专享价促销ID条数": promo_id_count,
            "含短卖点条数": selling_point_count,
            "空值跳过": skipped_empty_count,
            "异常条数": invalid_count,
            "重复条数": duplicate_count,
            "短卖点超长警告": selling_point_too_long_count,
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
        selling_point_count=selling_point_count,
        output_template_path=output_template_path,
        report_path=report_path,
        selling_point_column_found=selling_point_column_found,
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
        code_records = [record for record in records if record.binding_type is not None]
        selling_point_only_records = [record for record in records if record.binding_type is None]
        selected_records = code_records or selling_point_only_records
        superseded_records = selling_point_only_records if code_records else []

        identities = {(record.binding_type, record.binding_value) for record in selected_records}
        if len(identities) > 1:
            first = selected_records[0]
            raw_values = "；".join(
                _raw_row_summary(record, rows_by_source.get(record.source_row))
                for record in selected_records
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

        first = selected_records[0]
        output.append(first)
        for duplicate in selected_records[1:] + superseded_records:
            duplicate_count += 1
            row = rows_by_source.get(duplicate.source_row)
            issues.append(
                IssueRecord(
                    source_row=duplicate.source_row,
                    sku=duplicate.sku,
                    raw_code=(row.raw_code or row.selling_point) if row else duplicate.binding_value,
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


def _selling_point_issue(row: BusinessRow, issue_type: str, message: str, action: str) -> IssueRecord:
    return IssueRecord(
        source_row=row.source_row,
        sku=row.sku,
        raw_code=row.selling_point,
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
