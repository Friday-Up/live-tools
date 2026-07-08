from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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


def capture_once(
    url,
    output_dir,
    planned_slot,
    captured_at,
    auth_file,
    browser_factory=BigscreenBrowser,
    should_stop=None,
    log_callback=None,
):
    output_dir = Path(output_dir)
    parsed = parse_bigscreen_url(url)
    log = log_callback or (lambda _: None)
    slot_dir = output_dir / captured_at.strftime("%Y%m%d_%H%M%S")
    slot_dir.mkdir(parents=True, exist_ok=True)
    records = []
    browser = browser_factory(
        parsed.url,
        auth_file=auth_file,
        headless=False,
        log_callback=log,
    ).start()
    try:
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
                run_capture_step(browser, step)
                browser.screenshot(path)
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

    manifest_file = write_manifest_workbook(output_dir, records)
    zip_file = write_zip_archive(output_dir, parsed.room_id, captured_at)
    return CaptureOnceResult(parsed.room_id, output_dir, records, manifest_file, zip_file)
