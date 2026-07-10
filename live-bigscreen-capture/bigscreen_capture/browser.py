import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


PRICE_AUDIT_ROOT = Path(__file__).resolve().parents[2] / "live-sku-price-audit"
if str(PRICE_AUDIT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRICE_AUDIT_ROOT))

from utils.browser_manager import BrowserManager  # noqa: E402


class BigscreenBrowser:
    LOCATOR_TIMEOUT_MS = 15000

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
            page_zoom="80%",
        )
        self.page = self.browser_manager.start()
        return self

    def check_login_status(self):
        if self.browser_manager is None:
            return False
        if not self.browser_manager.check_login_status():
            return False
        try:
            self._goto_bigscreen()
            sidebar = self.page.locator('[class*="side-bar-index-name"]').filter(has_text="概览")
            self._wait_for_visible(sidebar, "未找到页面元素: 概览")
        except (PlaywrightError, RuntimeError):
            return False
        return True

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

    def get_room_name(self):
        self._goto_bigscreen()
        locator = self.page.locator('[class*="header-index-currentUserName"]')
        target = self._wait_for_visible(locator, "未找到直播间账号名称")
        return target.inner_text().strip()

    def select_overview_live_tab(self, label):
        self._click_text(label)
        self._wait_stable()

    def select_overview_product_scope(self, label):
        self._select_ant_dropdown("全部商品", label)
        self._wait_stable()

    def select_flow_metric(self, label):
        locator = self.page.locator('[class*="scroll-tab-index-scrollTabItem"]').filter(
            has_text=label
        )
        self._click_locator(locator, "未找到页面元素: %s" % label)
        self._wait_stable()

    def select_user_portrait(self, label):
        self._select_ant_dropdown("访问用户", label)
        self._wait_stable()

    def sort_product_table(self, label):
        header = self.page.locator("thead th").filter(has_text=label)
        header = self._wait_for_visible(header, "未找到商品分析表头: %s" % label)
        for _ in range(2):
            header.click(force=True)
            self._wait_stable()
            if self._is_desc_sort_active(header) or self._is_visible_column_desc_sorted(label):
                return
        self._log("未确认商品分析表头降序状态: %s，继续截图" % label)

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
        locator = self.page.locator('[class*="side-bar-index-name"]').filter(has_text=label)
        target = self._wait_for_visible(locator, "未找到页面元素: %s" % label)
        if not self._is_sidebar_selected(target):
            target.click(force=True)
        self._wait_stable()

    def _click_text(self, label):
        locator = self.page.get_by_text(label, exact=True)
        self._click_locator(locator, "未找到页面元素: %s" % label)

    def _click_locator(self, locator, error_message):
        self._wait_for_visible(locator, error_message).click(force=True)

    def _wait_for_visible(self, locator, error_message):
        target = locator.first
        try:
            target.wait_for(state="visible", timeout=self.LOCATOR_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            raise RuntimeError(error_message)
        return target

    @staticmethod
    def _is_sidebar_selected(locator):
        return bool(
            locator.evaluate(
                "el => Boolean(el.closest('[class*=\"side-bar-index-selected\"]'))"
            )
        )

    def _select_ant_dropdown(self, current_text, option_text):
        dropdown = self.page.locator(".ant-select-selection-item").filter(has_text=current_text)
        try:
            dropdown = self._wait_for_visible(dropdown, "未找到下拉框: %s" % current_text)
        except RuntimeError:
            dropdown = self.page.locator(".ant-select-selection-item").filter(has_text=option_text)
            dropdown = self._wait_for_visible(dropdown, "未找到下拉框: %s" % current_text)
        dropdown.click(force=True)
        self.page.wait_for_timeout(500)

        option = self.page.locator(".ant-select-item-option-content").filter(has_text=option_text)
        option = self._wait_for_visible(option, "未找到下拉选项: %s" % option_text)
        option.evaluate("el => el.click()")

    def _is_desc_sort_active(self, header):
        return bool(
            header.evaluate(
                """el => {
                    const attrValues = [
                        el.getAttribute('aria-sort'),
                        el.getAttribute('data-sort-order'),
                        el.dataset ? el.dataset.sortOrder : '',
                    ].filter(Boolean).map(value => String(value).toLowerCase());
                    if (attrValues.some(value => value.includes('desc'))) return true;

                    const down = el.querySelector('.ant-table-column-sorter-down');
                    if (!down) return false;
                    const className = [
                        down.className,
                        down.parentElement ? down.parentElement.className : '',
                        down.closest('[class*="sorter"]') ? down.closest('[class*="sorter"]').className : '',
                    ].map(value => String(value || '')).join(' ');
                    const ariaChecked = down.getAttribute('aria-checked');
                    const ariaSelected = down.getAttribute('aria-selected');
                    const title = String(down.getAttribute('title') || down.getAttribute('aria-label') || '').toLowerCase();
                    return className.includes('active')
                        || className.includes('ant-table-column-sorter-active')
                        || ariaChecked === 'true'
                        || ariaSelected === 'true'
                        || title.includes('desc');
                }"""
            )
        )

    def _is_visible_column_desc_sorted(self, label):
        return bool(
            self.page.evaluate(
                """label => {
                    const headers = Array.from(document.querySelectorAll('thead th'));
                    const header = headers.find(el => (el.innerText || '').includes(label));
                    if (!header || !header.parentElement) return false;
                    const columnIndex = Array.from(header.parentElement.children).indexOf(header);
                    if (columnIndex < 0) return false;

                    const values = Array.from(document.querySelectorAll('tbody tr'))
                        .slice(0, 20)
                        .map(row => row.children[columnIndex])
                        .filter(Boolean)
                        .map(cell => String(cell.innerText || ''))
                        .map(text => text.replace(/[^0-9.\\-]/g, ''))
                        .filter(text => /\\d/.test(text))
                        .map(Number)
                        .filter(value => Number.isFinite(value));

                    if (values.length < 2) return false;
                    return values.every((value, index) => index === 0 || values[index - 1] >= value);
                }""",
                label,
            )
        )

    def _wait_stable(self):
        self.page.wait_for_timeout(1500)
