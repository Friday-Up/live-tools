import unittest


class ProductSelectionPackageTest(unittest.TestCase):
    def test_core_modules_are_available_from_product_selection_package(self):
        from product_selection_agent import config, fetcher, parser, recommender, selector

        self.assertEqual(config.TOP_N_PER_CATEGORY, 10)
        self.assertTrue(callable(fetcher.fetch_all))
        self.assertTrue(callable(parser.parse_all))
        self.assertTrue(callable(recommender.recommend))
        self.assertTrue(callable(selector.build_candidate_pool))

    def test_cli_is_a_thin_wrapper_around_service(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

        self.assertIn("from product_selection_agent.service import", source)
        self.assertNotIn("def save_excel", source)
        self.assertNotIn("def _diagnostics", source)


if __name__ == "__main__":
    unittest.main()
