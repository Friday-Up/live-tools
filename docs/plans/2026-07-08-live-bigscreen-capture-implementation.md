# Live Bigscreen Capture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `蓝屏自动截图` tool that accepts a JD Live bigscreen URL, schedules whole-hour captures, and saves the agreed 15 screenshot items per capture run.

**Architecture:** Add a new independent `live-bigscreen-capture` module for URL parsing, slot planning, capture manifests, browser-step orchestration, result manifests, and ZIP output. Keep `live-web` as the unified UI/API/task-status layer and reuse the existing Playwright login-state browser capability from `live-sku-price-audit`.

**Tech Stack:** Python 3.9+, Flask, unittest, openpyxl, Playwright via the existing `BrowserManager`, PyInstaller packaging.

---

### Task 1: Core Data Model, URL Parsing, Slot Planning, and Capture Manifest

**Files:**
- Create: `live-bigscreen-capture/bigscreen_capture/__init__.py`
- Create: `live-bigscreen-capture/bigscreen_capture/models.py`
- Create: `live-bigscreen-capture/bigscreen_capture/url_parser.py`
- Create: `live-bigscreen-capture/bigscreen_capture/schedule.py`
- Create: `live-bigscreen-capture/bigscreen_capture/capture_manifest.py`
- Create: `live-bigscreen-capture/tests/__init__.py`
- Create: `live-bigscreen-capture/tests/test_url_parser.py`
- Create: `live-bigscreen-capture/tests/test_schedule.py`
- Create: `live-bigscreen-capture/tests/test_capture_manifest.py`

**Step 1: Write failing URL parser tests**

Create `live-bigscreen-capture/tests/test_url_parser.py`:

```python
import unittest

from bigscreen_capture.url_parser import parse_bigscreen_url, BigscreenUrlError


class BigscreenUrlParserTest(unittest.TestCase):
    def test_parses_jlive_bigscreen_id(self):
        parsed = parse_bigscreen_url("https://jlive.jd.com/bigScreen?id=46794566")

        self.assertEqual(parsed.room_id, "46794566")
        self.assertEqual(parsed.url, "https://jlive.jd.com/bigScreen?id=46794566")

    def test_rejects_missing_id(self):
        with self.assertRaises(BigscreenUrlError):
            parse_bigscreen_url("https://jlive.jd.com/bigScreen")

    def test_rejects_wrong_host(self):
        with self.assertRaises(BigscreenUrlError):
            parse_bigscreen_url("https://example.com/bigScreen?id=46794566")


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run URL parser test to verify failure**

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest tests/test_url_parser.py -v
```

Expected: FAIL because `bigscreen_capture.url_parser` does not exist.

**Step 3: Implement minimal URL parser and models**

Create `live-bigscreen-capture/bigscreen_capture/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ParsedBigscreenUrl:
    url: str
    room_id: str


@dataclass(frozen=True)
class CaptureStep:
    code: str
    name: str
    page: str
    action: str
    filename_label: str


@dataclass
class CaptureRecord:
    planned_slot: str
    executed_at: Optional[datetime]
    room_id: str
    step_code: str
    step_name: str
    filename: str
    status: str
    error: str = ""
    path: Optional[Path] = None
```

Create `live-bigscreen-capture/bigscreen_capture/url_parser.py`:

```python
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from .models import ParsedBigscreenUrl


class BigscreenUrlError(ValueError):
    pass


def parse_bigscreen_url(raw_url: str) -> ParsedBigscreenUrl:
    raw_url = (raw_url or "").strip()
    if not raw_url:
        raise BigscreenUrlError("请填写蓝屏页面链接")

    parsed = urlparse(raw_url)
    if parsed.netloc != "jlive.jd.com":
        raise BigscreenUrlError("链接必须是 jlive.jd.com 的蓝屏页面")
    if "/bigScreen" not in parsed.path:
        raise BigscreenUrlError("链接必须是蓝屏 bigScreen 页面")

    room_ids = parse_qs(parsed.query).get("id") or []
    room_id = room_ids[0].strip() if room_ids else ""
    if not room_id:
        raise BigscreenUrlError("链接中没有识别到直播间 ID")

    return ParsedBigscreenUrl(url=raw_url, room_id=room_id)
```

Create `live-bigscreen-capture/bigscreen_capture/__init__.py`:

```python
from .url_parser import BigscreenUrlError, parse_bigscreen_url

__all__ = ["BigscreenUrlError", "parse_bigscreen_url"]
```

**Step 4: Run URL parser test to verify pass**

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest tests/test_url_parser.py -v
```

Expected: PASS.

**Step 5: Write failing schedule tests**

Create `live-bigscreen-capture/tests/test_schedule.py`:

```python
import unittest
from datetime import date, datetime

from bigscreen_capture.schedule import build_hour_options, build_planned_slots


