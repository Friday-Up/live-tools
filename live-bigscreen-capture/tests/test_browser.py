import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from bigscreen_capture.browser import BigscreenBrowser


class FakeLocator:
    def __init__(self, page, label, count=1):
        self.page = page
        self.label = label
        self._count = count
        self.has_text = None

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def click(self, **kwargs):
        self.page.actions.append(("click", self.label, self.has_text))
        self.page.clicks.append((self.label, kwargs))

    def filter(self, **kwargs):
        self.has_text = kwargs.get("has_text")
        self.page.filters.append((self.label, kwargs))
        return self

    def evaluate(self, script):
        self.page.evaluations.append((self.label, script))
        if script == "el => el.click()":
            self.page.actions.append(("dom_click", self.label, self.has_text))
            self.page.dom_clicks.append((self.label, self.has_text))
            return None
        if "side-bar-index-selected" in script:
            return self.has_text in self.page.selected_labels
        if self.page.evaluation_results:
            return self.page.evaluation_results.pop(0)
        return None

    def wait_for(self, **kwargs):
        key = (self.label, self.has_text)
        self.page.actions.append(("wait_for", self.label, self.has_text))
        self.page.locator_waits.append((self.label, self.has_text, kwargs))
        if key in self.page.wait_failures:
            raise PlaywrightTimeoutError("locator did not become visible")

    def inner_text(self):
        return self.page.locator_texts.get(self.label, "")


class FakePage:
    def __init__(self):
        self.url = ""
        self.goto_calls = []
        self.clicks = []
        self.filters = []
        self.evaluations = []
        self.actions = []
        self.dom_clicks = []
        self.locator_waits = []
        self.wait_failures = set()
        self.selected_labels = set()
        self.waits = []
        self.screenshots = []
        self.evaluation_results = []
        self.page_evaluations = []
        self.page_evaluation_results = []
        self.locator_texts = {}

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


