from pathlib import Path
import unittest


LIVE_ROOT = Path(__file__).resolve().parents[1]


class PlaywrightRuntimeConfigTest(unittest.TestCase):
    def test_all_browser_modules_require_chromium_channel_capable_playwright(self):
        requirement_files = (
            "live-web/requirements.txt",
            "live-sku-price-audit/requirements.txt",
            "live-room-creator/requirements.txt",
            "live-bigscreen-capture/requirements.txt",
            "product-selection-agent/requirements.txt",
        )

        for relative_path in requirement_files:
            with self.subTest(requirements=relative_path):
                content = (LIVE_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("playwright>=1.50,<2", content)


if __name__ == "__main__":
    unittest.main()