class BigscreenScheduleTest(unittest.TestCase):
    def test_build_hour_options_returns_whole_hours(self):
        options = build_hour_options(start_hour=12, end_hour=23)

        self.assertEqual(options[0], "12:00")
        self.assertEqual(options[-1], "23:00")
        self.assertEqual(len(options), 12)

    def test_build_planned_slots_marks_past_slots(self):
        now = datetime(2026, 7, 8, 18, 35, 0)

        slots = build_planned_slots(
            capture_date=date(2026, 7, 8),
            hour_labels=["18:00", "19:00"],
            now=now,
        )

        self.assertEqual(slots[0].label, "18:00")
        self.assertEqual(slots[0].status, "missed")
        self.assertEqual(slots[1].label, "19:00")
        self.assertEqual(slots[1].status, "pending")


if __name__ == "__main__":
    unittest.main()
```

**Step 6: Implement schedule module**

Create `live-bigscreen-capture/bigscreen_capture/schedule.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True)
class PlannedSlot:
    label: str
    run_at: datetime
    status: str


def build_hour_options(start_hour: int = 0, end_hour: int = 23) -> list[str]:
    return [f"{hour:02d}:00" for hour in range(start_hour, end_hour + 1)]


def build_planned_slots(
    capture_date: date,
    hour_labels: list[str],
    now: datetime | None = None,
) -> list[PlannedSlot]:
    current = now or datetime.now()
    slots: list[PlannedSlot] = []
    for label in hour_labels:
        hour, minute = [int(part) for part in label.split(":", 1)]
        run_at = datetime.combine(capture_date, time(hour=hour, minute=minute))
        status = "missed" if run_at < current else "pending"
        slots.append(PlannedSlot(label=label, run_at=run_at, status=status))
    return slots
```

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest tests/test_schedule.py -v
```

Expected: PASS.

**Step 7: Write failing manifest tests**

Create `live-bigscreen-capture/tests/test_capture_manifest.py`:

```python
import unittest

from bigscreen_capture.capture_manifest import CAPTURE_STEPS


class CaptureManifestTest(unittest.TestCase):
    def test_manifest_contains_confirmed_15_steps(self):
        labels = [step.filename_label for step in CAPTURE_STEPS]

        self.assertEqual(len(CAPTURE_STEPS), 15)
        self.assertEqual(CAPTURE_STEPS[0].filename_label, "概览总览")
        self.assertIn("渠道流量饼状图_在线", labels)
        self.assertIn("渠道成交饼状图_成交", labels)
        self.assertIn("挂袋数据", labels)
        self.assertIn("订单Top10", labels)
        self.assertIn("GMVTop10", labels)


if __name__ == "__main__":
    unittest.main()
```

**Step 8: Implement capture manifest**

Create `live-bigscreen-capture/bigscreen_capture/capture_manifest.py`:

```python
from __future__ import annotations

from .models import CaptureStep


CAPTURE_STEPS = [
    CaptureStep("01", "概览总览", "概览", "打开概览并截整页", "概览总览"),
    CaptureStep("02", "渠道流量饼状图_在线", "概览", "左侧直播间卡片切到在线", "渠道流量饼状图_在线"),
    CaptureStep("03", "渠道成交饼状图_成交", "概览", "左侧直播间卡片切到成交", "渠道成交饼状图_成交"),
    CaptureStep("04", "挂袋数据", "概览", "中间商品范围下拉切到挂袋商品并截整页", "挂袋数据"),
    CaptureStep("05", "在线人数曲线", "流量", "综合趋势切到在线人数", "在线人数曲线"),
    CaptureStep("06", "访问人数曲线", "流量", "综合趋势切到访问人数", "访问人数曲线"),
    CaptureStep("07", "人均停留时长曲线", "流量", "综合趋势切到人均停留时长", "人均停留时长曲线"),
    CaptureStep("08", "成交人数曲线", "流量", "综合趋势切到成交人数", "成交人数曲线"),
    CaptureStep("09", "成交金额曲线", "流量", "综合趋势切到成交金额", "成交金额曲线"),
    CaptureStep("10", "成交单量曲线", "流量", "综合趋势切到成交单量", "成交单量曲线"),
    CaptureStep("11", "曝光点击率曲线", "流量", "综合趋势切到直播曝光点击率", "曝光点击率曲线"),
    CaptureStep("12", "用户画像_访问用户", "概览", "右侧用户画像下拉选择访问用户", "用户画像_访问用户"),
    CaptureStep("13", "用户画像_成交用户", "概览", "右侧用户画像下拉选择成交用户", "用户画像_成交用户"),
    CaptureStep("14", "订单Top10", "商品", "商品分析表按成交件数降序", "订单Top10"),
    CaptureStep("15", "GMVTop10", "商品", "商品分析表按成交金额降序", "GMVTop10"),
]
```

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest tests/test_capture_manifest.py -v
```

Expected: PASS.

**Step 9: Commit**

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
git add live-bigscreen-capture
git commit -m "feat: add bigscreen capture core models"
```

### Task 2: File Naming, Manifest Workbook, and ZIP Archive

**Files:**
- Create: `live-bigscreen-capture/bigscreen_capture/file_naming.py`
- Create: `live-bigscreen-capture/bigscreen_capture/archive_writer.py`
- Create: `live-bigscreen-capture/tests/test_file_naming.py`
- Create: `live-bigscreen-capture/tests/test_archive_writer.py`

