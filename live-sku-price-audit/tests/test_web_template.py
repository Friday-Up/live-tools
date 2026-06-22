from pathlib import Path
import unittest


class WebTemplateTests(unittest.TestCase):
    def test_web_ui_does_not_show_input_directory_file_picker(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertNotIn("existingFilePicker", html)
        self.assertNotIn("loadExistingFiles", html)
        self.assertNotIn("/api/list_files", html)
        self.assertNotIn("或选择 input 目录中的文件", html)


if __name__ == "__main__":
    unittest.main()
