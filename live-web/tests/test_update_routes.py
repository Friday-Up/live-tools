from pathlib import Path
import tempfile
import unittest

from app import create_app


class FakeUpdateManager:
    def __init__(self):
        self.calls = []
        self.state = {
            "supported": True,
            "stage": "available",
            "current_version": "0.5.0",
            "latest_version": "0.5.1",
        }

    def status(self):
        self.calls.append("status")
        return dict(self.state)

    def start_check(self):
        self.calls.append("check")
        return dict(self.state)

    def start_download(self):
        self.calls.append("download")
        self.state["stage"] = "downloading"
        return dict(self.state)


class UpdateRoutesTest(unittest.TestCase):
    def setUp(self):
        self.manager = FakeUpdateManager()
        self.app = create_app(
            base_dir=Path(tempfile.mkdtemp()),
            update_manager=self.manager,
        )
        self.client = self.app.test_client()

    def test_status_and_check_routes(self):
        self.assertEqual(self.client.get("/api/update/status").status_code, 200)
        self.assertEqual(self.client.post("/api/update/check").status_code, 200)
        self.assertEqual(self.manager.calls, ["status", "check"])

    def test_download_requires_same_origin_header(self):
        response = self.client.post("/api/update/download")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("download", self.manager.calls)

        response = self.client.post(
            "/api/update/download",
            headers={"X-Live-Tools-Update": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["stage"], "downloading")

    def test_install_requires_same_origin_header(self):
        response = self.client.post("/api/update/install")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