**Step 1: Write failing file naming tests**

Create `live-bigscreen-capture/tests/test_file_naming.py`:

```python
import unittest
from datetime import datetime

from bigscreen_capture.file_naming import screenshot_filename, zip_filename


class FileNamingTest(unittest.TestCase):
    def test_screenshot_filename_uses_required_format(self):
        name = screenshot_filename(
            room_id="46794566",
            captured_at=datetime(2026, 7, 8, 19, 0, 0),
            step_code="02",
            label="渠道流量饼状图_在线",
        )

        self.assertEqual(
            name,
            "蓝屏数据截图_46794566__20260708_190000_02_渠道流量饼状图_在线.png",
        )

    def test_zip_filename_uses_date(self):
        self.assertEqual(zip_filename("46794566", datetime(2026, 7, 8, 19, 0, 0)), "蓝屏数据截图_46794566__20260708.zip")


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Implement file naming**

Create `live-bigscreen-capture/bigscreen_capture/file_naming.py`:

```python
from __future__ import annotations

from datetime import datetime


def screenshot_filename(room_id: str, captured_at: datetime, step_code: str, label: str) -> str:
    return f"蓝屏数据截图_{room_id}__{captured_at:%Y%m%d_%H%M%S}_{step_code}_{label}.png"


def zip_filename(room_id: str, captured_at: datetime) -> str:
    return f"蓝屏数据截图_{room_id}__{captured_at:%Y%m%d}.zip"
```

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest tests/test_file_naming.py -v
```

Expected: PASS.

**Step 3: Write failing archive writer tests**

Create `live-bigscreen-capture/tests/test_archive_writer.py`:

```python
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from bigscreen_capture.archive_writer import write_manifest_workbook, write_zip_archive
from bigscreen_capture.models import CaptureRecord


class ArchiveWriterTest(unittest.TestCase):
    def test_writes_manifest_workbook_and_zip(self):
        output_dir = Path(tempfile.mkdtemp())
        image_path = output_dir / "20260708_190000" / "蓝屏数据截图_46794566__20260708_190000_01_概览总览.png"
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(b"png")
        records = [
            CaptureRecord(
                planned_slot="19:00",
                executed_at=datetime(2026, 7, 8, 19, 0, 1),
                room_id="46794566",
                step_code="01",
                step_name="概览总览",
                filename=image_path.name,
                status="成功",
                path=image_path,
            )
        ]

        manifest = write_manifest_workbook(output_dir, records)
        archive = write_zip_archive(output_dir, room_id="46794566", captured_at=datetime(2026, 7, 8, 19, 0, 0))

        workbook = load_workbook(manifest)
        self.assertEqual(workbook.active["A1"].value, "计划整点")
        self.assertEqual(workbook.active["E2"].value, "概览总览")
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
        self.assertIn("截图清单.xlsx", names)
        self.assertIn("20260708_190000/" + image_path.name, names)


if __name__ == "__main__":
    unittest.main()
```

**Step 4: Implement archive writer**

Create `live-bigscreen-capture/bigscreen_capture/archive_writer.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

from .file_naming import zip_filename
from .models import CaptureRecord


MANIFEST_NAME = "截图清单.xlsx"
HEADERS = ["计划整点", "实际执行时间", "直播间ID", "序号", "截图项", "文件名", "状态", "失败原因"]


def write_manifest_workbook(output_dir: Path, records: list[CaptureRecord]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MANIFEST_NAME
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "截图清单"
    sheet.append(HEADERS)
    for record in records:
        sheet.append([
            record.planned_slot,
            record.executed_at.strftime("%Y-%m-%d %H:%M:%S") if record.executed_at else "",
            record.room_id,
            record.step_code,
            record.step_name,
            record.filename,
            record.status,
            record.error,
        ])
    workbook.save(path)
    return path


def write_zip_archive(output_dir: Path, room_id: str, captured_at: datetime) -> Path:
    archive_path = output_dir / zip_filename(room_id, captured_at)
    manifest_path = output_dir / MANIFEST_NAME
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as zf:
        if manifest_path.exists():
            zf.write(manifest_path, MANIFEST_NAME)
        for path in sorted(output_dir.rglob("*.png")):
            zf.write(path, path.relative_to(output_dir).as_posix())
    return archive_path
```

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest tests/test_archive_writer.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
git add live-bigscreen-capture
git commit -m "feat: add bigscreen capture output writers"
```

### Task 3: Browser Step Executor with Fake-Driven Tests

**Files:**
- Create: `live-bigscreen-capture/bigscreen_capture/capture_steps.py`
- Create: `live-bigscreen-capture/bigscreen_capture/browser.py`
- Create: `live-bigscreen-capture/tests/test_capture_steps.py`

**Step 1: Write fake-driven capture step tests**

Create `live-bigscreen-capture/tests/test_capture_steps.py`:

```python
import unittest

