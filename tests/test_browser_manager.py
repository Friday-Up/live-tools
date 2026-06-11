import time
import unittest

from utils.browser_manager import BrowserManager


class FakeLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(self, cart_url):
        self.url = ""
        self.cart_url = cart_url
        self.visited = []

    def goto(self, url, **kwargs):
        self.visited.append(url)
        self.url = self.cart_url if "cart.jd.com" in url else url

    def title(self):
        return "京东(JD.COM)"

    def locator(self, selector):
        if selector == "text=退出":
            return FakeLocator(1)
        return FakeLocator(0)


class FakeContext:
    def cookies(self):
        return [{"name": "pin", "expires": time.time() + 3600}]


class BrowserManagerLoginTests(unittest.TestCase):
    def test_cart_redirect_to_passport_is_not_logged_in_even_if_homepage_has_logout_text_and_cookie(self):
        manager = BrowserManager()
        manager.page = FakePage("https://passport.jd.com/new/login.aspx")
        manager.context = FakeContext()

        self.assertFalse(manager.check_login_status())

    def test_cart_page_accessible_is_logged_in(self):
        manager = BrowserManager()
        manager.page = FakePage("https://cart.jd.com/cart_index")
        manager.context = FakeContext()

        self.assertTrue(manager.check_login_status())


if __name__ == "__main__":
    unittest.main()
