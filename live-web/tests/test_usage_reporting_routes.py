import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from app import create_app
from red_rain_creator.models import RedRainResult


class FakeUsageReporter:
    def __init__(self):
        self.events = []

    def report_async(self, **event):
        self.events.append(event)


class UsageReportingRoutesTest(unittest.TestCase):
    def test_red_rain_reports_ordered_lifecycle_and_existing_as_success(self):
        class ImmediateThread:
            def __init__(self, target, args, daemon=False):
                self.target = target
                self.args = args

            def start(self):
                self.target(*self.args)

        class ExistingBrowser:
            def __init__(self, **_kwargs):
                self.headless = True

            def start(self):
                return None

            def ensure_login(self, interactive=False):
                return True

            def create_activity(self, row):
                if row.red_packet_id == "pending":
                    return RedRainResult.from_row(row, status="待确认", error="等待后台确认")
                return RedRainResult.from_row(row, status="已存在", activity_id="A100")

            def close(self, force=True):
                return None

        reporter = FakeUsageReporter()
        app = create_app(base_dir=Path(tempfile.mkdtemp()), usage_reporter=reporter)
        client = app.test_client()
        preview = client.post(
            "/api/red-rain/preview",
            data={"file": (io.BytesIO(self._red_rain_workbook_bytes()), "红包雨.xlsx")},
            content_type="multipart/form-data",
        ).get_json()

        with patch("app.RedRainCreatorBrowser", ExistingBrowser), patch("app.threading.Thread", ImmediateThread):
            start = client.post("/api/red-rain/start", json={"task_id": preview["task_id"]})

        self.assertEqual(start.status_code, 200)
        download = client.get("/api/red-rain/download")
        self.assertEqual(download.status_code, 200)
        download.close()
        self.assertEqual(
            [event["action"] for event in reporter.events],
            ["upload", "task_start", "task_finish", "download"],
        )
        finish = reporter.events[2]
        self.assertEqual(finish["tool_code"], "red_rain_creator")
        self.assertEqual(finish["item_count"], 2)
        self.assertEqual(finish["success_count"], 1)
        self.assertEqual(finish["fail_count"], 0)
        self.assertEqual(finish["status"], "pending")
        self.assertEqual(finish["extra"]["existed_count"], 1)
        self.assertEqual(finish["extra"]["pending_count"], 1)

    def test_promotion_binding_reports_task_lifecycle_and_download(self):
        reporter = FakeUsageReporter()
        app = create_app(base_dir=Path(tempfile.mkdtemp()), usage_reporter=reporter)
        client = app.test_client()

        response = client.post(
            "/api/promotion-binding/generate",
            data={"file": (io.BytesIO(self._business_workbook_bytes()), "业务提报.xlsx")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        download_response = client.get(payload["template_download_url"])
        download_response.close()

        self.assertEqual(
            [event["action"] for event in reporter.events],
            ["task_start", "task_finish", "download"],
        )
        finish_event = reporter.events[1]
        self.assertEqual(finish_event["tool_code"], "promotion_binding")
        self.assertEqual(finish_event["task_id"], payload["task_id"])
        self.assertEqual(finish_event["status"], "success")
        self.assertEqual(finish_event["success_count"], 2)
        self.assertEqual(finish_event["fail_count"], 0)
        self.assertEqual(finish_event["extra"]["coupon_key_count"], 1)

    def test_bigscreen_capture_reports_room_identity_on_finish_and_download(self):
        class FakeCaptureResult:
            room_id = "46794566"
            room_name = "京东青春采销"
            success_count = 15
            fail_count = 0
            stopped_count = 0
            records = [object()]

        class ImmediateThread:
            def __init__(self, target, args):
                self.target = target
                self.args = args

            def start(self):
                self.target(*self.args)

        reporter = FakeUsageReporter()
        app = create_app(base_dir=Path(tempfile.mkdtemp()), usage_reporter=reporter)
        client = app.test_client()

        with patch("app.capture_bigscreen_once") as fake_capture, \
                patch("app.write_bigscreen_capture_bundle") as fake_bundle, \
                patch("app.threading.Thread", ImmediateThread):
            zip_file = app.config["BIGSCREEN_OUTPUT_DIR"] / "result.zip"
            zip_file.write_bytes(b"zip")
            fake_capture.return_value = FakeCaptureResult
            fake_bundle.return_value = (app.config["BIGSCREEN_OUTPUT_DIR"] / "manifest.xlsx", zip_file)

            response = client.post(
                "/api/bigscreen-capture/capture-now",
                json={"url": "https://jlive.jd.com/bigScreen?id=46794566"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        download_response = client.get(
            f"/api/bigscreen-capture/download/{payload['task_id']}"
        )
        self.assertEqual(download_response.status_code, 200)
        download_response.close()
        self.assertEqual(
            [event["action"] for event in reporter.events],
            ["task_start", "task_finish", "download"],
        )
        finish_event = reporter.events[1]
        self.assertEqual(finish_event["tool_code"], "bigscreen_capture")
        self.assertEqual(finish_event["task_id"], payload["task_id"])
        self.assertEqual(finish_event["status"], "success")
        self.assertEqual(finish_event["item_count"], 15)
        self.assertEqual(finish_event["success_count"], 15)
        self.assertEqual(finish_event["fail_count"], 0)
        self.assertEqual(finish_event["extra"]["room_id"], "46794566")
        self.assertEqual(finish_event["extra"]["room_name"], "京东青春采销")
        download_event = reporter.events[2]
        self.assertEqual(download_event["extra"]["room_id"], "46794566")
        self.assertEqual(download_event["extra"]["room_name"], "京东青春采销")

    def _business_workbook_bytes(self):
        wb = Workbook()
        ws = wb.active
        ws.append(
            [
                "skuID",
                "商品名称",
                "促销编码 专享券填专享券key码 专享价填ERP促销编码 （达人id：22766602）",
            ]
        )
        ws.append(["1001", "A 商品", "vender_BA#a9d94c41368e441094132b17a3b40fd6"])
        ws.append(["1002", "B 商品", "381421541016"])
        output = io.BytesIO()
        wb.save(output)
        wb.close()
        return output.getvalue()

    def _red_rain_workbook_bytes(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["活动名称", "开始时间", "结束时间", "红包发放方式", "红包ID", "中奖概率"])
        ws.append(["晚场红包雨", "2099-01-01 20:00:00", "2099-01-01 20:10:00", "普通发放", "123", 50])
        ws.append(["夜场红包雨", "2099-01-01 21:00:00", "2099-01-01 21:10:00", "普通发放", "pending", 50])
        output = io.BytesIO()
        wb.save(output)
        wb.close()
        return output.getvalue()


if __name__ == "__main__":
    unittest.main()
