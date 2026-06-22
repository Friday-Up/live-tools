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
        self.assertIn("直播 SKU 价格巡检工具", html)
        self.assertIn("SKU 测价", html)
        self.assertIn("绑定券码/促销ID", html)
        self.assertIn("生成导入模板", html)
        self.assertIn("promotionColumnMapping", html)
        self.assertIn("promotionSkuColumn", html)
        self.assertIn("promotionCodeColumn", html)
        self.assertIn("promotionProductNameColumn", html)
        self.assertIn("/api/promotion-binding/preview", html)
        self.assertIn("/api/promotion-binding/generate", html)
        self.assertIn("upload-area", html)
        self.assertIn("progress-section", html)
        self.assertIn("log-container", html)


if __name__ == "__main__":
    unittest.main()
