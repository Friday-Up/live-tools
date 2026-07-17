from pathlib import Path
import unittest


class CommandLineEntryTest(unittest.TestCase):
    def test_cli_captures_low_price_screenshots_before_writing_results(self):
        source = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("capture_low_price_result_screenshots_with_page_factory", source)
        self.assertLess(
            source.index("capture_low_price_result_screenshots_with_page_factory("),
            source.index("write_results("),
        )

    def test_cli_does_not_delete_playwright_cli_state(self):
        source = Path("main.py").read_text(encoding="utf-8")

        self.assertNotIn("utils.cleanup", source)
        self.assertNotIn("auto_cleanup", source)


if __name__ == "__main__":
    unittest.main()
