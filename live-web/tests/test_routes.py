import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import unquote

from openpyxl import Workbook

from app import create_app, resolve_live_dir, resolve_web_root


class PromotionBindingRoutesTest(unittest.TestCase):
    def test_resolves_source_and_packaged_runtime_paths(self):
        source_app = Path("/repo/live/live-web/app.py")
        packaged_exe = Path("C:/tools/Live-Tools-Web/Live-Tools-Web.exe")

        self.assertEqual(resolve_live_dir(file_path=source_app, frozen=False), Path("/repo/live"))
        self.assertEqual(resolve_live_dir(executable_path=packaged_exe, frozen=True), Path("C:/tools/Live-Tools-Web"))

        source_root = Path(tempfile.mkdtemp())
        web_root = source_root / "live-web"
        web_root.mkdir()
        self.assertEqual(resolve_web_root(source_root, source_app), web_root)

    def test_generate_promotion_binding_files(self):
        base_dir = Path(tempfile.mkdtemp())
        app = create_app(base_dir=base_dir)
        client = app.test_client()
        old_runtime_file = base_dir / "runtime" / "output" / "promotion-binding" / "old" / "old.xlsx"
        old_runtime_file.parent.mkdir(parents=True, exist_ok=True)
        old_runtime_file.write_bytes(b"old")
        old_time = time.time() - 8 * 24 * 60 * 60
        os.utime(old_runtime_file, (old_time, old_time))

        data = {
            "file": (
                io.BytesIO(self._business_workbook_bytes()),
                "业务提报.xlsx",
            )
        }

        response = client.post(
            "/api/promotion-binding/generate",
            data=data,
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["summary"]["success_count"], 2)
        self.assertIn("template_download_url", payload)
        self.assertIn("report_download_url", payload)

        template_response = client.get(payload["template_download_url"])
        report_response = client.get(payload["report_download_url"])

        self.assertEqual(template_response.status_code, 200)
        self.assertEqual(report_response.status_code, 200)
        template_disposition = unquote(template_response.headers["Content-Disposition"])
        report_disposition = unquote(report_response.headers["Content-Disposition"])
        self.assertIn("京东绑券上传模板_", template_disposition)
        self.assertIn("异常报告_", report_disposition)
        self.assertNotIn(payload["task_id"], template_disposition)
        self.assertNotIn(payload["task_id"], report_disposition)
        self.assertFalse(old_runtime_file.exists())
        self.assertTrue(str(app.config["PROMOTION_INPUT_DIR"]).startswith(str(base_dir / "runtime")))
        self.assertTrue(str(app.config["PROMOTION_OUTPUT_DIR"]).startswith(str(base_dir / "runtime")))
        self.assertTrue(app.config["PROMOTION_RESULTS"][payload["task_id"]]["template"].name.startswith("京东绑券上传模板_"))
        self.assertTrue(app.config["PROMOTION_RESULTS"][payload["task_id"]]["report"].name.startswith("异常报告_"))
        self.assertGreater(len(template_response.data), 1000)
        self.assertGreater(len(report_response.data), 1000)
        template_response.close()
        report_response.close()

    def test_preview_promotion_binding_columns(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        client = app.test_client()

        response = client.post(
            "/api/promotion-binding/preview",
            data={"file": (io.BytesIO(self._business_workbook_bytes()), "业务提报.xlsx")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["task_id"])
        self.assertEqual(payload["suggested_mapping"]["sku_col"], 1)
        self.assertEqual(payload["suggested_mapping"]["product_name_col"], 2)
        self.assertEqual(payload["suggested_mapping"]["code_col"], 3)
        self.assertEqual(payload["columns"][0]["header"], "skuID")
        self.assertEqual(payload["columns"][0]["sample_values"], ["1001", "1002"])
        self.assertTrue(Path(payload["path"]).exists())

    def test_generate_promotion_binding_files_with_selected_columns(self):
        base_dir = Path(tempfile.mkdtemp())
        app = create_app(base_dir=base_dir)
        client = app.test_client()

        preview_response = client.post(
            "/api/promotion-binding/preview",
            data={"file": (io.BytesIO(self._manual_mapping_workbook_bytes()), "业务提报.xlsx")},
            content_type="multipart/form-data",
        )
        preview_payload = preview_response.get_json()
        self.assertTrue(preview_payload["success"])
        self.assertIsNone(preview_payload["suggested_mapping"]["sku_col"])
        self.assertIsNone(preview_payload["suggested_mapping"]["code_col"])

        response = client.post(
            "/api/promotion-binding/generate",
            json={
                "task_id": preview_payload["task_id"],
                "column_mapping": {
                    "sku_col": 2,
                    "code_col": 4,
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["summary"]["success_count"], 2)
        self.assertIn(payload["task_id"], app.config["PROMOTION_RESULTS"])

    def test_create_app_cleans_old_runtime_and_legacy_files(self):
        base_dir = Path(tempfile.mkdtemp())
        old_runtime_file = base_dir / "runtime" / "input" / "promotion-binding" / "old.xlsx"
        fresh_runtime_file = base_dir / "runtime" / "input" / "promotion-binding" / "fresh.xlsx"
        old_legacy_file = base_dir / "input" / "promotion-binding" / "legacy.xlsx"
        for file_path in [old_runtime_file, fresh_runtime_file, old_legacy_file]:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"x")

        now = time.time()
        old_time = now - 8 * 24 * 60 * 60
        fresh_time = now - 24 * 60 * 60
        os.utime(old_runtime_file, (old_time, old_time))
        os.utime(old_legacy_file, (old_time, old_time))
        os.utime(fresh_runtime_file, (fresh_time, fresh_time))

        app = create_app(base_dir=base_dir)

        self.assertEqual(app.config["RUNTIME_RETENTION_DAYS"], 7)
        self.assertFalse(old_runtime_file.exists())
        self.assertFalse(old_legacy_file.exists())
        self.assertTrue(fresh_runtime_file.exists())
        self.assertEqual(app.config["PRICE_INPUT_DIR"], base_dir / "runtime" / "input" / "price-audit")

    def test_rejects_non_xlsx_upload(self):
        app = create_app(base_dir=Path(tempfile.mkdtemp()))
        client = app.test_client()

        response = client.post(
            "/api/promotion-binding/generate",
            data={"file": (io.BytesIO(b"not excel"), "bad.txt")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    def test_price_audit_upload_and_start_validation_are_available(self):
        base_dir = Path(tempfile.mkdtemp())
        app = create_app(base_dir=base_dir)
        client = app.test_client()

        upload_response = client.post(
            "/api/upload",
            data={"file": (io.BytesIO(self._price_workbook_bytes()), "测价.xlsx")},
            content_type="multipart/form-data",
        )

        self.assertEqual(upload_response.status_code, 200)
        upload_payload = upload_response.get_json()
        self.assertTrue(upload_payload["success"])
        self.assertTrue(Path(upload_payload["path"]).exists())

        invalid_threshold_response = client.post(
            "/api/start",
            json={"file": upload_payload["path"], "threshold": "abc"},
        )
        self.assertEqual(invalid_threshold_response.status_code, 400)
        self.assertIn("价格门槛", invalid_threshold_response.get_json()["error"])

        status_response = client.get("/api/status")
        self.assertEqual(status_response.status_code, 200)
        self.assertIn("running", status_response.get_json())

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
        return output.getvalue()

    def _manual_mapping_workbook_bytes(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["排期", "商品编号", "标题", "权益内容"])
        ws.append(["2026-06-18", "1001", "A 商品", "vender_BA#a9d94c41368e441094132b17a3b40fd6"])
        ws.append(["2026-06-19", "1002", "B 商品", "381421541016"])
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    def _price_workbook_bytes(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["商品SKU"])
        ws.append(["100264886683"])
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()


if __name__ == "__main__":
    unittest.main()