class FakeLoggedInBrowserManager:
    def __init__(self, page):
        self.page = page

    def check_login_status(self):
        return True


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
        self.assertEqual(
            page.dom_clicks,
            [('[class*="side-bar-index-name"]', "流量")],
        )
        self.assertEqual(page.clicks, [])
        self.assertIn(
            ('[class*="side-bar-index-name"]', {"has_text": "流量"}),
            page.filters,
        )

    def test_open_flow_waits_for_sidebar_visibility_before_clicking(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.open_flow()

        wait_action = ('wait_for', '[class*="side-bar-index-name"]', "流量")
        click_action = ('dom_click', '[class*="side-bar-index-name"]', "流量")
        self.assertIn(wait_action, page.actions)
        self.assertIn(click_action, page.actions)
        self.assertLess(
            page.actions.index(wait_action),
            page.actions.index(click_action),
        )

    def test_select_flow_metric_waits_for_scoped_metric_before_clicking(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.select_flow_metric("在线人数")

        selector = '[class*="scroll-tab-index-scrollTabItem"]'
        wait_action = ("wait_for", selector, "在线人数")
        click_action = ("dom_click", selector, "在线人数")
        self.assertIn(wait_action, page.actions)
        self.assertIn(click_action, page.actions)
        self.assertLess(
            page.actions.index(wait_action),
            page.actions.index(click_action),
        )

    def test_select_overview_live_tab_uses_dom_click(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.select_overview_live_tab("成交")

        self.assertEqual(page.dom_clicks, [("成交", None)])
        self.assertEqual(page.clicks, [])

    def test_selected_sidebar_is_not_clicked_again(self):
        page = FakePage()
        page.url = "https://jlive.jd.com/bigScreen?id=46794566"
        page.selected_labels.add("概览")
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.open_overview()

        self.assertEqual(page.clicks, [])
        self.assertEqual(page.dom_clicks, [])

    def test_check_login_status_is_false_when_bigscreen_never_becomes_ready(self):
        page = FakePage()
        sidebar_selector = '[class*="side-bar-index-name"]'
        page.wait_failures.add((sidebar_selector, "概览"))
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page
        browser.browser_manager = FakeLoggedInBrowserManager(page)

        self.assertFalse(browser.check_login_status())
        self.assertEqual(page.goto_calls[-1][0], browser.url)
        self.assertIn(
            (sidebar_selector, "概览", {"state": "visible", "timeout": 15000}),
            page.locator_waits,
        )

    def test_check_login_status_is_false_when_bigscreen_navigation_fails(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page
        browser.browser_manager = FakeLoggedInBrowserManager(page)

        with patch.object(page, "goto", side_effect=PlaywrightError("net::ERR_ABORTED")):
            try:
                result = browser.check_login_status()
            except PlaywrightError as exc:
                self.fail("check_login_status leaked Playwright Error: %s" % exc)

        self.assertFalse(result)

    def test_get_room_name_waits_for_account_node_and_returns_visible_text(self):
        page = FakePage()
        selector = '[class*="header-index-currentUserName"]'
        page.locator_texts[selector] = " 京东青春采销 "
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        room_name = browser.get_room_name()

        self.assertEqual(room_name, "京东青春采销")
        self.assertEqual(page.goto_calls[-1][0], browser.url)
        self.assertIn(
            (selector, None, {"state": "visible", "timeout": 15000}),
            page.locator_waits,
        )

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

        self.assertEqual(page.clicks, [])
        self.assertEqual(
            page.filters,
            [
                (".ant-select-selection-item", {"has_text": "全部商品"}),
                (".ant-select-item-option-content", {"has_text": "挂袋商品"}),
            ],
        )
        self.assertEqual(
            page.dom_clicks,
            [
                (".ant-select-selection-item", "全部商品"),
                (".ant-select-item-option-content", "挂袋商品"),
            ],
        )
        self.assertIn(
            (".ant-select-selection-item", "全部商品", {"state": "visible", "timeout": 15000}),
            page.locator_waits,
        )
        self.assertIn(
            (".ant-select-item-option-content", "挂袋商品", {"state": "visible", "timeout": 15000}),
            page.locator_waits,
        )

    def test_select_user_portrait_uses_user_portrait_dropdown(self):
        page = FakePage()
        browser = BigscreenBrowser(
            "https://jlive.jd.com/bigScreen?id=46794566",
            auth_file="jd_auth.json",
        )
        browser.page = page

        browser.select_user_portrait("成交用户")

        self.assertEqual(page.clicks, [])
        self.assertEqual(
            page.filters,
            [
                (".ant-select-selection-item", {"has_text": "访问用户"}),
                (".ant-select-item-option-content", {"has_text": "成交用户"}),
            ],
        )
        self.assertEqual(
            page.dom_clicks,
            [
                (".ant-select-selection-item", "访问用户"),
                (".ant-select-item-option-content", "成交用户"),
            ],
        )

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

        self.assertEqual(page.clicks, [])
        self.assertEqual(page.dom_clicks, [("thead th", "成交件数")])
        self.assertEqual(page.filters, [("thead th", {"has_text": "成交件数"})])
        self.assertIn(
            ("thead th", "成交件数", {"state": "visible", "timeout": 15000}),
            page.locator_waits,
        )

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
            page.dom_clicks,
            [
                ("thead th", "成交金额"),
                ("thead th", "成交金额"),
            ],
        )
        self.assertEqual(page.clicks, [])

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

        self.assertEqual(page.clicks, [])
        self.assertEqual(page.dom_clicks, [("thead th", "成交件数")])
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
            page.dom_clicks,
            [
                ("thead th", "成交件数"),
                ("thead th", "成交件数"),
            ],
        )
        self.assertEqual(page.clicks, [])
        self.assertEqual(logs, ["未确认商品分析表头降序状态: 成交件数，继续截图"])


if __name__ == "__main__":
    unittest.main()
