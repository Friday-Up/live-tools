import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
