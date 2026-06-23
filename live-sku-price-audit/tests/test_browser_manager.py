import time
import unittest
from unittest.mock import patch

from utils.browser_manager import (
    DEFAULT_CONTEXT_OPTIONS,
    BrowserManager,
    should_block_request,
)


class FakeLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(self, cart_url, selector_counts=None):
        self.url = ""
        self.cart_url = cart_url
        self.visited = []
        self.selector_counts = selector_counts or {}
        self.title_text = "京东(JD.COM)"

    def goto(self, url, **kwargs):
        self.visited.append(url)
        self.url = self.cart_url if "cart.jd.com" in url else url

    def title(self):
        return self.title_text

    def locator(self, selector):
        if selector in self.selector_counts:
            return FakeLocator(self.selector_counts[selector])
        if selector == "text=退出":
            return FakeLocator(1)
        return FakeLocator(0)


class FakeContext:
    def __init__(self):
        self.created_pages = []
        self.routes = []
        self.init_scripts = []
        self.storage_state_calls = []
        self.closed = False

    def cookies(self):
        return [{"name": "pin", "expires": time.time() + 3600}]

    def new_page(self):
        page = object()
        self.created_pages.append(page)
        return page

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def storage_state(self, **kwargs):
        self.storage_state_calls.append(kwargs)

    def close(self):
        self.closed = True


class FakeRequest:
    def __init__(self, resource_type, url):
        self.resource_type = resource_type
        self.url = url


class FakeClosable:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def stop(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.contexts = []

    def new_context(self, **kwargs):
        context = FakeContext()
        context.options = kwargs
        self.contexts.append(context)
        return context


class FakeChromium:
    def __init__(self):
        self.launch_calls = []
        self.browser = FakeBrowser()

    def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        return self.browser


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()

    def start(self):
        return self


class BrowserManagerLoginTests(unittest.TestCase):
    def test_cart_redirect_to_passport_is_not_logged_in_even_if_homepage_has_logout_text_and_cookie(self):
        manager = BrowserManager()
        manager.page = FakePage("https://passport.jd.com/new/login.aspx")
        manager.context = FakeContext()

        self.assertFalse(manager.check_login_status(recheck_seconds=0, recheck_interval=0.001))

    def test_cart_page_accessible_is_logged_in(self):
        manager = BrowserManager()
        manager.page = FakePage("https://cart.jd.com/cart_index")
        manager.context = FakeContext()

        self.assertTrue(manager.check_login_status())

    def test_cart_page_with_login_prompt_is_not_logged_in(self):
        manager = BrowserManager()
        manager.page = FakePage(
            "https://cart.jd.com/cart_index",
            selector_counts={
                "text=登录后将显示您之前加入的商品": 1,
            },
        )
        manager.context = FakeContext()

        self.assertFalse(manager.check_login_status(recheck_seconds=0, recheck_interval=0.001))

    def test_cart_login_prompt_gets_rechecked_without_refreshing_page(self):
        class DelayedLoginPage(FakePage):
            def __init__(self):
                super().__init__("https://cart.jd.com/cart_index")
                self.prompt_checks = 0

            def locator(self, selector):
                if selector == "text=你好，请登录":
                    self.prompt_checks += 1
                    return FakeLocator(1 if self.prompt_checks == 1 else 0)
                return super().locator(selector)

        manager = BrowserManager()
        manager.page = DelayedLoginPage()
        manager.context = FakeContext()

        self.assertTrue(manager.check_login_status(recheck_seconds=0.01, recheck_interval=0.001))
        self.assertEqual(manager.page.visited, ["https://cart.jd.com/cart_index"])

    def test_new_page_uses_active_browser_context(self):
        manager = BrowserManager()
        context = FakeContext()
        manager.context = context

        page = manager.new_page()

        self.assertIs(page, context.created_pages[0])

    def test_fast_resource_blocking_blocks_heavy_nonessential_requests(self):
        self.assertTrue(should_block_request(FakeRequest("font", "https://static.jd.com/a.woff2")))
        self.assertTrue(should_block_request(FakeRequest("media", "https://static.jd.com/a.mp4")))
        self.assertTrue(should_block_request(FakeRequest("script", "https://wl.jd.com/joya.js")))
        self.assertFalse(should_block_request(FakeRequest("image", "https://img10.360buyimg.com/item/a.jpg")))
        self.assertFalse(should_block_request(FakeRequest("script", "https://item.jd.com/item.js")))

    def test_fast_resource_blocking_can_skip_images_for_scan_workers(self):
        self.assertTrue(
            should_block_request(
                FakeRequest("image", "https://img10.360buyimg.com/item/a.jpg"),
                block_images=True,
            )
        )
        self.assertFalse(
            should_block_request(
                FakeRequest("xhr", "https://item.jd.com/functionId=pc_detailpage_wareBusiness"),
                block_images=True,
            )
        )

    def test_enable_fast_resource_blocking_registers_context_route(self):
        manager = BrowserManager()
        context = FakeContext()
        manager.context = context

        manager.enable_fast_resource_blocking()

        self.assertEqual(context.routes[0][0], "**/*")

    def test_configure_page_display_installs_zoom_init_script(self):
        manager = BrowserManager()
        context = FakeContext()
        manager.context = context

        manager.configure_page_display()

        self.assertEqual(DEFAULT_CONTEXT_OPTIONS["viewport"]["width"], 1600)
        self.assertEqual(DEFAULT_CONTEXT_OPTIONS["viewport"]["height"], 1100)
        self.assertEqual(len(context.init_scripts), 1)
        self.assertIn("document.documentElement.style.zoom = '75%'", context.init_scripts[0])

    def test_start_passes_headless_flag_and_performance_args_to_chromium_launch(self):
        fake_playwright = FakePlaywright()

        with patch("utils.browser_manager.sync_playwright", return_value=fake_playwright), \
             patch("utils.browser_manager.os.path.exists", return_value=False):
            manager = BrowserManager(headless=True)
            manager.start()

        self.assertEqual(len(fake_playwright.chromium.launch_calls), 1)
        call = fake_playwright.chromium.launch_calls[0]
        self.assertTrue(call.get("headless"))
        self.assertIn("args", call)
        self.assertIn("--disable-background-timer-throttling", call["args"])

    def test_start_can_skip_fast_resource_blocking_for_login_browser(self):
        fake_playwright = FakePlaywright()

        with patch("utils.browser_manager.sync_playwright", return_value=fake_playwright), \
             patch("utils.browser_manager.os.path.exists", return_value=False):
            manager = BrowserManager(headless=False, block_resources=False)
            manager.start()

        context = fake_playwright.chromium.browser.contexts[0]
        self.assertEqual(context.routes, [])
        self.assertEqual(len(context.init_scripts), 1)

    def test_force_close_skips_storage_state_to_exit_quickly(self):
        manager = BrowserManager(auth_file="auth.json")
        context = FakeContext()
        page = FakeClosable()
        browser = FakeClosable()
        playwright = FakeClosable()
        manager.context = context
        manager.page = page
        manager.browser = browser
        manager.playwright = playwright

        manager.close(force=True)

        self.assertEqual(context.storage_state_calls, [])
        self.assertTrue(page.closed)
        self.assertTrue(context.closed)
        self.assertTrue(browser.closed)
        self.assertTrue(playwright.closed)


if __name__ == "__main__":
    unittest.main()
