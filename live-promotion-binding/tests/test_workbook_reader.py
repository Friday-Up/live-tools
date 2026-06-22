import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from promotion_binding.workbook_reader import BusinessRow, read_business_rows


class WorkbookReaderTest(unittest.TestCase):
    def test_reads_rows_with_normalized_headers_and_original_row_numbers(self):
        path = self._create_workbook(
            [
                [
                    "ui",
                    "商品名称*【必填】",
                    "上播·SKU\xa0ID*\n【必填】",
                    "券码/价码\n达人id：22766602",
                ],
                ["讲解", "A 商品", 10079660739051, "vender_BA#a9d94c41368e441094132b17a3b40fd6"],
                ["挂链", "B 商品", "100089021178", 381421541016],
                ["无SKU", "C 商品", None, "381421541016"],
            ]
        )

        rows = read_business_rows(path)

        self.assertEqual(
            rows,
            [
                BusinessRow(
                    source_row=2,
                    sku="10079660739051",
                    raw_code="vender_BA#a9d94c41368e441094132b17a3b40fd6",
                    product_name="A 商品",
                ),
                BusinessRow(source_row=3, sku="100089021178", raw_code="381421541016", product_name="B 商品"),
            ],
        )

    def test_raises_when_required_headers_are_missing(self):
        path = self._create_workbook([["SKU", "备注"], ["100", "x"]])

        with self.assertRaisesRegex(ValueError, "未找到"):
            read_business_rows(path)

    def _create_workbook(self, rows):
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        path = Path(tmp.name)

        wb = Workbook()
        ws = wb.active
        for row in rows:
            ws.append(row)
        wb.save(path)
        return path


if __name__ == "__main__":
    unittest.main()
