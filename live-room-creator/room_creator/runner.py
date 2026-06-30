"""批量创建直播间任务编排。"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from . import config
from .browser import DailyLimitReachedError, RoomCreatorBrowser
from .excel_reader import read_room_rows, ColumnMapping
from .models import BatchResult, RoomCreateResult, RoomCreateRow
from .report_writer import write_batch_report
from .validator import find_duplicates, validate_row


class BatchRunner:
    """串行批量创建直播间。"""

    def __init__(
        self,
        browser: RoomCreatorBrowser,
        log_callback: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, int, int, int, str], None]] = None,
    ):
        self.browser = browser
        self._log = log_callback or (lambda _: None)
        self.stop_event = stop_event or threading.Event()
        self.progress_callback = progress_callback or (lambda *args, **kwargs: None)

    def _log_msg(self, message: str):
        print(message)
        self._log(message)

    def prepare_rows(
        self,
        file_path: str | Path,
        mapping: ColumnMapping,
    ) -> tuple[list[RoomCreateRow], list[RoomCreateResult]]:
        """读取并预校验所有行，返回可创建行和预校验失败结果。"""
        rows = read_room_rows(file_path, mapping)
        duplicates = find_duplicates(rows)

        valid_rows: list[RoomCreateRow] = []
        pre_failed: list[RoomCreateResult] = []

        for row in rows:
            errors = validate_row(row)
            if row.row_index in duplicates:
                errors.append("与前面行的标题+开播时间重复")

            if errors:
                pre_failed.append(
                    RoomCreateResult(
                        row_index=row.row_index,
                        title=row.title,
                        start_time=row.start_time,
                        live_form=row.live_form,
                        live_direction=row.live_direction,
                        live_location=row.live_location,
                        live_category=row.live_category,
                        success=False,
                        error="; ".join(errors),
                    )
                )
            else:
                valid_rows.append(row)

        return valid_rows, pre_failed

    def run_batch(
        self,
        rows: list[RoomCreateRow],
    ) -> BatchResult:
        """串行创建直播间。"""
        result = BatchResult()

        if len(rows) > config.DAILY_CREATE_LIMIT:
            result.stopped_by_limit = True
            result.error = f"超出每日创建上限 {config.DAILY_CREATE_LIMIT} 个"
            self._log_msg(result.error)
            return result

        if not rows:
            result.error = "没有可创建的直播间"
            return result

        self._log_msg(f"开始批量创建，共 {len(rows)} 个直播间，每日上限 {config.DAILY_CREATE_LIMIT}")

        for index, row in enumerate(rows, start=1):
            if self.stop_event.is_set():
                result.stopped_by_user = True
                self._log_msg("用户停止任务")
                break

            self._log_msg(f"[{index}/{len(rows)}] 正在创建: {row.title}")
            try:
                self.progress_callback(index, len(rows), result.created_count, result.failed_count, row.title)
            except Exception:
                pass

            try:
                room_result = self.browser.create_room(row)
            except DailyLimitReachedError as exc:
                # 当前行失败，后续全部标记为因日上限跳过
                room_result = RoomCreateResult(
                    row_index=row.row_index,
                    title=row.title,
                    start_time=row.start_time,
                    live_form=row.live_form,
                    live_direction=row.live_direction,
                    live_location=row.live_location,
                    live_category=row.live_category,
                    success=False,
                    error=str(exc),
                )
                result.results.append(room_result)
                result.failed_count += 1
                result.stopped_by_limit = True
                result.error = f"当日创建场次已达上限 {config.DAILY_CREATE_LIMIT} 场，停止后续创建"
                self._log_msg(f"第 {row.row_index} 行触发日创建上限，停止后续创建")

                for remaining_row in rows[index:]:
                    result.results.append(
                        RoomCreateResult(
                            row_index=remaining_row.row_index,
                            title=remaining_row.title,
                            start_time=remaining_row.start_time,
                            live_form=remaining_row.live_form,
                            live_direction=remaining_row.live_direction,
                            live_location=remaining_row.live_location,
                            live_category=remaining_row.live_category,
                            success=False,
                            error=f"当日创建场次已达上限 {config.DAILY_CREATE_LIMIT} 场，未执行",
                        )
                    )
                    result.skipped_count += 1
                try:
                    self.progress_callback(index, len(rows), result.created_count, result.failed_count, row.title)
                except Exception:
                    pass
                break

            result.results.append(room_result)

            if room_result.success:
                result.created_count += 1
            else:
                result.failed_count += 1
            try:
                self.progress_callback(index, len(rows), result.created_count, result.failed_count, row.title)
            except Exception:
                pass

            # 每行之间随机延迟，降低风控概率
            if index < len(rows) and not self.stop_event.is_set():
                delay = 1.5
                self._log_msg(f"等待 {delay}s 后继续...")
                time.sleep(delay)

        self._log_msg(
            f"任务结束：成功 {result.created_count}，失败 {result.failed_count}，"
            f"跳过 {result.skipped_count}"
        )
        return result

    def run_from_excel(
        self,
        file_path: str | Path,
        mapping: ColumnMapping,
        output_dir: str | Path,
    ) -> tuple[BatchResult, Path]:
        """完整流程：读取 Excel -> 校验 -> 创建 -> 生成报告。"""
        valid_rows, pre_failed = self.prepare_rows(file_path, mapping)

        result = self.run_batch(valid_rows)
        result.results.extend(pre_failed)
        result.skipped_count = len(pre_failed)

        output_path = write_batch_report(result, output_dir)
        return result, output_path
