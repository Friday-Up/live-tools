import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from bigscreen_capture.service import capture_once, write_capture_bundle


class FakeBrowser:
    instances = []

    def __init__(self, url, auth_file, headless=False, log_callback=None):
        self.url = url
        self.headless = headless
        self.calls = []
        self.logged_in = True
        FakeBrowser.instances.append(self)

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
        self.calls.append(("screenshot", Path(path).name))
        Path(path).write_bytes(b"png")

    def close(self, force=False):
        self.calls.append(("close", force))

    def check_login_status(self):
        self.calls.append("check_login_status")
        return self.logged_in

    def get_room_name(self):
        self.calls.append("get_room_name")
        return "京东青春采销"

    def open_login_page(self):
        self.calls.append("open_login_page")

    def save_auth_state(self):
        self.calls.append("save_auth_state")


class CaptureServiceTest(unittest.TestCase):
    def setUp(self):
        FakeBrowser.instances = []

    def test_capture_once_writes_15_images_manifest_and_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

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
            self.assertEqual(result.fail_count, 0)
            self.assertEqual(len(list(output_dir.rglob("*.png"))), 15)
            self.assertTrue(result.manifest_file.exists())
            self.assertTrue(result.zip_file.exists())

    def test_capture_once_returns_live_room_account_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = capture_once(
                url="https://jlive.jd.com/bigScreen?id=46794566",
                output_dir=output_dir,
                planned_slot="19:00",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
                auth_file=output_dir / "jd_auth.json",
                browser_factory=FakeBrowser,
            )

            self.assertEqual(result.room_name, "京东青春采销")
            calls = FakeBrowser.instances[0].calls
            first_screenshot_index = next(
                index
                for index, call in enumerate(calls)
                if isinstance(call, tuple) and call[0] == "screenshot"
            )
            self.assertLess(calls.index("check_login_status"), calls.index("get_room_name"))
            self.assertLess(calls.index("get_room_name"), first_screenshot_index)

    def test_capture_once_continues_when_room_name_cannot_be_read(self):
        class RoomNameErrorBrowser(FakeBrowser):
            def get_room_name(self):
                self.calls.append("get_room_name")
                raise RuntimeError("账号名称节点加载超时")

        logs = []
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = capture_once(
                url="https://jlive.jd.com/bigScreen?id=46794566",
                output_dir=output_dir,
                planned_slot="19:00",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
                auth_file=output_dir / "jd_auth.json",
                browser_factory=RoomNameErrorBrowser,
                log_callback=logs.append,
            )

            self.assertEqual(result.room_name, "")
            self.assertEqual(result.success_count, 15)
            self.assertEqual(len(list(output_dir.rglob("*.png"))), 15)
            self.assertTrue(result.manifest_file.exists())
            self.assertTrue(result.zip_file.exists())
            self.assertIn(
                "读取直播间账号名称失败: 账号名称节点加载超时，继续截图",
                logs,
            )

    def test_capture_once_uses_headless_mode_unless_show_browser_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            capture_once(
                url="https://jlive.jd.com/bigScreen?id=46794566",
                output_dir=output_dir,
                planned_slot="19:00",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
                auth_file=output_dir / "jd_auth.json",
                browser_factory=FakeBrowser,
                show_browser=False,
            )

            self.assertTrue(FakeBrowser.instances[0].headless)

    def test_capture_once_can_show_browser_when_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            capture_once(
                url="https://jlive.jd.com/bigScreen?id=46794566",
                output_dir=output_dir,
                planned_slot="19:00",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
                auth_file=output_dir / "jd_auth.json",
                browser_factory=FakeBrowser,
                show_browser=True,
            )

            self.assertFalse(FakeBrowser.instances[0].headless)

    def test_capture_once_prompts_for_login_and_saves_auth_before_capturing(self):
        class LoginBrowser(FakeBrowser):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.logged_in = False

            def check_login_status(self):
                self.calls.append("check_login_status")
                if "open_login_page" in self.calls:
                    return True
                return False

        login_events = []
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = capture_once(
                url="https://jlive.jd.com/bigScreen?id=46794566",
                output_dir=output_dir,
                planned_slot="19:00",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
                auth_file=output_dir / "jd_auth.json",
                browser_factory=LoginBrowser,
                show_browser=True,
                on_login_required=lambda browser: login_events.append(browser),
                wait_for_login=lambda: True,
            )

            calls = LoginBrowser.instances[0].calls
            self.assertIn("open_login_page", calls)
            self.assertIn("save_auth_state", calls)
            self.assertEqual(len(login_events), 1)
            self.assertEqual(result.success_count, 15)

    def test_capture_once_counts_stopped_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = capture_once(
                url="https://jlive.jd.com/bigScreen?id=46794566",
                output_dir=output_dir,
                planned_slot="19:00",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
                auth_file=output_dir / "jd_auth.json",
                browser_factory=FakeBrowser,
                should_stop=lambda: True,
            )

            self.assertEqual(result.success_count, 0)
            self.assertEqual(result.fail_count, 0)
            self.assertEqual(result.stopped_count, 15)

    def test_capture_once_logs_step_and_archive_progress(self):
        logs = []
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            capture_once(
                url="https://jlive.jd.com/bigScreen?id=46794566",
                output_dir=output_dir,
                planned_slot="19:00",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
                auth_file=output_dir / "jd_auth.json",
                browser_factory=FakeBrowser,
                log_callback=logs.append,
            )

            self.assertTrue(any(log.startswith("截图成功 01 概览总览，用时 ") for log in logs))
            self.assertIn("开始生成截图清单和 ZIP", logs)
            self.assertTrue(any(log.startswith("截图清单和 ZIP 已生成，用时 ") for log in logs))

    def test_write_capture_bundle_combines_multiple_slot_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            first = output_dir / "1900" / "蓝屏数据截图_46794566__20260708_190000_01_概览总览.png"
            second = output_dir / "2000" / "蓝屏数据截图_46794566__20260708_200000_01_概览总览.png"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"png")
            second.write_bytes(b"png")
            records = [
                capture_record("19:00", "01", "概览总览", first),
                capture_record("20:00", "01", "概览总览", second),
            ]

            manifest, archive = write_capture_bundle(
                output_dir=output_dir,
                room_id="46794566",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
                records=records,
            )

            self.assertTrue(manifest.exists())
            self.assertTrue(archive.exists())
            self.assertIn("蓝屏数据截图_46794566__20260708.zip", archive.name)


def capture_record(planned_slot, step_code, step_name, path):
    from bigscreen_capture.models import CaptureRecord

    return CaptureRecord(
        planned_slot=planned_slot,
        executed_at=datetime(2026, 7, 8, 19, 0, 0),
        room_id="46794566",
        step_code=step_code,
        step_name=step_name,
        filename=path.name,
        status="成功",
        path=path,
    )


if __name__ == "__main__":
    unittest.main()
