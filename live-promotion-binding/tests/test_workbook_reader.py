import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from promotion_binding.workbook_reader import BusinessRow, ColumnMapping, inspect_business_workbook, read_business_rows


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

    def test_reads_rows_with_current_business_export_headers(self):
        path = self._create_workbook(
            [
                [
                    "意向上播日期",
                    "讲解/挂链 【必填】",
                    "事业部",
                    "一级类目",
                    "二级类目",
                    "三级类目",
                    "自营/pop",
                    "skuID",
                    "商品名称",
                    "前台价",
                    "到手价",
                    "库存情况",
                    "促销编码 专享券填专享券key码 专享价填ERP促销编码 （达人id：22766602）",
                    "手卡",
                ],
                ["2026-06-18", "讲解", "事业部A", "", "", "", "自营", 1001, "A 商品", "", "", "", 381421541016, ""],
            ]
        )

        rows = read_business_rows(path)

        self.assertEqual(
            rows,
            [BusinessRow(source_row=2, sku="1001", raw_code="381421541016", product_name="A 商品")],
        )

    def test_inspects_workbook_and_suggests_columns_from_business_keywords(self):
        path = self._create_workbook(
            [
                [
                    "意向上播日期",
                    "讲解/挂链 【必填】",
                    "事业部",
                    "一级类目",
                    "二级类目",
                    "三级类目",
                    "自营/pop",
                    "skuID",
                    "商品名称",
                    "前台价",
                    "到手价",
                    "库存情况",
                    "促销编码 专享券填专享券key码 专享价填ERP促销编码 （达人id：22766602）",
                    "手卡",
                ],
                ["2026-06-18", "讲解", "事业部A", "", "", "", "自营", 1001, "A 商品", "", "", "", 381421541016, ""],
                ["2026-06-19", "挂链", "事业部B", "", "", "", "pop", 1002, "B 商品", "", "", "", "vender_BA#a9d94c41368e441094132b17a3b40fd6", ""],
            ]
        )

        inspection = inspect_business_workbook(path)

        self.assertEqual(inspection.suggested_mapping.sku_col, 8)
        self.assertEqual(inspection.suggested_mapping.code_col, 13)
        self.assertEqual(inspection.suggested_mapping.product_name_col, 9)
        self.assertEqual(inspection.columns[7].header, "skuID")
        self.assertEqual(inspection.columns[7].sample_values, ["1001", "1002"])
        self.assertEqual(inspection.columns[12].sample_values[0], "381421541016")

    def test_reads_rows_with_explicit_column_mapping_when_headers_do_not_match_keywords(self):
        path = self._create_workbook(
            [
                ["排期", "商品编号", "标题", "权益内容"],
                ["2026-06-18", 1001, "A 商品", 381421541016],
                ["2026-06-19", "1002", "B 商品", "vender_BA#a9d94c41368e441094132b17a3b40fd6"],
            ]
        )

        rows = read_business_rows(path, ColumnMapping(sku_col=2, code_col=4, product_name_col=3))

        self.assertEqual(
            rows,
            [
                BusinessRow(source_row=2, sku="1001", raw_code="381421541016", product_name="A 商品"),
                BusinessRow(
                    source_row=3,
                    sku="1002",
                    raw_code="vender_BA#a9d94c41368e441094132b17a3b40fd6",
                    product_name="B 商品",
                ),
            ],
        )

    def test_raises_when_required_headers_are_missing(self):
        path = self._create_workbook([["SKU", "备注"], ["100", "x"]])

        with self.assertRaisesRegex(ValueError, "未找到"):
            read_business_rows(path)

    def test_inspects_and_reads_selling_point_column(self):
        path = self._create_workbook(
            [
                ["skuID", "商品名称", "券码", "短卖点（折扣、直降、卖点都可以）"],
                ["1001", "A 商品", "vender_BA#a9d94c41368e441094132b17a3b40fd6", "限时直降"],
                ["1002", "B 商品", "381421541016", "满减优惠"],
            ]
        )

        inspection = inspect_business_workbook(path)
        self.assertEqual(inspection.suggested_mapping.selling_point_col, 4)

        rows = read_business_rows(path)
        self.assertEqual(
            rows,
            [
                BusinessRow(
                    source_row=2,
                    sku="1001",
                    raw_code="vender_BA#a9d94c41368e441094132b17a3b40fd6",
                    product_name="A 商品",
                    selling_point="限时直降",
                ),
                BusinessRow(
                    source_row=3,
                    sku="1002",
                    raw_code="381421541016",
                    product_name="B 商品",
                    selling_point="满减优惠",
                ),
            ],
        )

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
