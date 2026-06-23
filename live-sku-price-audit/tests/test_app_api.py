import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

import app as web_app


def make_excel_file():
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    wb = Workbook()
    ws = wb.active
    ws.append(["商品SKU"])
    ws.append(["100264886683"])
    wb.save(tmp.name)
    return tmp.name


class AppApiTests(unittest.TestCase):
    def setUp(self):
        web_app.app.config["TESTING"] = False
        self.client = web_app.app.test_client()

    def test_start_rejects_invalid_threshold_with_json_error(self):
        response = self.client.post(
            "/api/start",
            json={"file": make_excel_file(), "threshold": "abc"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["success"], False)
        self.assertIn("价格门槛", response.get_json()["error"])

    def test_start_rejects_path_outside_input_directory(self):
        response = self.client.post(
            "/api/start",
            json={"file": make_excel_file(), "threshold": 6},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["success"], False)
        self.assertIn("请先上传", response.get_json()["error"])

    def test_audit_outputs_capture_low_price_screenshots_before_writing_results(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        main_source = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("capture_low_price_result_screenshots_with_page_factory", app_source)
        self.assertLess(
            app_source.index("capture_low_price_result_screenshots_with_page_factory("),
            app_source.index("write_results("),
        )
        self.assertIn("capture_low_price_result_screenshots_with_page_factory", main_source)
        self.assertLess(
            main_source.index("capture_low_price_result_screenshots_with_page_factory("),
            main_source.index("write_results("),
        )

    def test_price_audit_worker_browser_visibility_is_configurable(self):
        app_source = Path("app.py").read_text(encoding="utf-8")

        worker_factory_source = app_source[app_source.index("def create_worker_page"):app_source.index("def on_result")]
        self.assertIn("show_browser = bool(data.get('show_browser'))", app_source)
        self.assertIn("args=(input_file, threshold, show_browser)", app_source)
        self.assertIn("worker_headless = not show_browser", app_source)
        self.assertIn("headless=worker_headless", worker_factory_source)

    def test_price_audit_scan_workers_block_images_but_screenshot_workers_keep_images(self):
        app_source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn("block_images=block_images", app_source)
        self.assertIn(
            "page_factory=lambda worker_index: create_worker_page(worker_index, block_images=True)",
            app_source,
        )
        self.assertIn(
            "page_factory=lambda worker_index: create_worker_page(worker_index, block_images=False)",
            app_source,
        )

    def test_price_audit_closes_login_browser_and_returns_to_worker_browser_mode_after_login(self):
        app_source = Path("app.py").read_text(encoding="utf-8")

        self.assertGreaterEqual(
            app_source.count("browser = BrowserManager(CONFIG['auth_file'], headless=worker_headless)"),
            2,
        )
        self.assertIn("登录成功后切回测价浏览器", app_source)
        self.assertIn("检查测价浏览器登录状态", app_source)
        self.assertIn("登录状态未能同步到测价浏览器", app_source)
        self.assertIn("低价截图：应补", app_source)

    def test_price_audit_login_browser_disables_resource_blocking(self):
        app_source = Path("app.py").read_text(encoding="utf-8")

        self.assertGreaterEqual(
            app_source.count("headless=False, block_resources=False"),
            2,
        )

    def test_stop_request_closes_active_browsers(self):
        app_source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn("def close_current_browsers", app_source)
        self.assertIn("close_current_browsers()", app_source[app_source.index("def stop_audit"):])


if __name__ == "__main__":
    unittest.main()
