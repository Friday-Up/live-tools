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


class FakePage:
    def __init__(self):
        self.url = ""
        self.goto_calls = []
        self.clicks = []
        self.waits = []
        self.screenshots = []

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = url

    def get_by_text(self, label, exact=True):
        return FakeLocator(self, label)

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

    def test_select_overview_product_scope_clicks_all_products_then_bag_products(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.select_overview_product_scope("挂袋商品")

        self.assertEqual([call[0] for call in page.clicks], ["全部商品", "挂袋商品"])

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


if __name__ == "__main__":
    unittest.main()
