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
                "excel_download_url": "",
            },
        )

    def test_start_runs_service_and_exposes_excel_download_only(self):
        received_options = {}

        def fake_execute(output_dir, headless, allow_partial, context):
            received_options.update(
                {"headless": headless, "allow_partial": allow_partial}
            )
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            excel_path = output_dir / "selection.xlsx"
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
        self.assertTrue(received_options["allow_partial"])

        excel_response = self.client.get(status["excel_download_url"])
        self.assertEqual(excel_response.data, b"xlsx")
        excel_response.close()
        self.assertNotIn("json_download_url", status)

    def test_web_always_allows_partial_source_results(self):
        received_options = {}

        def fake_execute(**kwargs):
            received_options.update(kwargs)
            raise RuntimeError("stop after capturing options")

        with mock.patch.object(web_app.threading, "Thread", ImmediateThread), mock.patch.object(
            web_app, "execute_product_selection", side_effect=fake_execute
        ):
            self.client.post(
                "/api/product-selection/start",
                json={"allow_partial": False},
            )

        self.assertTrue(received_options["allow_partial"])

    def test_rejects_duplicate_start_and_stop_marks_task_stopping(self):
        with mock.patch.object(web_app.threading, "Thread", DormantThread):
            first = self.client.post("/api/product-selection/start", json={})
            second = self.client.post("/api/product-selection/start", json={})
            stopped = self.client.post("/api/product-selection/stop")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(stopped.status_code, 200)
        self.assertTrue(stopped.get_json()["stopping"])

    def test_download_rejects_unknown_task(self):
        unknown = self.client.get("/api/product-selection/download/missing")

        self.assertEqual(unknown.status_code, 404)

    def test_worker_exposes_failed_and_cancelled_states(self):
        with mock.patch.object(web_app.threading, "Thread", ImmediateThread), mock.patch.object(
            web_app,
            "execute_product_selection",
            side_effect=RuntimeError("抓取失败"),
        ):
            failed = self.client.post("/api/product-selection/start", json={})

        self.assertEqual(failed.status_code, 202)
        failed_status = self.client.get("/api/product-selection/status").get_json()
        self.assertEqual(failed_status["stage"], "failed")
        self.assertFalse(failed_status["success"])
        self.assertIn("抓取失败", failed_status["error"])

        with mock.patch.object(web_app.threading, "Thread", ImmediateThread), mock.patch.object(
            web_app,
            "execute_product_selection",
            side_effect=web_app.SelectionCancelled("选品任务已停止"),
        ):
            cancelled = self.client.post("/api/product-selection/start", json={})

        self.assertEqual(cancelled.status_code, 202)
        cancelled_status = self.client.get("/api/product-selection/status").get_json()
        self.assertEqual(cancelled_status["stage"], "cancelled")
        self.assertFalse(cancelled_status["success"])
        self.assertIn("已停止", cancelled_status["error"])


if __name__ == "__main__":
    unittest.main()
