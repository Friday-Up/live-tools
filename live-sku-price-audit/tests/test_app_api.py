import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_parse_sku_input_supports_multiple_separators_and_dedup(self):
        self.assertEqual(
            web_app.parse_sku_input("100264886683,48279162646;100264886683"),
            ["100264886683", "48279162646"],
        )
        self.assertEqual(
            web_app.parse_sku_input("100264886683，48279162646；100264886683"),
            ["100264886683", "48279162646"],
        )
        self.assertEqual(
            web_app.parse_sku_input("100264886683\n48279162646\t100264886683"),
            ["100264886683", "48279162646"],
        )

    def test_start_from_skus_rejects_invalid_threshold_with_json_error(self):
        response = self.client.post(
            "/api/start-from-skus",
            json={"skus": "100264886683", "threshold": "abc"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["success"], False)
        self.assertIn("价格门槛", response.get_json()["error"])

    def test_start_from_skus_rejects_empty_input(self):
        response = self.client.post(
            "/api/start-from-skus",
            json={"skus": "", "threshold": 6},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["success"], False)
        self.assertIn("SKU", response.get_json()["error"])

    @patch.object(web_app, "run_audit_task")
    def test_start_from_skus_creates_input_file_and_returns_count(self, mock_run):
        response = self.client.post(
            "/api/start-from-skus",
            json={"skus": "100264886683,48279162646", "threshold": 6},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 2)
        mock_run.assert_called_once()

        # 清理生成的临时输入文件
        input_dir = Path(web_app.CONFIG["input_dir"])
        generated_files = list(input_dir.glob("页面输入SKU_*.xlsx"))
        self.assertTrue(generated_files, "应生成临时输入文件")
        for f in generated_files:
            f.unlink(missing_ok=True)

    def test_start_from_skus_rejects_whitespace_only_input(self):
        response = self.client.post(
            "/api/start-from-skus",
            json={"skus": "   \n\t  ", "threshold": 6},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["success"], False)
        self.assertIn("SKU", response.get_json()["error"])

    def test_start_from_skus_requests_cleanup_of_temp_input_file(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn("cleanup_input", app_source)
        self.assertIn("kwargs={'cleanup_input': True}", app_source)
        self.assertIn("def remove_file_with_retries", app_source)
        self.assertIn("remove_file_with_retries(input_file)", app_source)


if __name__ == "__main__":
    unittest.main()