from bigscreen_capture.capture_manifest import CAPTURE_STEPS
from bigscreen_capture.capture_steps import run_capture_step


class FakeBigscreenBrowser:
    def __init__(self):
        self.calls = []

    def open_overview(self):
        self.calls.append(("open_overview",))

    def open_flow(self):
        self.calls.append(("open_flow",))

    def open_product(self):
        self.calls.append(("open_product",))

    def select_overview_live_tab(self, label):
        self.calls.append(("select_overview_live_tab", label))

    def select_overview_product_scope(self, label):
        self.calls.append(("select_overview_product_scope", label))

    def select_flow_metric(self, label):
        self.calls.append(("select_flow_metric", label))

    def select_user_portrait(self, label):
        self.calls.append(("select_user_portrait", label))

    def sort_product_table(self, label):
        self.calls.append(("sort_product_table", label))


class CaptureStepsTest(unittest.TestCase):
    def test_channel_flow_uses_overview_online_tab(self):
        browser = FakeBigscreenBrowser()

        run_capture_step(browser, CAPTURE_STEPS[1])

        self.assertEqual(browser.calls, [("open_overview",), ("select_overview_live_tab", "在线")])

    def test_bag_data_uses_overview_product_scope(self):
        browser = FakeBigscreenBrowser()

        run_capture_step(browser, CAPTURE_STEPS[3])

        self.assertEqual(browser.calls, [("open_overview",), ("select_overview_product_scope", "挂袋商品")])

    def test_order_top10_sorts_product_by_deal_count(self):
        browser = FakeBigscreenBrowser()

        run_capture_step(browser, CAPTURE_STEPS[13])

        self.assertEqual(browser.calls, [("open_product",), ("sort_product_table", "成交件数")])


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Implement capture step dispatcher**

Create `live-bigscreen-capture/bigscreen_capture/capture_steps.py`:

```python
from __future__ import annotations

from .models import CaptureStep


FLOW_METRICS = {
    "05": "在线人数",
    "06": "访问人数",
    "07": "人均停留时长",
    "08": "成交人数",
    "09": "成交金额",
    "10": "成交单量",
    "11": "直播曝光点击率",
}


def run_capture_step(browser, step: CaptureStep) -> None:
    if step.code == "01":
        browser.open_overview()
    elif step.code == "02":
        browser.open_overview()
        browser.select_overview_live_tab("在线")
    elif step.code == "03":
        browser.open_overview()
        browser.select_overview_live_tab("成交")
    elif step.code == "04":
        browser.open_overview()
        browser.select_overview_product_scope("挂袋商品")
    elif step.code in FLOW_METRICS:
        browser.open_flow()
        browser.select_flow_metric(FLOW_METRICS[step.code])
    elif step.code == "12":
        browser.open_overview()
        browser.select_user_portrait("访问用户")
    elif step.code == "13":
        browser.open_overview()
        browser.select_user_portrait("成交用户")
    elif step.code == "14":
        browser.open_product()
        browser.sort_product_table("成交件数")
    elif step.code == "15":
        browser.open_product()
        browser.sort_product_table("成交金额")
    else:
        raise ValueError(f"未知截图项: {step.code}")
```

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest tests/test_capture_steps.py -v
```

Expected: PASS.

**Step 3: Implement Playwright browser adapter**

Create `live-bigscreen-capture/bigscreen_capture/browser.py`.

Key implementation:

```python
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

PRICE_AUDIT_ROOT = Path(__file__).resolve().parents[2] / "live-sku-price-audit"
if str(PRICE_AUDIT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRICE_AUDIT_ROOT))

from utils.browser_manager import BrowserManager  # type: ignore


class BigscreenBrowser:
    def __init__(self, url: str, auth_file: str | Path, headless: bool = False, log_callback: Optional[Callable[[str], None]] = None):
        self.url = url
        self.auth_file = Path(auth_file)
        self.headless = headless
        self._log = log_callback or (lambda _: None)
        self.browser_manager: BrowserManager | None = None
        self.page = None

    def start(self):
        self.browser_manager = BrowserManager(str(self.auth_file), headless=self.headless, block_resources=False)
        self.page = self.browser_manager.start()
        self.open_overview()
        return self

    def check_login_status(self) -> bool:
        if self.browser_manager is None:
            return False
        return self.browser_manager.check_login_status()

    def open_login_page(self):
        if self.browser_manager is None:
            raise RuntimeError("浏览器未启动")
        self.browser_manager.open_login_page()

    def save_auth_state(self):
        if self.browser_manager is not None:
            self.browser_manager.save_auth_state()

    def close(self, force: bool = False):
        if self.browser_manager is not None:
            self.browser_manager.close(force=force)

    def open_overview(self):
        self._goto_bigscreen()
        self._click_sidebar("概览")

    def open_flow(self):
        self._goto_bigscreen()
        self._click_sidebar("流量")

    def open_product(self):
        self._goto_bigscreen()
        self._click_sidebar("商品")

    def select_overview_live_tab(self, label: str):
        self._click_text(label)
        self._wait_stable()

    def select_overview_product_scope(self, label: str):
        self._click_text("全部商品")
        self._click_text(label)
        self._wait_stable()

    def select_flow_metric(self, label: str):
        self._click_text(label)
        self._wait_stable()

    def select_user_portrait(self, label: str):
        self._click_text("访问用户")
        self._click_text(label)
        self._wait_stable()

    def sort_product_table(self, label: str):
        self._click_text(label)
        self._wait_stable()

    def screenshot(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=False)

    def _goto_bigscreen(self):
        if self.page is None:
            raise RuntimeError("浏览器未启动")
        if "jlive.jd.com/bigScreen" not in (self.page.url or ""):
            self.page.goto(self.url, wait_until="networkidle", timeout=60000)
        self._wait_stable()

    def _click_sidebar(self, label: str):
        self._click_text(label)
        self._wait_stable()

    def _click_text(self, label: str):
        locator = self.page.get_by_text(label, exact=True)
        if locator.count() < 1:
            raise RuntimeError(f"未找到页面元素: {label}")
        locator.first.click(force=True)

    def _wait_stable(self):
        self.page.wait_for_timeout(1500)
