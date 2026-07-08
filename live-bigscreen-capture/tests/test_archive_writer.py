import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from bigscreen_capture.archive_writer import write_manifest_workbook, write_zip_archive
from bigscreen_capture.models import CaptureRecord


class ArchiveWriterTest(unittest.TestCase):
    def test_writes_manifest_workbook_and_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            image_path = output_dir / "20260708_190000" / "蓝屏数据截图_46794566__20260708_190000_01_概览总览.png"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"png")
            records = [
                CaptureRecord(
                    planned_slot="19:00",
                    executed_at=datetime(2026, 7, 8, 19, 0, 1),
                    room_id="46794566",
                    step_code="01",
                    step_name="概览总览",
                    filename=image_path.name,
                    status="成功",
                    path=image_path,
                )
            ]

            manifest = write_manifest_workbook(output_dir, records)
            archive = write_zip_archive(
                output_dir,
                room_id="46794566",
                captured_at=datetime(2026, 7, 8, 19, 0, 0),
            )

            workbook = load_workbook(manifest)
            self.assertEqual(workbook.active["A1"].value, "计划整点")
            self.assertEqual(workbook.active["E2"].value, "概览总览")
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
            self.assertIn("截图清单.xlsx", names)
            self.assertIn("20260708_190000/" + image_path.name, names)


if __name__ == "__main__":
    unittest.main()
