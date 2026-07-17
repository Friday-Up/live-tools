from pathlib import Path
import unittest


LIVE_ROOT = Path(__file__).resolve().parents[1]


class WindowsPackagingTest(unittest.TestCase):
    def test_unified_windows_launcher_is_the_only_business_entry(self):
        launcher = LIVE_ROOT / "启动直播工具.bat"

        self.assertTrue(launcher.exists())
        content = launcher.read_text(encoding="utf-8")
        self.assertIn("Live-Tools-Web.exe", content)
        self.assertIn("live-web", content)
        self.assertIn('set "PYTHONUTF8=1"', content)
        self.assertIn('set "PYTHONIOENCODING=utf-8"', content)
        self.assertNotIn("启动测价工具", content)
        self.assertNotIn("SKU-Price-Audit", content)

    def test_live_web_windows_source_launcher_writes_service_log(self):
        launcher = LIVE_ROOT / "live-web" / "start.bat"

        self.assertTrue(launcher.exists())
        content = launcher.read_text(encoding="utf-8")
        self.assertIn('set PYTHONUTF8=1', content)
        self.assertIn('set PYTHONIOENCODING=utf-8', content)
        self.assertIn('set "LOG_DIR=%~dp0runtime\\logs"', content)
        self.assertIn('Get-Date -Format yyyyMMdd', content)
        self.assertIn('%PYTHON_CMD% app.py >> "%LOG_FILE%" 2>&1', content)

    def test_legacy_price_audit_web_entry_is_not_kept_alongside_unified_web(self):
        price_root = LIVE_ROOT / "live-sku-price-audit"

        for legacy_path in (
            price_root / "app.py",
            price_root / "templates" / "index.html",
            price_root / "start.sh",
            price_root / "start.bat",
            price_root / "utils" / "cleanup.py",
        ):
            self.assertFalse(legacy_path.exists(), f"应删除旧入口: {legacy_path}")

    def test_github_workflow_builds_live_tools_from_unified_web_entry(self):
        workflow = LIVE_ROOT / ".github" / "workflows" / "build-windows.yml"

        self.assertTrue(workflow.exists())
        content = workflow.read_text(encoding="utf-8")

        self.assertIn("Build Live Tools Windows", content)
        self.assertIn("Live-Tools-Web", content)
        self.assertIn('--contents-directory "."', content)
        self.assertIn("live-web/app.py", content)
        self.assertIn("live-web/templates", content)
        self.assertIn("live-promotion-binding/assets", content)
        self.assertIn("live-promotion-binding/promotion_binding", content)
        self.assertIn("live-sku-price-audit/utils", content)
        self.assertIn("live-bigscreen-capture/bigscreen_capture", content)
        self.assertIn("pip install -r product-selection-agent/requirements.txt", content)
        self.assertIn("product-selection-agent/product_selection_agent", content)
        self.assertIn('--paths "product-selection-agent"', content)
        self.assertIn("--hidden-import product_selection_agent.service", content)
        self.assertIn("product-selection-agent/model-config.example.json", content)
        self.assertIn("Live-Tools-Windows.zip", content)
        self.assertIn("启动直播工具.bat", content)
        self.assertIn('Get-ChildItem -Path $distPath -Recurse -Directory -Filter "tests"', content)
        self.assertIn("Test directories must not be included in the Windows package", content)
        self.assertIn("Private model config must not be included in the Windows package", content)
        self.assertNotIn("启动测价工具.bat", content)


if __name__ == "__main__":
    unittest.main()