```

During execution, refine selectors from real page failures. Prefer scoped locators once failures identify duplicate text. Do not over-engineer selectors before a real run.

**Step 4: Commit**

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
git add live-bigscreen-capture
git commit -m "feat: add bigscreen capture browser steps"
```

### Task 4: Synchronous Capture Service and Unit Tests

**Files:**
- Create: `live-bigscreen-capture/bigscreen_capture/service.py`
- Create: `live-bigscreen-capture/tests/test_service.py`

**Step 1: Write failing service test using a fake browser**

Create `live-bigscreen-capture/tests/test_service.py`:

```python
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from bigscreen_capture.service import capture_once


class FakeBrowser:
    def __init__(self, url, auth_file, headless=False, log_callback=None):
        self.url = url
        self.calls = []

    def start(self):
        self.calls.append("start")
        return self

    def open_overview(self):
        self.calls.append("open_overview")

    def select_overview_live_tab(self, label):
        self.calls.append(("select_overview_live_tab", label))

    def select_overview_product_scope(self, label):
        self.calls.append(("select_overview_product_scope", label))

    def open_flow(self):
        self.calls.append("open_flow")

    def select_flow_metric(self, label):
        self.calls.append(("select_flow_metric", label))

    def select_user_portrait(self, label):
        self.calls.append(("select_user_portrait", label))

    def open_product(self):
        self.calls.append("open_product")

    def sort_product_table(self, label):
        self.calls.append(("sort_product_table", label))

    def screenshot(self, path):
        Path(path).write_bytes(b"png")

    def close(self, force=False):
        self.calls.append(("close", force))


class CaptureServiceTest(unittest.TestCase):
    def test_capture_once_writes_15_images_manifest_and_zip(self):
        output_dir = Path(tempfile.mkdtemp())

        result = capture_once(
            url="https://jlive.jd.com/bigScreen?id=46794566",
            output_dir=output_dir,
            planned_slot="19:00",
            captured_at=datetime(2026, 7, 8, 19, 0, 0),
            auth_file=output_dir / "jd_auth.json",
            browser_factory=FakeBrowser,
        )

        self.assertEqual(result.room_id, "46794566")
        self.assertEqual(result.success_count, 15)
        self.assertEqual(len(list(output_dir.rglob("*.png"))), 15)
        self.assertTrue(result.manifest_file.exists())
        self.assertTrue(result.zip_file.exists())


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Implement service**

Create `live-bigscreen-capture/bigscreen_capture/service.py`.

Key implementation:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

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
    records: list[CaptureRecord]
    manifest_file: Path
    zip_file: Path

    @property
    def success_count(self) -> int:
        return sum(1 for record in self.records if record.status == "成功")

    @property
    def fail_count(self) -> int:
        return sum(1 for record in self.records if record.status == "失败")


def capture_once(
    url: str,
    output_dir: Path,
    planned_slot: str,
    captured_at: datetime,
    auth_file: Path,
    browser_factory: Callable = BigscreenBrowser,
    should_stop: Callable[[], bool] | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> CaptureOnceResult:
    parsed = parse_bigscreen_url(url)
    log = log_callback or (lambda _: None)
    slot_dir = output_dir / f"{captured_at:%Y%m%d_%H%M%S}"
    records: list[CaptureRecord] = []
    browser = browser_factory(parsed.url, auth_file=auth_file, headless=False, log_callback=log).start()
    try:
        for step in CAPTURE_STEPS:
            filename = screenshot_filename(parsed.room_id, captured_at, step.code, step.filename_label)
            path = slot_dir / filename
            if should_stop and should_stop():
                records.append(CaptureRecord(planned_slot, None, parsed.room_id, step.code, step.name, filename, "已停止", path=path))
                continue
            try:
                log(f"开始截图 {step.code} {step.name}")
                run_capture_step(browser, step)
                browser.screenshot(path)
                records.append(CaptureRecord(planned_slot, datetime.now(), parsed.room_id, step.code, step.name, filename, "成功", path=path))
            except Exception as exc:
                records.append(CaptureRecord(planned_slot, datetime.now(), parsed.room_id, step.code, step.name, filename, "失败", str(exc), path=path))
                log(f"截图失败 {step.code} {step.name}: {exc}")
    finally:
        browser.close(force=True)

    manifest_file = write_manifest_workbook(output_dir, records)
    zip_file = write_zip_archive(output_dir, parsed.room_id, captured_at)
    return CaptureOnceResult(parsed.room_id, output_dir, records, manifest_file, zip_file)
```

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-bigscreen-capture
python3 -m unittest tests/test_service.py -v
```

Expected: PASS.

**Step 3: Commit**

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
git add live-bigscreen-capture
git commit -m "feat: add bigscreen capture service"
```

