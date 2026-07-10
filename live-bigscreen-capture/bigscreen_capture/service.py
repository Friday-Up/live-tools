from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic

from .archive_writer import write_manifest_workbook, write_zip_archive
from .browser import BigscreenBrowser
from .capture_manifest import CAPTURE_STEPS
from .capture_steps import run_capture_step
from .file_naming import screenshot_filename
from .models import CaptureRecord
from .url_parser import parse_bigscreen_url


@dataclass
class CaptureOnceResult:
    room_id: str
    room_name: str
    output_dir: Path
    records: list
    manifest_file: Path
    zip_file: Path

    @property
    def success_count(self):
        return sum(1 for record in self.records if record.status == "成功")

    @property
    def fail_count(self):
        return sum(1 for record in self.records if record.status == "失败")

    @property
    def stopped_count(self):
        return sum(1 for record in self.records if record.status == "已停止")


def capture_once(
    url,
    output_dir,
    planned_slot,
    captured_at,
    auth_file,
    browser_factory=BigscreenBrowser,
    should_stop=None,
    log_callback=None,
    show_browser=False,
    on_login_required=None,
    wait_for_login=None,
):
    output_dir = Path(output_dir)
    parsed = parse_bigscreen_url(url)
    log = log_callback or (lambda _: None)
    slot_dir = output_dir / captured_at.strftime("%Y%m%d_%H%M%S")
    slot_dir.mkdir(parents=True, exist_ok=True)
    records = []
    def start_browser(headless):
        return browser_factory(
            parsed.url,
            auth_file=auth_file,
            headless=headless,
            log_callback=log,
        ).start()

    browser = start_browser(headless=not show_browser)
    try:
        if hasattr(browser, "check_login_status"):
            log("检查蓝屏登录状态")
            if not browser.check_login_status():
                log("蓝屏登录态失效，需要登录")
                if not show_browser:
                    log("当前为隐藏浏览器，切换为显示窗口以便登录")
                    browser.close(force=True)
                    browser = start_browser(headless=False)
                browser.open_login_page()
                if on_login_required:
                    on_login_required(browser)
                if wait_for_login and not wait_for_login():
                    raise RuntimeError("登录未完成")
                if not browser.check_login_status():
                    raise RuntimeError("登录状态未能同步到蓝屏截图浏览器")
                browser.save_auth_state()
                log("蓝屏登录状态已保存")

        room_name = browser.get_room_name()

        for step in CAPTURE_STEPS:
            filename = screenshot_filename(
                parsed.room_id,
                captured_at,
                step.code,
                step.filename_label,
            )
            path = slot_dir / filename
            if should_stop and should_stop():
                records.append(
                    CaptureRecord(
                        planned_slot,
                        None,
                        parsed.room_id,
                        step.code,
                        step.name,
                        filename,
                        "已停止",
                        path=path,
                    )
                )
                continue
            try:
                log("开始截图 %s %s" % (step.code, step.name))
                step_started_at = monotonic()
                run_capture_step(browser, step)
                browser.screenshot(path)
                log("截图成功 %s %s，用时 %.1fs" % (step.code, step.name, monotonic() - step_started_at))
                records.append(
                    CaptureRecord(
                        planned_slot,
                        datetime.now(),
                        parsed.room_id,
                        step.code,
                        step.name,
                        filename,
                        "成功",
                        path=path,
                    )
                )
            except Exception as exc:
                records.append(
                    CaptureRecord(
                        planned_slot,
                        datetime.now(),
                        parsed.room_id,
                        step.code,
                        step.name,
                        filename,
                        "失败",
                        str(exc),
                        path=path,
                    )
                )
                log("截图失败 %s %s: %s" % (step.code, step.name, exc))
    finally:
        browser.close(force=True)

    archive_started_at = monotonic()
    log("开始生成截图清单和 ZIP")
    manifest_file = write_manifest_workbook(output_dir, records)
    zip_file = write_zip_archive(output_dir, parsed.room_id, captured_at)
    log("截图清单和 ZIP 已生成，用时 %.1fs" % (monotonic() - archive_started_at))
    return CaptureOnceResult(
        parsed.room_id,
        room_name,
        output_dir,
        records,
        manifest_file,
        zip_file,
    )


def write_capture_bundle(output_dir, room_id, captured_at, records):
    output_dir = Path(output_dir)
    manifest_file = write_manifest_workbook(output_dir, records)
    zip_file = write_zip_archive(output_dir, room_id, captured_at)
    return manifest_file, zip_file
