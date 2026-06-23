import tempfile
import unittest
from pathlib import Path

from app import create_app


class WebTemplateTest(unittest.TestCase):
    def test_index_contains_price_audit_and_promotion_binding_tabs(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("直播运营工具", html)
        self.assertIn("SKU 测价、绑定券码/促销ID统一入口", html)
        self.assertNotIn("直播 SKU 价格巡检工具", html)
        self.assertIn("SKU 测价", html)
        self.assertIn("绑定券码/促销ID", html)
        self.assertIn("生成导入模板", html)
        self.assertIn("promotionColumnMapping", html)
        self.assertIn("promotionSkuColumn", html)
        self.assertIn("promotionCodeColumn", html)
        self.assertNotIn("promotionProductNameColumn", html)
        self.assertNotIn("promotionColumnPreview", html)
        self.assertNotIn("商品名称列", html)
        self.assertIn("/api/promotion-binding/preview", html)
        self.assertIn("/api/promotion-binding/generate", html)
        self.assertIn("upload-area", html)
        self.assertIn("progress-section", html)
        self.assertIn("log-container", html)

    def test_price_audit_progress_uses_completed_count_for_concurrent_runs(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("const completed = Math.min(data.current || 0, data.total || 0);", html)
        self.assertIn("(completed / data.total) * 100", html)
        self.assertNotIn("data.current - 1", html)

    def test_price_audit_result_summary_shows_failed_count(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn('id="resultFailed"', html)
        self.assertIn("异常数量", html)
        self.assertIn("const failed = data.fail_count || 0;", html)
        self.assertIn("document.getElementById('resultFailed').textContent = failed;", html)


if __name__ == "__main__":
    unittest.main()