### Task 5: live-web Backend Routes and Task State

**Files:**
- Modify: `live-web/app.py`
- Modify: `live-web/tests/test_routes.py`

**Step 1: Write failing route tests**

Add tests to `live-web/tests/test_routes.py`:

```python
    def test_bigscreen_capture_preview_returns_room_id_and_hours(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        client = app.test_client()

        response = client.post(
            "/api/bigscreen-capture/preview",
            json={"url": "https://jlive.jd.com/bigScreen?id=46794566"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["room_id"], "46794566")
        self.assertIn("19:00", payload["hour_options"])

    def test_bigscreen_capture_rejects_bad_url(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        client = app.test_client()

        response = client.post("/api/bigscreen-capture/preview", json={"url": "https://example.com"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    def test_bigscreen_capture_capture_now_uses_service(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        client = app.test_client()

        with patch("app.capture_bigscreen_once") as fake_capture:
            fake_capture.return_value.room_id = "46794566"
            fake_capture.return_value.success_count = 15
            fake_capture.return_value.fail_count = 0
            fake_capture.return_value.zip_file = app.config["BIGSCREEN_OUTPUT_DIR"] / "result.zip"
            fake_capture.return_value.zip_file.write_bytes(b"zip")

            response = client.post(
                "/api/bigscreen-capture/capture-now",
                json={"url": "https://jlive.jd.com/bigScreen?id=46794566"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertEqual(response.get_json()["success_count"], 15)
```

**Step 2: Run route tests to verify failure**

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-web
python3 -m unittest tests/test_routes.py -v
```

Expected: FAIL because routes and imports do not exist.

**Step 3: Add module path, runtime config, and imports**

Modify `live-web/app.py` near the existing roots:

```python
BIGSCREEN_CAPTURE_ROOT = LIVE_DIR / "live-bigscreen-capture"
if str(BIGSCREEN_CAPTURE_ROOT) not in sys.path:
    sys.path.insert(0, str(BIGSCREEN_CAPTURE_ROOT))
```

Add imports:

```python
from bigscreen_capture.schedule import build_hour_options
from bigscreen_capture.service import capture_once as capture_bigscreen_once
from bigscreen_capture.url_parser import BigscreenUrlError, parse_bigscreen_url
```

Inside `create_app`, add directories:

```python
bigscreen_output_dir = runtime_dir / "output" / "bigscreen-capture"
bigscreen_output_dir.mkdir(parents=True, exist_ok=True)
app.config["BIGSCREEN_OUTPUT_DIR"] = bigscreen_output_dir
app.config["BIGSCREEN_RESULTS"] = {}
app.config["BIGSCREEN_AUTH_FILE"] = PRICE_AUDIT_ROOT / "jd_auth.json"
```

Update `_cleanup_runtime_for_app` to create `BIGSCREEN_OUTPUT_DIR`.

**Step 4: Add preview and capture-now routes**

Add routes inside `create_app`:

```python
    @app.route("/api/bigscreen-capture/preview", methods=["POST"])
    def preview_bigscreen_capture():
        data = request.get_json(silent=True) or {}
        try:
            parsed = parse_bigscreen_url(data.get("url", ""))
        except BigscreenUrlError as exc:
            return _json_error(str(exc))
        return jsonify({
            "success": True,
            "room_id": parsed.room_id,
            "hour_options": build_hour_options(12, 23),
        })

    @app.route("/api/bigscreen-capture/capture-now", methods=["POST"])
    def capture_bigscreen_now():
        _cleanup_runtime_for_app(app)
        data = request.get_json(silent=True) or {}
        try:
            parsed = parse_bigscreen_url(data.get("url", ""))
        except BigscreenUrlError as exc:
            return _json_error(str(exc))

        task_id = uuid.uuid4().hex
        output_dir = app.config["BIGSCREEN_OUTPUT_DIR"] / task_id
        result = capture_bigscreen_once(
            url=parsed.url,
            output_dir=output_dir,
            planned_slot="立即截图",
            captured_at=datetime.now(),
            auth_file=app.config["BIGSCREEN_AUTH_FILE"],
        )
        app.config["BIGSCREEN_RESULTS"][task_id] = {"zip": result.zip_file}
        return jsonify({
            "success": True,
            "task_id": task_id,
            "room_id": result.room_id,
            "success_count": result.success_count,
            "fail_count": result.fail_count,
            "download_url": url_for("download_bigscreen_capture", task_id=task_id),
        })

    @app.route("/api/bigscreen-capture/download/<task_id>")
    def download_bigscreen_capture(task_id):
        result = app.config["BIGSCREEN_RESULTS"].get(task_id)
        if not result or not Path(result["zip"]).is_file():
            return _json_error("结果文件不存在", status_code=404)
        return send_file(result["zip"], as_attachment=True)
