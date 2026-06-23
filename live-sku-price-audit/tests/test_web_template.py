from pathlib import Path
import unittest


class WebTemplateTests(unittest.TestCase):
    def test_web_ui_does_not_show_input_directory_file_picker(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertNotIn("existingFilePicker", html)
        self.assertNotIn("loadExistingFiles", html)
        self.assertNotIn("/api/list_files", html)
        self.assertNotIn("或选择 input 目录中的文件", html)

    def test_progress_uses_completed_count_for_concurrent_runs(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("const completed = Math.min(data.current || 0, data.total || 0);", html)
        self.assertIn("(completed / data.total) * 100", html)
        self.assertNotIn("data.current - 1", html)

    def test_result_summary_shows_failed_count(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('id="resultFailed"', html)
        self.assertIn("异常数量", html)
        self.assertIn("const failed = data.fail_count || 0;", html)
        self.assertIn("document.getElementById('resultFailed').textContent = failed;", html)


if __name__ == "__main__":
    unittest.main()
