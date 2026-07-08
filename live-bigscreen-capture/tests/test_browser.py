import tempfile
import unittest
from pathlib import Path

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


class FakePage:
    def __init__(self):
        self.url = ""
        self.goto_calls = []
        self.clicks = []
        self.filters = []
        self.evaluations = []
        self.waits = []
        self.screenshots = []

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
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.sort_product_table("成交件数")

        self.assertEqual(page.clicks, [("thead th", {"force": True})])
        self.assertEqual(page.filters, [("thead th", {"has_text": "成交件数"})])


if __name__ == "__main__":
    unittest.main()
