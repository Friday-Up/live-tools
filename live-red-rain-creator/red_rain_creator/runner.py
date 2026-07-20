"""红包雨批量创建任务编排。"""

import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

from .browser import LoginRequiredError, RedRainCreatorBrowser
from .excel_reader import ColumnMapping, read_rows_with_errors
from .models import BatchResult, RedRainResult, RedRainRow
from .report_writer import write_batch_report
from .validator import find_duplicate_red_packet_ids, find_duplicates, find_overlaps, validate_row


class BatchRunner:
    def __init__(
        self,
        browser: RedRainCreatorBrowser,
        log_callback: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, int, int, int, int, int, str], None]] = None,
        login_callback: Optional[Callable[[], bool]] = None,
    ):
        self.browser = browser
        self._log = log_callback or (lambda _: None)
        self.stop_event = stop_event or threading.Event()
        self.progress_callback = progress_callback or (lambda *args: None)
        self.login_callback = login_callback

    def _log_msg(self, message: str):
        self._log(message)

    def prepare_rows(self, file_path: Union[str, Path], mapping: ColumnMapping) -> Tuple[List[RedRainRow], List[RedRainResult]]:
        rows, parse_rejected = read_rows_with_errors(file_path, mapping)
        duplicate_rows = find_duplicates(rows)
        duplicate_packet_rows = find_duplicate_red_packet_ids(rows)
        overlap_rows = find_overlaps(rows)
        valid_rows = []
        rejected = list(parse_rejected)
        for row in rows:
            errors = validate_row(row)
            if row.row_index in duplicate_rows:
                errors.append("与前面行完全重复")
            if row.row_index in duplicate_packet_rows:
                errors.append("红包ID与前面行重复")
            if row.row_index in overlap_rows:
                errors.append("活动时间与 Excel 内其他红包雨重叠")
            if errors:
                rejected.append(RedRainResult.from_row(row, status="跳过", error="; ".join(errors)))
            else:
                valid_rows.append(row)
        return valid_rows, rejected

    def run_batch(self, rows: List[RedRainRow]) -> BatchResult:
        result = BatchResult()
        total = len(rows)
        for index, row in enumerate(rows, start=1):
            if self.stop_event.is_set():
                result.stopped_by_user = True
                remaining = rows[index - 1 :]
                result.results.extend(
                    RedRainResult.from_row(item, status="跳过", error="用户停止，未执行")
                    for item in remaining
                )
                result.skipped_count += len(remaining)
                break
            self._log_msg(f"[{index}/{total}] 正在创建: {row.activity_name}")
            login_retries = 0
            while True:
                try:
                    item = self.browser.create_activity(row)
                    break
                except LoginRequiredError as exc:
                    login_retries += 1
                    self._log_msg(f"登录态失效，暂停当前行: {row.activity_name}")
                    if login_retries > 2 or not self.login_callback or not self.login_callback():
                        item = RedRainResult.from_row(row, status="失败", error=str(exc))
                        break
                    self._log_msg(f"登录已恢复，重新处理当前行: {row.activity_name}")
            result.results.append(item)
            if item.status == "成功":
                result.created_count += 1
            elif item.status == "已存在":
                result.existed_count += 1
            elif item.status == "待确认":
                result.pending_count += 1
            else:
                result.failed_count += 1
            self.progress_callback(
                index,
                total,
                result.created_count,
                result.failed_count,
                result.existed_count,
                result.pending_count,
                row.activity_name,
            )
            if index < total and not self.stop_event.is_set():
                time.sleep(0.8)
        return result

    def run_from_excel(self, file_path, mapping, output_dir):
        valid_rows, rejected = self.prepare_rows(file_path, mapping)
        result = self.run_batch(valid_rows)
        result.results.extend(rejected)
        result.skipped_count += len(rejected)
        return result, write_batch_report(result, output_dir)
