import re
import sys
from pathlib import Path
from time import monotonic

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


PRICE_AUDIT_ROOT = Path(__file__).resolve().parents[2] / "live-sku-price-audit"
if str(PRICE_AUDIT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRICE_AUDIT_ROOT))

from utils.browser_manager import BrowserManager  # noqa: E402


class BigscreenBrowser:
    LOCATOR_TIMEOUT_MS = 15000
    ACTION_VERIFY_TIMEOUT_MS = 3000
    ACTION_VERIFY_INTERVAL_MS = 200

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
        locator = self.page.get_by_text(label, exact=True)
        target = self._wait_for_visible(locator, "未找到页面元素: %s" % label)
        self._dom_click_and_verify(
            target,
            lambda: self._is_control_selected(target),
            "标签未切换为: %s" % label,
        )
        self._wait_stable()

    def select_overview_product_scope(self, label):
        self._select_ant_dropdown("全部商品", label)
        self._wait_stable()

    def select_flow_metric(self, label):
        locator = self.page.locator('[class*="scroll-tab-index-scrollTabItem"]').filter(
            has_text=label
        )
        target = self._wait_for_visible(locator, "未找到页面元素: %s" % label)
        self._dom_click_and_verify(
            target,
            lambda: self._is_control_selected(target),
            "指标未切换为: %s" % label,
        )
        self._wait_stable()

    def select_user_portrait(self, label):
        self._select_ant_dropdown("访问用户", label)
        self._wait_stable()

    def sort_product_table(self, label):
        header = self.page.locator("thead th").filter(has_text=label)
        header = self._wait_for_visible(header, "未找到商品分析表头: %s" % label)
        caret = header.locator('[aria-label="caret-down"]')
        caret = self._wait_for_visible(caret, "未找到商品分析排序箭头: %s" % label)
        for _ in range(2):
            self._dom_click(caret)
            self._wait_stable()
            if self._is_visible_column_desc_sorted(label):
                return
        raise RuntimeError("商品分析表未按降序排列: %s" % label)

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
            self._dom_click_and_verify(
                target,
                lambda: self._is_sidebar_selected(target),
                "页面未切换到: %s" % label,
            )
        self._wait_stable()

    def _click_text(self, label):
        locator = self.page.get_by_text(label, exact=True)
        self._click_locator(locator, "未找到页面元素: %s" % label)

    def _click_locator(self, locator, error_message):
        self._dom_click(self._wait_for_visible(locator, error_message))

    @staticmethod
    def _dom_click(locator):
        locator.evaluate("el => el.click()")

    @staticmethod
    def _dom_mousedown(locator):
        locator.dispatch_event("mousedown")

    def _dom_click_and_verify(self, locator, is_selected, error_message):
        if self._condition_is_met(is_selected):
            return
        for _ in range(2):
            self._dom_click(locator)
            if self._wait_for_condition(is_selected):
                return
        raise RuntimeError(error_message)

    @staticmethod
    def _condition_is_met(predicate):
        try:
            return bool(predicate())
        except PlaywrightError:
            return False

    def _wait_for_condition(self, predicate):
        deadline = monotonic() + self.ACTION_VERIFY_TIMEOUT_MS / 1000
        while True:
            try:
                if predicate():
                    return True
            except PlaywrightError:
                pass
            if monotonic() >= deadline:
                return False
            self.page.wait_for_timeout(self.ACTION_VERIFY_INTERVAL_MS)

    def _wait_for_visible(self, locator, error_message, timeout=None):
        target = locator.first
        try:
            target.wait_for(
                state="visible",
                timeout=self.LOCATOR_TIMEOUT_MS if timeout is None else timeout,
            )
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

    @staticmethod
    def _is_control_selected(locator):
        return bool(
            locator.evaluate(
                """el => {
                    // BIGSCREEN_CONTROL_SELECTED
                    const candidates = [
                        el,
                        el.closest('label'),
                        el.closest('[role="radio"]'),
                    ].filter(Boolean);
                    return candidates.some(node => {
                        const input = node.matches('input') ? node : node.querySelector('input');
                        const className = String(node.className || '').toLowerCase();
                        return Boolean(input && input.checked)
                            || node.getAttribute('aria-checked') === 'true'
                            || node.getAttribute('aria-selected') === 'true'
                            || className.includes('checked')
                            || className.includes('selected')
                            || className.includes('active');
                    });
                }"""
            )
        )

    def _select_ant_dropdown(self, current_text, option_text):
        selected = self.page.locator(".ant-select-selection-item").filter(
            has_text=option_text
        )
        if selected.count() > 0:
            return

        dropdown = self.page.locator(".ant-select-selector").filter(has_text=current_text)
        try:
            dropdown = self._wait_for_visible(dropdown, "未找到下拉框: %s" % current_text)
        except RuntimeError:
            dropdown = self.page.locator(".ant-select-selector").filter(has_text=option_text)
            dropdown = self._wait_for_visible(
                dropdown,
                "未找到下拉框: %s" % current_text,
                timeout=self.ACTION_VERIFY_TIMEOUT_MS,
            )

        option = self.page.locator(".ant-select-item-option").filter(has_text=option_text)
        for attempt in range(2):
            self._dom_mousedown(dropdown)
            self.page.wait_for_timeout(500)
            try:
                option = self._wait_for_visible(
                    option,
                    "未找到下拉选项: %s" % option_text,
                    timeout=self.ACTION_VERIFY_TIMEOUT_MS,
                )
                break
            except RuntimeError:
                if attempt == 1:
                    raise

        self._dom_click_and_verify(
            option,
            lambda: selected.count() > 0,
            "下拉框未切换为: %s" % option_text,
        )

    def _is_visible_column_desc_sorted(self, label):
        rows = self.page.evaluate(
            """label => {
                const headers = Array.from(document.querySelectorAll('thead th'));
                const header = headers.find(el => (el.innerText || '').trim() === label);
                const container = header ? header.closest('.ant-table-container') : null;
                if (!header || !header.parentElement || !container) return [];

                const columnIndex = Array.from(header.parentElement.children).indexOf(header);
                const body = container.querySelector('.ant-table-body tbody');
                if (columnIndex < 0 || !body) return [];

                return Array.from(body.querySelectorAll('tr')).slice(0, 30).map(row => ({
                    product: row.children[0] ? String(row.children[0].innerText || '') : '',
                    value: row.children[columnIndex]
                        ? String(row.children[columnIndex].innerText || '')
                        : '',
                }));
            }""",
            label,
        )

        values = []
        for row in rows or []:
            product = str(row.get("product") or "").strip()
            raw_value = str(row.get("value") or "")
            if not product or "讲解中" in product:
                continue
            number_text = re.sub(r"[^0-9.\-]", "", raw_value)
            if not re.search(r"\d", number_text):
                continue
            try:
                values.append(float(number_text))
            except ValueError:
                continue

        if not values:
            return False
        return all(
            index == 0 or values[index - 1] >= value
            for index, value in enumerate(values)
        )

    def _wait_stable(self):
        self.page.wait_for_timeout(1500)
