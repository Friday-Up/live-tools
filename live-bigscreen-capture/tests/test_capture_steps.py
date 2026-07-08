import unittest

from bigscreen_capture.capture_manifest import CAPTURE_STEPS
from bigscreen_capture.capture_steps import run_capture_step


class FakeBigscreenBrowser:
    def __init__(self):
        self.calls = []

    def open_overview(self):
        self.calls.append(("open_overview",))

    def open_flow(self):
        self.calls.append(("open_flow",))

    def open_product(self):
        self.calls.append(("open_product",))

    def select_overview_live_tab(self, label):
        self.calls.append(("select_overview_live_tab", label))

    def select_overview_product_scope(self, label):
        self.calls.append(("select_overview_product_scope", label))

    def select_flow_metric(self, label):
        self.calls.append(("select_flow_metric", label))

    def select_user_portrait(self, label):
        self.calls.append(("select_user_portrait", label))

    def sort_product_table(self, label):
        self.calls.append(("sort_product_table", label))


class CaptureStepsTest(unittest.TestCase):
    def test_channel_flow_uses_overview_online_tab(self):
        browser = FakeBigscreenBrowser()

        run_capture_step(browser, CAPTURE_STEPS[1])

        self.assertEqual(browser.calls, [("open_overview",), ("select_overview_live_tab", "在线")])

    def test_channel_deal_uses_overview_deal_tab(self):
        browser = FakeBigscreenBrowser()

        run_capture_step(browser, CAPTURE_STEPS[2])

        self.assertEqual(browser.calls, [("open_overview",), ("select_overview_live_tab", "成交")])

    def test_bag_data_uses_overview_product_scope(self):
        browser = FakeBigscreenBrowser()

        run_capture_step(browser, CAPTURE_STEPS[3])

        self.assertEqual(browser.calls, [("open_overview",), ("select_overview_product_scope", "挂袋商品")])

    def test_order_top10_sorts_product_by_deal_count(self):
        browser = FakeBigscreenBrowser()

        run_capture_step(browser, CAPTURE_STEPS[13])

        self.assertEqual(browser.calls, [("open_product",), ("sort_product_table", "成交件数")])

    def test_gmv_top10_sorts_product_by_deal_amount(self):
        browser = FakeBigscreenBrowser()

        run_capture_step(browser, CAPTURE_STEPS[14])

        self.assertEqual(browser.calls, [("open_product",), ("sort_product_table", "成交金额")])


if __name__ == "__main__":
    unittest.main()