```

Also import `datetime` at the top:

```python
from datetime import datetime
```

**Step 5: Run route tests to verify pass**

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-web
python3 -m unittest tests/test_routes.py -v
```

Expected: PASS.

**Step 6: Add scheduled start/status/stop routes**

After `capture-now` works, extend with thread-backed scheduled task:

- Status dict: `_initial_bigscreen_status()`
- Routes:
  - `/api/bigscreen-capture/start`
  - `/api/bigscreen-capture/status`
  - `/api/bigscreen-capture/stop`
  - `/api/bigscreen-capture/continue`
- Thread target loops through planned slots, sleeps until each whole-hour run time, calls `capture_bigscreen_once`, updates counts and result ZIP.
- Stop flag interrupts waiting and prevents later slots.

Add focused tests for:

- start rejects empty slots
- status returns initial shape
- stop sets `stopping=True`

**Step 7: Commit**

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
git add live-web/app.py live-web/tests/test_routes.py
git commit -m "feat: add bigscreen capture web routes"
```

### Task 6: Web UI Tab and Client-Side Flow

**Files:**
- Modify: `live-web/templates/index.html`
- Modify: `live-web/tests/test_web_template.py`

**Step 1: Write failing template tests**

Add to `live-web/tests/test_web_template.py`:

```python
    def test_index_contains_bigscreen_capture_panel(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("蓝屏自动截图", html)
        self.assertIn('id="bigscreenCapturePanel"', html)
        self.assertIn('id="bigscreenUrlInput"', html)
        self.assertIn('id="bigscreenHourGrid"', html)
        self.assertIn("/api/bigscreen-capture/preview", html)
        self.assertIn("/api/bigscreen-capture/start", html)
        self.assertIn("/api/bigscreen-capture/capture-now", html)
        self.assertIn("/api/bigscreen-capture/download", html)
```

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-web
python3 -m unittest tests/test_web_template.py -v
```

Expected: FAIL.

**Step 2: Add tab and panel markup**

Modify the `.tool-tabs` grid to four columns:

```css
.tool-tabs {
    grid-template-columns: 1fr 1fr 1fr 1fr;
}
```

Add tab:

```html
<button class="tool-tab" data-tool="bigscreenCapturePanel">蓝屏自动截图</button>
```

Add panel:

```html
<section class="tool-panel" id="bigscreenCapturePanel">
    <div class="card">
        <div class="section-title">蓝屏页面</div>
        <div class="form-group">
            <label class="form-label" for="bigscreenUrlInput">蓝屏页面链接</label>
            <input class="form-input" id="bigscreenUrlInput" placeholder="https://jlive.jd.com/bigScreen?id=46794566">
        </div>
        <div class="form-row" style="margin-top: 12px;">
            <button class="btn btn-secondary" id="bigscreenPreviewBtn">识别链接</button>
            <button class="btn btn-secondary" id="bigscreenCaptureNowBtn">立即截图一次</button>
        </div>
        <div class="status-message" id="bigscreenStatusMessage"></div>
    </div>

    <div class="card">
        <div class="section-title">截图整点</div>
        <div class="hour-grid" id="bigscreenHourGrid"></div>
        <div class="form-row" style="margin-top: 12px;">
            <div class="form-group">
                <label class="form-label" for="bigscreenStartHour">开始整点</label>
                <select class="form-input" id="bigscreenStartHour"></select>
            </div>
            <div class="form-group">
                <label class="form-label" for="bigscreenEndHour">结束整点</label>
                <select class="form-input" id="bigscreenEndHour"></select>
            </div>
            <button class="btn btn-secondary" id="bigscreenGenerateHoursBtn">生成整点</button>
        </div>
        <div class="action-row">
            <button class="btn btn-primary" id="bigscreenStartBtn">开始自动截图</button>
            <button class="btn btn-secondary" id="bigscreenStopBtn" style="display:none;">停止任务</button>
            <button class="btn btn-success" id="bigscreenDownloadBtn" style="display:none;">下载截图包</button>
        </div>
    </div>

    <div class="card progress-section" id="bigscreenProgressCard">
        <div class="summary-grid" id="bigscreenSummary"></div>
        <div class="log-container" id="bigscreenLogContainer"></div>
    </div>
</section>
```

Add CSS for `.hour-grid` and selected buttons.

**Step 3: Add JavaScript flow**

Add functions:

- `renderBigscreenHours(hours)`
- `getSelectedBigscreenHours()`
- `previewBigscreenUrl()`
- `startBigscreenCapture()`
- `captureBigscreenNow()`
- `pollBigscreenStatus()`
- `renderBigscreenStatus(data)`
- `stopBigscreenCapture()`

The shared login modal continue button should also notify:

```javascript
fetch('/api/bigscreen-capture/continue', { method: 'POST' });
```

**Step 4: Run template tests**

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-web
python3 -m unittest tests/test_web_template.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
git add live-web/templates/index.html live-web/tests/test_web_template.py
git commit -m "feat: add bigscreen capture web panel"
```

### Task 7: Packaging, Requirements, and README

**Files:**
- Create: `live-bigscreen-capture/requirements.txt`
- Create: `live-bigscreen-capture/README.md`
- Modify: `.github/workflows/build-windows.yml`
- Modify: `启动直播工具.bat`
- Modify: `README.md`
- Modify: `tests/test_windows_packaging.py`

**Step 1: Write failing packaging test**

Extend `tests/test_windows_packaging.py`:

```python
        self.assertIn("live-bigscreen-capture", content)
        self.assertIn("bigscreen_capture", content)
```

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
python3 -m unittest tests/test_windows_packaging.py -v
```

Expected: FAIL until workflow is updated.

**Step 2: Add module requirements**

Create `live-bigscreen-capture/requirements.txt`:

```text
openpyxl>=3.1.0
playwright>=1.40.0
```

**Step 3: Update GitHub Actions packaging**

Modify `.github/workflows/build-windows.yml`:

- Install requirements:

```powershell
pip install -r live-bigscreen-capture/requirements.txt
```

- Add path:

```powershell
--paths "live-bigscreen-capture" `
```

- Add hidden imports:

```powershell
--hidden-import bigscreen_capture `
--hidden-import bigscreen_capture.service `
--hidden-import bigscreen_capture.browser `
--hidden-import bigscreen_capture.capture_steps `
```

- Add data:

```powershell
$bigscreenPackage = "live-bigscreen-capture/bigscreen_capture"
--add-data "$bigscreenPackage;live-bigscreen-capture/bigscreen_capture" `
```

- Verify output includes:

```powershell
"live-bigscreen-capture/bigscreen_capture"
```

**Step 4: Update Windows launcher dependency install**

Modify `启动直播工具.bat` source-mode install block:

```bat
%PYTHON_CMD% -m pip install -r "live-bigscreen-capture\requirements.txt"
```

**Step 5: Update README**

Add `蓝屏自动截图` to:

- Intro feature list
- Feature table
- Quick start tab list
- Usage guide
- Project structure
- Test commands

**Step 6: Run packaging tests**

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
python3 -m unittest tests/test_windows_packaging.py -v
```

Expected: PASS.

**Step 7: Commit**

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
git add live-bigscreen-capture/requirements.txt live-bigscreen-capture/README.md .github/workflows/build-windows.yml 启动直播工具.bat README.md tests/test_windows_packaging.py
git commit -m "chore: package bigscreen capture tool"
```

### Task 8: Full Test Pass and Manual Real-Link Verification

**Files:**
- Modify as needed from failures only.

**Step 1: Run all local unit tests**

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live
python3 -m unittest discover -s tests -p "test_*.py" -v

cd live-bigscreen-capture
python3 -m unittest discover -s tests -p "test_*.py" -v

cd ../live-web
python3 -m unittest discover -s tests -p "test_*.py" -v

cd ../live-promotion-binding
python3 -m unittest discover -s tests -p "test_*.py" -v

cd ../live-sku-price-audit
python3 -m unittest discover -s tests -p "test_*.py" -v

cd ../live-room-creator
python3 -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS, except pre-existing unrelated failures must be documented with exact failure text.

**Step 2: Start local web server**

Run:

```bash
cd /Users/zhangyaolong.5/Friday/idea_workspace/me/live/live-web
./start.sh
```

Expected:

```text
http://127.0.0.1:8080
```

**Step 3: Manual real-link verification**

Use:

```text
https://jlive.jd.com/bigScreen?id=46794566
```

In `蓝屏自动截图`:

1. Paste the link.
2. Click `识别链接`.
3. Click `立即截图一次`.
4. Complete login if prompted.
5. Confirm ZIP download is available.
6. Confirm output contains 15 screenshots.

Required visual checks:

- `02_渠道流量饼状图_在线` shows `概览` left `直播间` card with `在线` selected.
- `03_渠道成交饼状图_成交` shows `概览` left `直播间` card with `成交` selected.
- `04_挂袋数据` shows overview page after the center top product dropdown is switched to `挂袋商品`.
- `14_订单Top10` shows product page sorted by `成交件数`.
- `15_GMVTop10` shows product page sorted by `成交金额`.

**Step 4: Final commit for fixes**

If manual verification requires selector fixes:

```bash
git add <changed files>
git commit -m "fix: stabilize bigscreen capture selectors"
```

**Step 5: Final status**

Run:

```bash
git status --short
```

Expected: clean, unless generated runtime files are ignored.
