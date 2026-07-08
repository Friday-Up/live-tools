import sys
from pathlib import Path


PRICE_AUDIT_ROOT = Path(__file__).resolve().parents[2] / "live-sku-price-audit"
if str(PRICE_AUDIT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRICE_AUDIT_ROOT))

from utils.browser_manager import BrowserManager  # noqa: E402


class BigscreenBrowser:
    def __init__(self, url, auth_file, headless=False, log_callback=None):
        self.url = url
        self.auth_file = Path(auth_file)
        self.headless = headless
        self._log = log_callback or (lambda _: None)
        self.browser_manager = None
        self.page = None

    def start(self):
        self.browser_manager = BrowserManager(
            str(self.auth_file),
            headless=self.headless,
            block_resources=False,
        )
        self.page = self.browser_manager.start()
        self.open_overview()
        return self

    def check_login_status(self):
        if self.browser_manager is None:
            return False
        return self.browser_manager.check_login_status()

    def open_login_page(self):
        if self.browser_manager is None:
            raise RuntimeError("浏览器未启动")
        self.browser_manager.open_login_page()

    def save_auth_state(self):
        if self.browser_manager is not None:
            self.browser_manager.save_auth_state()

    def close(self, force=False):
        if self.browser_manager is not None:
            self.browser_manager.close(force=force)

    def open_overview(self):
        self._goto_bigscreen()
        self._click_sidebar("概览")

    def open_flow(self):
        self._goto_bigscreen()
        self._click_sidebar("流量")

    def open_product(self):
        self._goto_bigscreen()
        self._click_sidebar("商品")

    def select_overview_live_tab(self, label):
        self._click_text(label)
        self._wait_stable()

    def select_overview_product_scope(self, label):
        self._click_text("全部商品")
        self._click_text(label)
        self._wait_stable()

    def select_flow_metric(self, label):
        self._click_text(label)
        self._wait_stable()

    def select_user_portrait(self, label):
        self._click_text("访问用户")
        self._click_text(label)
        self._wait_stable()

    def sort_product_table(self, label):
        self._click_text(label)
        self._wait_stable()

    def screenshot(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=False)

    def _goto_bigscreen(self):
        if self.page is None:
            raise RuntimeError("浏览器未启动")
        if "jlive.jd.com/bigScreen" not in (self.page.url or ""):
            self.page.goto(self.url, wait_until="networkidle", timeout=60000)
        self._wait_stable()

    def _click_sidebar(self, label):
        self._click_text(label)
        self._wait_stable()

    def _click_text(self, label):
        locator = self.page.get_by_text(label, exact=True)
        if locator.count() < 1:
            raise RuntimeError("未找到页面元素: %s" % label)
        locator.first.click(force=True)

    def _wait_stable(self):
        self.page.wait_for_timeout(1500)
