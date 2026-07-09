import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bigscreen_capture.browser import BigscreenBrowser


class FakeLocator:
    def __init__(self, page, label, count=1):
        self.page = page
        self.label = label
        self._count = count

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def click(self, **kwargs):
        self.page.clicks.append((self.label, kwargs))

    def filter(self, **kwargs):
        self.page.filters.append((self.label, kwargs))
        return self

    def evaluate(self, script):
        self.page.evaluations.append((self.label, script))
        if self.page.evaluation_results:
            return self.page.evaluation_results.pop(0)
        return None


class FakePage:
    def __init__(self):
        self.url = ""
        self.goto_calls = []
        self.clicks = []
        self.filters = []
        self.evaluations = []
        self.waits = []
        self.screenshots = []
        self.evaluation_results = []
        self.page_evaluations = []
        self.page_evaluation_results = []

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = url

    def get_by_text(self, label, exact=True):
        return FakeLocator(self, label)

    def locator(self, selector):
        return FakeLocator(self, selector)

    def wait_for_timeout(self, timeout):
        self.waits.append(timeout)

    def screenshot(self, **kwargs):
        self.screenshots.append(kwargs)

    def evaluate(self, script, arg=None):
        self.page_evaluations.append((script, arg))
        if self.page_evaluation_results:
            return self.page_evaluation_results.pop(0)
        return False


class FakeBrowserManager:
    instances = []

    def __init__(self, auth_file, **kwargs):
        self.auth_file = auth_file
        self.kwargs = kwargs
        self.page = FakePage()
        FakeBrowserManager.instances.append(self)

    def start(self):
        return self.page


class BigscreenBrowserTest(unittest.TestCase):
    def test_open_flow_navigates_to_bigscreen_and_clicks_flow_sidebar(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.open_flow()

        self.assertEqual(page.goto_calls[0][0], "https://jlive.jd.com/bigScreen?id=46794566")
        self.assertEqual(page.clicks[-1][0], "流量")

    def test_start_uses_80_percent_zoom_for_bigscreen_capture(self):
        FakeBrowserManager.instances = []
        with patch("bigscreen_capture.browser.BrowserManager", FakeBrowserManager):
            browser = BigscreenBrowser(
                "https://jlive.jd.com/bigScreen?id=46794566",
                auth_file="jd_auth.json",
            )
            browser.start()

        self.assertEqual(FakeBrowserManager.instances[0].kwargs["page_zoom"], "80%")

    def test_start_does_not_open_bigscreen_before_login_check(self):
        FakeBrowserManager.instances = []
        with patch("bigscreen_capture.browser.BrowserManager", FakeBrowserManager):
            browser = BigscreenBrowser(
                "https://jlive.jd.com/bigScreen?id=46794566",
                auth_file="jd_auth.json",
            )
            browser.start()

        page = FakeBrowserManager.instances[0].page
        self.assertEqual(page.goto_calls, [])
        self.assertEqual(page.clicks, [])

    def test_select_overview_product_scope_uses_top_product_dropdown(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.select_overview_product_scope("挂袋商品")

        self.assertEqual(page.clicks, [(".ant-select-selection-item", {"force": True})])
        self.assertEqual(
            page.filters,
            [
                (".ant-select-selection-item", {"has_text": "全部商品"}),
                (".ant-select-item-option-content", {"has_text": "挂袋商品"}),
            ],
        )
        self.assertEqual(page.evaluations, [(".ant-select-item-option-content", "el => el.click()")])

    def test_select_user_portrait_uses_user_portrait_dropdown(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.select_user_portrait("成交用户")

        self.assertEqual(page.clicks, [(".ant-select-selection-item", {"force": True})])
        self.assertEqual(
            page.filters,
            [
                (".ant-select-selection-item", {"has_text": "访问用户"}),
                (".ant-select-item-option-content", {"has_text": "成交用户"}),
            ],
        )
        self.assertEqual(page.evaluations, [(".ant-select-item-option-content", "el => el.click()")])

    def test_screenshot_uses_visible_viewport_not_full_page(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "screen.png"

            browser.screenshot(path)

            self.assertEqual(page.screenshots, [{"path": str(path), "full_page": False}])
            self.assertTrue(path.parent.exists())

    def test_sort_product_table_clicks_table_header(self):
        page = FakePage()
        page.evaluation_results = [True]
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.sort_product_table("成交件数")

        self.assertEqual(page.clicks, [("thead th", {"force": True})])
        self.assertEqual(page.filters, [("thead th", {"has_text": "成交件数"})])

    def test_sort_product_table_clicks_again_until_descending_is_active(self):
        page = FakePage()
        page.evaluation_results = [False, True]
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.sort_product_table("成交金额")

        self.assertEqual(
            page.clicks,
            [
                ("thead th", {"force": True}),
                ("thead th", {"force": True}),
            ],
        )

    def test_sort_product_table_stops_after_one_click_when_visible_values_are_descending(self):
        page = FakePage()
        page.evaluation_results = [False]
        page.page_evaluation_results = [True]
        logs = []
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
            log_callback=logs.append,
        )
        browser.page = page

        browser.sort_product_table("成交件数")

        self.assertEqual(page.clicks, [("thead th", {"force": True})])
        self.assertEqual(page.page_evaluations[0][1], "成交件数")
        self.assertEqual(logs, [])

    def test_sort_product_table_continues_when_descending_state_is_not_detectable(self):
        page = FakePage()
        page.evaluation_results = [False, False]
        logs = []
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
            log_callback=logs.append,
        )
        browser.page = page

        browser.sort_product_table("成交件数")

        self.assertEqual(
            page.clicks,
            [
                ("thead th", {"force": True}),
                ("thead th", {"force": True}),
            ],
        )
        self.assertEqual(logs, ["未确认商品分析表头降序状态: 成交件数，继续截图"])


if __name__ == "__main__":
    unittest.main()
