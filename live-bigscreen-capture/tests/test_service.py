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


if __name__ == "__main__":
    unittest.main()
