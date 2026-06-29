import unittest

from promotion_binding.code_parser import IssueType, ParsedCode, parse_code_cell


class CodeParserTest(unittest.TestCase):
    def test_parses_exclusive_coupon_key(self):
        result = parse_code_cell("vender_BA#a9d94c41368e441094132b17a3b40fd6")

        self.assertEqual(
            result,
            ParsedCode(
                keys=["vender_BA#a9d94c41368e441094132b17a3b40fd6"],
                promo_ids=[],
                issues=[],
            ),
        )

    def test_parses_promo_id(self):
        result = parse_code_cell("381421541016")

        self.assertEqual(result.keys, [])
        self.assertEqual(result.promo_ids, ["381421541016"])
        self.assertEqual(result.issues, [])

    def test_ignores_numbers_inside_coupon_key(self):
        result = parse_code_cell("vender_BA#17314945377a4f1f9c0f1f24b79123a4")

        self.assertEqual(result.keys, ["vender_BA#17314945377a4f1f9c0f1f24b79123a4"])
        self.assertEqual(result.promo_ids, [])
        self.assertEqual(result.issues, [])

    def test_marks_business_words_as_invalid(self):
        result = parse_code_cell("百亿补贴")

        self.assertEqual(result.keys, [])
        self.assertEqual(result.promo_ids, [])
        self.assertEqual(result.issues, [IssueType.INVALID_CODE])

    def test_marks_multiple_keys_as_issue(self):
        result = parse_code_cell(
            "vender_BA#a825d4ab8f8f4ba6960aa20c142dabbb；"
            "vender_BA#65482cc4e1a24ce99acbe89014f3530f（后三个月）"
        )

        self.assertEqual(
            result.keys,
            [
                "vender_BA#a825d4ab8f8f4ba6960aa20c142dabbb",
                "vender_BA#65482cc4e1a24ce99acbe89014f3530f",
            ],
        )
        self.assertEqual(result.promo_ids, [])
        self.assertEqual(result.issues, [IssueType.MULTIPLE_KEYS])

    def test_marks_key_and_promo_conflict(self):
        result = parse_code_cell("vender_BA#a9d94c41368e441094132b17a3b40fd6 381421541016")

        self.assertEqual(result.keys, ["vender_BA#a9d94c41368e441094132b17a3b40fd6"])
        self.assertEqual(result.promo_ids, ["381421541016"])
        self.assertEqual(result.issues, [IssueType.KEY_PROMO_CONFLICT])


    def test_parses_ba_key(self):
        result = parse_code_cell("BA_9t7zua1")
        self.assertEqual(result.keys, ["BA_9t7zua1"])
        self.assertEqual(result.promo_ids, [])
        self.assertEqual(result.issues, [])

    def test_parses_ba_key_case_insensitive(self):
        result = parse_code_cell("ba_9T7ZUA1")
        self.assertEqual(result.keys, ["BA_9T7ZUA1"])
        self.assertEqual(result.promo_ids, [])
        self.assertEqual(result.issues, [])

    def test_marks_multiple_ba_keys_as_issue(self):
        result = parse_code_cell("BA_9t7zua1 BA_9bz63kn")
        self.assertEqual(result.keys, ["BA_9t7zua1", "BA_9bz63kn"])
        self.assertEqual(result.promo_ids, [])
        self.assertEqual(result.issues, [IssueType.MULTIPLE_KEYS])

    def test_marks_ba_key_and_promo_conflict(self):
        result = parse_code_cell("BA_9t7zua1 381421541016")
        self.assertEqual(result.keys, ["BA_9t7zua1"])
        self.assertEqual(result.promo_ids, ["381421541016"])
        self.assertEqual(result.issues, [IssueType.KEY_PROMO_CONFLICT])

    def test_parses_mixed_vender_and_ba_keys_as_multiple_keys(self):
        result = parse_code_cell(
            "vender_BA#a9d94c41368e441094132b17a3b40fd6 BA_9t7zua1"
        )
        self.assertEqual(
            result.keys,
            [
                "vender_BA#a9d94c41368e441094132b17a3b40fd6",
                "BA_9t7zua1",
            ],
        )
        self.assertEqual(result.promo_ids, [])
        self.assertEqual(result.issues, [IssueType.MULTIPLE_KEYS])

if __name__ == "__main__":
    unittest.main()
