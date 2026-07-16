import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import app as web_app


class ImmediateThread:
    def __init__(self, target, args=(), kwargs=None, daemon=None, **_unused):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class DormantThread(ImmediateThread):
    def start(self):
        return None


class ProductSelectionRoutesTest(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path(tempfile.mkdtemp())
        self.app = web_app.create_app(base_dir=self.base_dir)
        self.client = self.app.test_client()

    def test_status_has_stable_initial_shape(self):
        response = self.client.get("/api/product-selection/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "running": False,
                "stopping": False,
                "stage": "idle",
                "logs": [],
                "started_at": "",
                "finished_at": "",
                "task_id": "",
                "success": False,
                "error": "",
                "summary": {},
                "json_download_url": "",
                "excel_download_url": "",
            },
        )

    def test_start_runs_service_and_exposes_two_safe_downloads(self):
        def fake_execute(output_dir, headless, allow_partial, context):
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            json_path = output_dir / "selection.json"
            excel_path = output_dir / "selection.xlsx"
            json_path.write_text("{}", encoding="utf-8")
            excel_path.write_bytes(b"xlsx")
            context.log("[fetch] 已抓取")
            return SimpleNamespace(
                payload={
                    "items_count": 100,
                    "recommendation_mode": "llm_enhanced",
                    "diagnostics": {
                        "fetch_complete": True,
                        "ai_complete": False,
                        "sources": {"a": {}, "b": {}},
                    },
                    "selection": {"来源": {"类目": [{"sku_id": "1"}]}},
                },
                json_path=json_path,
                excel_path=excel_path,
            )

        with mock.patch.object(web_app.threading, "Thread", ImmediateThread), mock.patch.object(
            web_app, "execute_product_selection", side_effect=fake_execute
        ):
            response = self.client.post(
                "/api/product-selection/start",
                json={"headless": True, "allow_partial": False},
            )

        self.assertEqual(response.status_code, 202)
        status = self.client.get("/api/product-selection/status").get_json()
        self.assertFalse(status["running"])
        self.assertTrue(status["success"])
        self.assertEqual(status["stage"], "completed_with_warnings")
        self.assertEqual(status["summary"]["source_count"], 2)
        self.assertEqual(status["summary"]["category_count"], 1)
        self.assertEqual(status["summary"]["selected_count"], 1)
        self.assertIn("已抓取", "\n".join(status["logs"]))

        json_response = self.client.get(status["json_download_url"])
        excel_response = self.client.get(status["excel_download_url"])
        self.assertEqual(json_response.data, b"{}")
        self.assertEqual(excel_response.data, b"xlsx")
        json_response.close()
        excel_response.close()

    def test_rejects_duplicate_start_and_stop_marks_task_stopping(self):
        with mock.patch.object(web_app.threading, "Thread", DormantThread):
            first = self.client.post("/api/product-selection/start", json={})
            second = self.client.post("/api/product-selection/start", json={})
            stopped = self.client.post("/api/product-selection/stop")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(stopped.status_code, 200)
        self.assertTrue(stopped.get_json()["stopping"])

    def test_download_rejects_unknown_task_or_kind(self):
        unknown = self.client.get("/api/product-selection/download/missing/json")
        bad_kind = self.client.get("/api/product-selection/download/missing/secret")

        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(bad_kind.status_code, 404)


if __name__ == "__main__":
    unittest.main()
