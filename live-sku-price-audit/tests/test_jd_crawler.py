import unittest
import io
import threading
from contextlib import redirect_stdout
from unittest.mock import patch

from utils.jd_crawler import (
    CLICK_TIMEOUT_MS,
    PRICE_SETTLE_MIN_WAIT_MS,
    apply_page_zoom,
    click_element_safely,
    extract_price_from_ware_business,
    check_product_unavailable,
    check_need_login,
    get_series_tabs,
    move_mouse_to_safe_area,
    find_item_by_text,
    is_expected_item_page,
    wait_for_price_ready,
    wait_for_price_change,
    is_element_selected,
    crawl_sku_with_series,
    capture_low_price_result_screenshots,
    capture_low_price_result_screenshots_with_page_factory,
)


class FakeFirstLocator:
    def __init__(self, parent):
        self.parent = parent

    def wait_for(self, **kwargs):
        self.parent.wait_calls.append(kwargs)
        if self.parent.fail_wait:
            raise TimeoutError("not ready")


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector
        self.first = FakeFirstLocator(self)
        self.wait_calls = []
        self.fail_wait = False


class FakePage:
    def __init__(self):
        self.locators = {}
        self.wait_for_function_calls = []
        self.evaluate_calls = []
        self.wait_for_timeout_calls = []
        self.viewport_size = {"width": 1600, "height": 1100}
        self.mouse = FakeMouse()

    def locator(self, selector):
        self.locators.setdefault(selector, FakeLocator(self, selector))
        return self.locators[selector]

    def wait_for_function(self, expression, *, arg=None, **kwargs):
        self.wait_for_function_calls.append((expression, arg, kwargs))

    def evaluate(self, expression, arg=None):
        self.evaluate_calls.append((expression, arg))

    def wait_for_timeout(self, timeout):
        self.wait_for_timeout_calls.append(timeout)


class FakeMouse:
    def __init__(self):
        self.moves = []

    def move(self, x, y):
        self.moves.append((x, y))


class FakeSeriesElement:
    def __init__(self, text, class_name=""):
        self.text = text
        self.class_name = class_name

    def text_content(self):
        return self.text

    def evaluate(self, expression):
        return self.class_name


class TimeoutAwareSeriesElement(FakeSeriesElement):
    def __init__(self, text, class_name=""):
        super().__init__(text, class_name)
        self.text_content_calls = []
        self.evaluate_calls = []

    def text_content(self, **kwargs):
        self.text_content_calls.append(kwargs)
        if "timeout" not in kwargs:
            raise AssertionError("text_content must use a bounded timeout")
        return self.text

    def evaluate(self, expression, **kwargs):
        self.evaluate_calls.append(kwargs)
        if "timeout" not in kwargs:
            raise AssertionError("evaluate must use a bounded timeout")
        return self.class_name


class FakeSelectedSpecElement(FakeSeriesElement):
    def locator(self, selector):
        return FakeTextFirstLocator(None)


class FakeAllLocator:
    def __init__(self, elements):
        self.elements = elements

    def all(self):
        return self.elements


class FakeSeriesPage:
    def __init__(self, elements_by_selector):
        self.elements_by_selector = elements_by_selector

    def locator(self, selector):
        return FakeAllLocator(self.elements_by_selector.get(selector, []))


class FakeClickElement:
    def __init__(self):
        self.wait_state_calls = []
        self.scroll_calls = []
        self.click_calls = []
        self.evaluate_calls = []

    def wait_for_element_state(self, state, **kwargs):
        self.wait_state_calls.append((state, kwargs))

    def scroll_into_view_if_needed(self, **kwargs):
        self.scroll_calls.append(kwargs)

    def click(self, **kwargs):
        self.click_calls.append(kwargs)
        raise TimeoutError("blocked")

    def evaluate(self, expression, **kwargs):
        self.evaluate_calls.append((expression, kwargs))


class FakeResponse:
    def __init__(self, payload, url="https://api.m.jd.com/?functionId=pc_detailpage_wareBusiness"):
        self.payload = payload
        self.url = url

    def json(self):
        return self.payload


class FakeResponseInfo:
    def __init__(self, value=None):
        self.value = value


class FakeExpectResponse:
    def __init__(self, page, predicate):
        self.page = page
        self.predicate = predicate
        self.info = FakeResponseInfo()

    def __enter__(self):
        return self.info

    def __exit__(self, exc_type, exc, tb):
        for response in self.page.responses:
            if self.predicate(response):
                self.info.value = response
                return False
        raise TimeoutError("response timeout")


class FakeNetworkPage:
    def __init__(self, responses):
        self.responses = responses
        self.listeners = []
        self.wait_for_timeout_calls = []

    def expect_response(self, predicate, **kwargs):
        return FakeExpectResponse(self, predicate)

    def on(self, event, handler):
        if event == "response":
            self.listeners.append(handler)

    def remove_listener(self, event, handler):
        if event == "response" and handler in self.listeners:
            self.listeners.remove(handler)

    def emit_responses(self):
        for response in self.responses:
            for handler in list(self.listeners):
                handler(response)

    def wait_for_timeout(self, timeout):
        self.wait_for_timeout_calls.append(timeout)


class FakeTextFirstLocator:
    def __init__(self, text):
        self.text = text

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self.text is not None else 0

    def text_content(self, **kwargs):
        return self.text or ""


class FakeTextPage:
    def __init__(self, text_by_selector):
        self.text_by_selector = text_by_selector

    def locator(self, selector):
        return FakeTextFirstLocator(self.text_by_selector.get(selector))


class FakeUrlPage:
    def __init__(self, url):
        self.url = url


class FakeNoLoginLocator:
    def count(self):
        return 0


class FakeTitleErrorPage:
    url = "https://item.jingdonghealth.cn/100224684985.html"

    def locator(self, selector):
        return FakeNoLoginLocator()

    def title(self):
        raise RuntimeError("Execution context was destroyed")


class FakeCrawlPage:
    def __init__(self, url):
        self.url = url
        self.goto_calls = []
        self.screenshot_calls = []
        self.evaluate_calls = []

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = url

    def evaluate(self, expression, arg=None):
        self.evaluate_calls.append((expression, arg))

    def screenshot(self, **kwargs):
        self.screenshot_calls.append(kwargs)


class JdCrawlerWaitTests(unittest.TestCase):
    def test_wait_for_price_ready_uses_price_locator_wait(self):
        page = FakePage()

        self.assertTrue(wait_for_price_ready(page, timeout=1234))

        first_locator = next(iter(page.locators.values()))
        self.assertEqual(first_locator.wait_calls, [{"state": "attached", "timeout": 1234}])

    def test_wait_for_price_change_waits_for_dom_text_change(self):
        page = FakePage()

        self.assertTrue(wait_for_price_change(page, "¥10.00", timeout=800))

        self.assertEqual(len(page.wait_for_function_calls), 1)
        expression, arg, kwargs = page.wait_for_function_calls[0]
        self.assertEqual(arg["previousText"], "¥10.00")
        self.assertEqual(kwargs["timeout"], 800)
        self.assertIn("for (const selector of selectors)", expression)
        self.assertIn("changedMinWaitMs", expression)
        self.assertIn("lastChangedAt", expression)
        self.assertNotIn(".some(", expression)

    def test_series_tabs_filter_non_product_navigation_labels(self):
        page = FakeSeriesPage(
            {
                ".specification-series-item": [
                    FakeSeriesElement("进店逛逛联系客服进店逛逛"),
                    FakeSeriesElement("商品详情本品由指定商家销售和发货"),
                    FakeSeriesElement("限时直降"),
                ]
            }
        )

        tabs = get_series_tabs(page)

        self.assertEqual([text for _, _, text in tabs], ["限时直降"])

    def test_series_tabs_read_text_with_bounded_timeout(self):
        element = TimeoutAwareSeriesElement("限时直降")
        page = FakeSeriesPage({".specification-series-item": [element]})

        tabs = get_series_tabs(page)

        self.assertEqual([text for _, _, text in tabs], ["限时直降"])
        self.assertTrue(element.text_content_calls)
        self.assertIn("timeout", element.text_content_calls[0])

    def test_series_tabs_ignore_specification_group_labels(self):
        page = FakeSeriesPage(
            {
                ".specification-group-label": [
                    FakeSeriesElement("规格"),
                    FakeSeriesElement("颜色规格"),
                ]
            }
        )

        self.assertEqual(get_series_tabs(page), [])

    def test_series_tabs_ignore_review_question_text(self):
        page = FakeSeriesPage(
            {
                "[class*=\"tab\"][class*=\"item\"]": [
                    FakeSeriesElement("买家评价(80)问大家我要提问"),
                ]
            }
        )

        self.assertEqual(get_series_tabs(page), [])

    def test_find_item_by_text_matches_normalized_label(self):
        items = [
            (0, object(), " 规格 A "),
            (1, object(), "规格   B"),
        ]

        item = find_item_by_text(items, "规格 B")

        self.assertIs(item, items[1])

    def test_is_element_selected_checks_jd_selected_class(self):
        self.assertTrue(is_element_selected(FakeSeriesElement("", "specification-series-item--selected")))
        self.assertFalse(is_element_selected(FakeSeriesElement("", "specification-series-item")))

    def test_click_element_safely_fails_fast_before_js_fallback(self):
        element = FakeClickElement()

        self.assertTrue(click_element_safely(None, element))

        self.assertEqual(
            element.wait_state_calls,
            [
                ("visible", {"timeout": CLICK_TIMEOUT_MS}),
                ("stable", {"timeout": CLICK_TIMEOUT_MS}),
                ("enabled", {"timeout": CLICK_TIMEOUT_MS}),
            ],
        )
        self.assertEqual(element.scroll_calls, [{"timeout": CLICK_TIMEOUT_MS}])
        self.assertEqual(element.click_calls, [{"timeout": CLICK_TIMEOUT_MS}])
        self.assertEqual(
            element.evaluate_calls,
            [
                ("el => el.scrollIntoView({block: 'center', inline: 'nearest'})", {"timeout": CLICK_TIMEOUT_MS}),
                ("el => el.click()", {"timeout": CLICK_TIMEOUT_MS}),
            ],
        )

    def test_wait_for_price_change_enforces_minimum_settle_window(self):
        page = FakePage()

        self.assertTrue(wait_for_price_change(page, "¥10.00"))

        _, _, kwargs = page.wait_for_function_calls[0]
        self.assertGreaterEqual(kwargs["timeout"], PRICE_SETTLE_MIN_WAIT_MS)

    def test_apply_page_zoom_sets_document_zoom(self):
        page = FakePage()

        apply_page_zoom(page)

        self.assertEqual(len(page.evaluate_calls), 1)
        expression, arg = page.evaluate_calls[0]
        self.assertIn("document.documentElement.style.zoom", expression)
        self.assertEqual(arg, "75%")

    def test_move_mouse_to_safe_area_moves_pointer_out_of_product_image(self):
        page = FakePage()

        self.assertTrue(move_mouse_to_safe_area(page))

        self.assertEqual(page.mouse.moves, [(1580, 20)])
        self.assertEqual(page.wait_for_timeout_calls, [100])

    def test_click_element_safely_moves_mouse_away_before_clicking(self):
        page = FakePage()
        element = FakeClickElement()

        self.assertTrue(click_element_safely(page, element))

        self.assertEqual(page.mouse.moves, [(1580, 20)])

    def test_extract_price_from_ware_business_prefers_current_price(self):
        response = FakeResponse({"price": {"p": "52.89"}})

        self.assertEqual(extract_price_from_ware_business(response), 52.89)

    def test_extract_price_from_ware_business_falls_back_to_price_gather(self):
        response = FakeResponse(
            {
                "warePriceGatherVO": {
                    "priceItemList": [
                        {"price": "27.69", "priceType": "seckillPrice"},
                        {"price": "29.90", "priceType": "regularPrice"},
                    ]
                }
            }
        )

        self.assertEqual(extract_price_from_ware_business(response), 27.69)

    def test_extract_price_from_ware_business_ignores_negative_no_price_marker(self):
        response = FakeResponse({"price": {"p": "-1.00"}})

        self.assertIsNone(extract_price_from_ware_business(response))

    def test_selected_fast_read_waits_when_dom_price_missing(self):
        from utils import jd_crawler

        item = (0, FakeSeriesElement("规格 A", "selected"), "规格 A")

        with patch("utils.jd_crawler.find_item_by_text", return_value=item), \
             patch("utils.jd_crawler.is_element_selected", return_value=True), \
             patch("utils.jd_crawler.safe_extract_price", side_effect=[None, 5.5]), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True) as wait_ready:
            success, price, source = jd_crawler.select_item_and_read_price_fast(
                object(),
                lambda page: [item],
                "规格 A",
            )

        self.assertTrue(success)
        self.assertEqual(price, 5.5)
        self.assertEqual(source, "selected-dom")
        wait_ready.assert_called_once()

    def test_fast_read_uses_later_ware_response_when_first_has_no_price(self):
        from utils import jd_crawler

        item = (0, FakeSeriesElement("规格 A", ""), "规格 A")
        page = FakeNetworkPage([
            FakeResponse({"price": {"p": "-1.00"}}),
            FakeResponse({"price": {"p": "52.89"}}),
        ])

        def click_and_emit(page, get_items_func, item_text):
            page.emit_responses()
            return True

        with patch("utils.jd_crawler.find_item_by_text", return_value=item), \
             patch("utils.jd_crawler.is_element_selected", return_value=False), \
             patch("utils.jd_crawler.get_price_text", return_value="¥99.00"), \
             patch("utils.jd_crawler.click_item_by_text", side_effect=click_and_emit), \
             patch("utils.jd_crawler.wait_for_price_change", return_value=True), \
             patch("utils.jd_crawler.safe_extract_price", return_value=99.0):
            success, price, source = jd_crawler.select_item_and_read_price_fast(
                page,
                lambda page: [item],
                "规格 A",
                response_timeout=200,
            )

        self.assertTrue(success)
        self.assertEqual(price, 52.89)
        self.assertEqual(source, "ware-business")

    def test_check_product_unavailable_detects_off_shelf_panel_before_recommendation_price(self):
        page = FakeTextPage(
            {
                ".page-right-itemOver": "商品已下架\n推荐商品\n￥4.98到手价",
                "body": "商品已下架\n推荐商品\n￥4.98到手价",
            }
        )

        self.assertTrue(check_product_unavailable(page))

    def test_check_product_unavailable_ignores_normal_product_page(self):
        page = FakeTextPage(
            {
                ".page-right-itemOver": None,
                "body": "无穷美式烤鸡腿鸡肉零食即食小吃熟食\n¥7.9",
            }
        )

        self.assertFalse(check_product_unavailable(page))

    def test_expected_item_page_accepts_matching_sku_url(self):
        page = FakeUrlPage("https://item.jd.com/100264886683.html?cu=true")

        self.assertTrue(is_expected_item_page(page, "100264886683"))

    def test_expected_item_page_accepts_supported_redirect_item_domains(self):
        self.assertTrue(
            is_expected_item_page(
                FakeUrlPage("https://item.jingdonghealth.cn/100224684985.html"),
                "100224684985",
            )
        )
        self.assertTrue(
            is_expected_item_page(
                FakeUrlPage("https://npcitem.jd.hk/10088113674148.html"),
                "10088113674148",
            )
        )

    def test_expected_item_page_rejects_homepage_redirect_for_invalid_sku(self):
        page = FakeUrlPage("https://www.jd.com/?d")

        self.assertFalse(is_expected_item_page(page, "6082"))

    def test_check_need_login_ignores_transient_title_navigation_error(self):
        self.assertFalse(check_need_login(FakeTitleErrorPage()))

    def test_crawl_marks_manual_review_when_current_price_exists_but_series_clicks_fail(self):
        page = FakeCrawlPage("https://item.jd.com/48279162646.html")

        output = io.StringIO()
        with redirect_stdout(output), \
             patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.check_need_login", return_value=False), \
             patch("utils.jd_crawler.check_product_unavailable", return_value=False), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler.safe_extract_price", return_value=8.0), \
             patch("utils.jd_crawler.get_series_tabs", return_value=[(0, object(), "油辣椒248g")]), \
             patch("utils.jd_crawler.select_item_and_read_price_fast", return_value=(False, None, "click_failed")):
            result = crawl_sku_with_series(page, "48279162646", "/tmp", threshold_price=6.0)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["price"], 8.0)
        self.assertIn("需人工复核", result["message"])
        self.assertIn("需人工复核", output.getvalue())
        self.assertNotIn("所有规格价格均", output.getvalue())

    def test_crawl_marks_manual_review_when_clicked_spec_has_no_price(self):
        page = FakeCrawlPage("https://item.jd.com/100361964982.html")
        spec_items = [(0, object(), "规格 A"), (1, object(), "规格 B")]

        with redirect_stdout(io.StringIO()), \
             patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.check_need_login", return_value=False), \
             patch("utils.jd_crawler.check_product_unavailable", return_value=False), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler.get_series_tabs", return_value=[]), \
             patch("utils.jd_crawler.get_spec_items", return_value=spec_items), \
             patch(
                 "utils.jd_crawler.select_item_and_read_price_fast",
                 side_effect=[
                     (True, None, "selected-dom"),
                     (True, 9.0, "ware-business"),
                 ],
             ):
            result = crawl_sku_with_series(page, "100361964982", "/tmp", threshold_price=6.0)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["price"], 9.0)
        self.assertIn("需人工复核", result["message"])

    def test_crawl_uses_fast_series_price_when_series_has_no_specs(self):
        page = FakeCrawlPage("https://item.jd.com/100361964982.html")

        with redirect_stdout(io.StringIO()), \
             patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.check_need_login", return_value=False), \
             patch("utils.jd_crawler.check_product_unavailable", return_value=False), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler.safe_extract_price", return_value=9.0), \
             patch("utils.jd_crawler.get_series_tabs", return_value=[(0, object(), "系列 A")]), \
             patch("utils.jd_crawler.get_spec_items", return_value=[]), \
             patch(
                 "utils.jd_crawler.select_item_and_read_price_fast",
                 return_value=(True, 5.5, "ware-business"),
             ), \
             patch("utils.jd_crawler.extract_price", return_value=9.0):
            result = crawl_sku_with_series(page, "100361964982", "/tmp", threshold_price=6.0)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["price"], 5.5)
        self.assertIn({"series": "系列 A", "spec": "默认", "price": 5.5}, result["spec_details"])

    def test_crawl_retries_selected_spec_when_initial_price_missing(self):
        page = FakeCrawlPage("https://item.jd.com/100361964982.html")
        selected = FakeSelectedSpecElement("规格 A", "selected")
        spec_items = [(0, selected, "规格 A"), (1, object(), "规格 B")]
        retried_items = []

        def fake_fast_read(page, get_items_func, item_text, price_type='current'):
            retried_items.append(item_text)
            if item_text == "规格 A":
                return True, 5.5, "selected-dom"
            return True, 9.0, "ware-business"

        with redirect_stdout(io.StringIO()), \
             patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.check_need_login", return_value=False), \
             patch("utils.jd_crawler.check_product_unavailable", return_value=False), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler.get_series_tabs", return_value=[]), \
             patch("utils.jd_crawler.get_spec_items", return_value=spec_items), \
             patch("utils.jd_crawler.safe_extract_price", return_value=None), \
             patch(
                 "utils.jd_crawler.select_item_and_read_price_fast",
                 side_effect=fake_fast_read,
             ):
            result = crawl_sku_with_series(page, "100361964982", "/tmp", threshold_price=6.0)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["price"], 5.5)
        self.assertIn("规格 A", retried_items)

    def test_crawl_does_not_mark_partial_when_selected_spec_retry_gets_price(self):
        page = FakeCrawlPage("https://item.jd.com/100361964982.html")
        selected = FakeSelectedSpecElement("规格 A", "selected")
        spec_items = [(0, selected, "规格 A")]

        with redirect_stdout(io.StringIO()), \
             patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.check_need_login", return_value=False), \
             patch("utils.jd_crawler.check_product_unavailable", return_value=False), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler.get_series_tabs", return_value=[]), \
             patch("utils.jd_crawler.get_spec_items", return_value=spec_items), \
             patch("utils.jd_crawler.safe_extract_price", return_value=None), \
             patch(
                 "utils.jd_crawler.select_item_and_read_price_fast",
                 return_value=(True, 9.0, "selected-dom"),
             ):
            result = crawl_sku_with_series(page, "100361964982", "/tmp", threshold_price=6.0)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["price"], 9.0)

    def test_fast_threshold_scan_continues_until_all_specs_are_checked_without_time_budget(self):
        page = FakeCrawlPage("https://item.jd.com/100361964982.html")
        spec_items = [(0, object(), "规格 A"), (1, object(), "规格 B"), (2, object(), "规格 C")]
        clicked_specs = []

        def fake_fast_read(page, get_items_func, item_text, price_type='current'):
            clicked_specs.append(item_text)
            return True, 9.0, "ware-business"

        def fake_monotonic():
            if len(clicked_specs) >= 1:
                return 1000.0
            return 100.0

        output = io.StringIO()
        with redirect_stdout(output), \
             patch("utils.jd_crawler.time.monotonic", side_effect=fake_monotonic), \
             patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.check_need_login", return_value=False), \
             patch("utils.jd_crawler.check_product_unavailable", return_value=False), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler.get_series_tabs", return_value=[]), \
             patch("utils.jd_crawler.get_spec_items", return_value=spec_items), \
             patch("utils.jd_crawler.select_item_and_read_price_fast", side_effect=fake_fast_read):
            result = crawl_sku_with_series(page, "100361964982", "/tmp", threshold_price=6.0)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["price"], 9.0)
        self.assertEqual(page.goto_calls[0][1]["timeout"], 60000)
        self.assertEqual(clicked_specs, ["规格 A", "规格 B", "规格 C"])
        self.assertNotIn("快扫超过", output.getvalue())
        self.assertEqual(result["diagnostics"]["spec_count"], 3)
        self.assertEqual(result["diagnostics"]["price_source_counts"]["ware-business"], 3)
        self.assertGreaterEqual(result["diagnostics"]["duration_ms"], 0)

    def test_capture_low_price_result_screenshots_only_after_audit_for_missing_low_price_images(self):
        page = FakeCrawlPage("https://item.jd.com/100224684985.html")
        results = [
            {
                "sku": "100224684985",
                "status": "success",
                "price": 5.45,
                "screenshot_path": None,
                "spec_details": [
                    {"series": "默认", "spec": "【年销10亿贴丨标准装】10贴", "price": 5.45},
                    {"series": "默认", "spec": "【年销10亿贴丨爆款组套】60贴装", "price": 32.5},
                ],
            },
            {"sku": "10088113674148", "status": "success", "price": 27.9, "screenshot_path": None},
            {"sku": "100218639677", "status": "success", "price": 5.9, "screenshot_path": "/tmp/existing.png"},
            {"sku": "48279162646", "status": "partial", "price": 5.0, "screenshot_path": None},
        ]
        clicked = []

        def fake_click(target_page, get_items_func, item_text, timeout=2500):
            clicked.append((get_items_func.__name__, item_text))
            return True

        with patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler.wait_for_price_change", return_value=True), \
             patch("utils.jd_crawler.get_price_text", return_value="¥32.5"), \
             patch("utils.jd_crawler.click_item_by_text", side_effect=fake_click):
            count = capture_low_price_result_screenshots(page, results, "/tmp/screens", 6.0)

        self.assertEqual(count, 1)
        self.assertEqual(page.goto_calls, [("https://item.jd.com/100224684985.html", {"wait_until": "domcontentloaded", "timeout": 60000})])
        self.assertEqual(results[0]["screenshot_path"], "/tmp/screens/100224684985.png")
        self.assertEqual(page.screenshot_calls, [{"path": "/tmp/screens/100224684985.png", "full_page": False}])
        self.assertEqual(clicked, [("get_spec_items", "【年销10亿贴丨标准装】10贴")])

    def test_capture_low_price_result_screenshots_skips_image_when_low_spec_cannot_be_selected(self):
        page = FakeCrawlPage("https://item.jd.com/100224684985.html")
        results = [
            {
                "sku": "100224684985",
                "status": "success",
                "price": 5.45,
                "screenshot_path": None,
                "spec_details": [
                    {"series": "默认", "spec": "【年销10亿贴丨标准装】10贴", "price": 5.45},
                ],
            },
        ]

        with patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler.get_price_text", return_value="¥32.5"), \
             patch("utils.jd_crawler.click_item_by_text", return_value=False):
            count = capture_low_price_result_screenshots(page, results, "/tmp/screens", 6.0)

        self.assertEqual(count, 0)
        self.assertIsNone(results[0]["screenshot_path"])
        self.assertEqual(page.screenshot_calls, [])

    def test_capture_low_price_result_screenshots_skips_login_or_invalid_pages(self):
        page = FakeCrawlPage("https://passport.jd.com/new/login.aspx")
        results = [
            {"sku": "100224684985", "status": "success", "price": 5.45, "screenshot_path": None},
        ]

        with patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.check_need_login", return_value=True):
            count = capture_low_price_result_screenshots(page, results, "/tmp/screens", 6.0)

        self.assertEqual(count, 0)
        self.assertIsNone(results[0]["screenshot_path"])
        self.assertEqual(page.screenshot_calls, [])

    def test_capture_low_price_result_screenshots_with_page_factory_parallelizes_missing_images(self):
        created_pages = []
        cleaned_pages = []
        results = [
            {"sku": "100000000001", "status": "success", "price": 5.45, "screenshot_path": None},
            {"sku": "100000000002", "status": "success", "price": 5.90, "screenshot_path": None},
            {"sku": "100000000003", "status": "success", "price": 7.90, "screenshot_path": None},
            {"sku": "100000000004", "status": "partial", "price": 5.50, "screenshot_path": None},
            {"sku": "100000000005", "status": "success", "price": 5.30, "screenshot_path": "/tmp/existing.png"},
        ]

        def page_factory(worker_index):
            page = FakeCrawlPage("about:blank")
            created_pages.append((worker_index, page))

            def cleanup():
                cleaned_pages.append(page)

            return page, cleanup

        with patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler._select_low_price_detail_for_screenshot", return_value=True):
            summary = capture_low_price_result_screenshots_with_page_factory(
                results=results,
                screenshot_dir="/tmp/screens",
                threshold_price=6.0,
                page_factory=page_factory,
                worker_count=3,
            )

        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.captured, 2)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(summary.failed_skus, [])
        self.assertEqual(len(created_pages), 2)
        self.assertEqual(len(cleaned_pages), 2)
        self.assertEqual(results[0]["screenshot_path"], "/tmp/screens/100000000001.png")
        self.assertEqual(results[1]["screenshot_path"], "/tmp/screens/100000000002.png")
        self.assertIsNone(results[2]["screenshot_path"])
        self.assertIsNone(results[3]["screenshot_path"])
        self.assertEqual(results[4]["screenshot_path"], "/tmp/existing.png")

    def test_capture_low_price_result_screenshots_with_page_factory_accepts_login_recovery_tuple(self):
        created_pages = []
        cleaned_pages = []
        recovery_callbacks = []
        results = [
            {"sku": "100000000001", "status": "success", "price": 5.45, "screenshot_path": None},
        ]

        def page_factory(worker_index):
            page = FakeCrawlPage("about:blank")
            created_pages.append(page)

            def cleanup():
                cleaned_pages.append(page)

            def recover_login():
                recovery_callbacks.append(worker_index)
                return True

            return page, cleanup, recover_login

        with patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler._select_low_price_detail_for_screenshot", return_value=True):
            summary = capture_low_price_result_screenshots_with_page_factory(
                results=results,
                screenshot_dir="/tmp/screens",
                threshold_price=6.0,
                page_factory=page_factory,
                worker_count=3,
            )

        self.assertEqual(summary.total, 1)
        self.assertEqual(summary.captured, 1)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(len(created_pages), 1)
        self.assertEqual(cleaned_pages, created_pages)
        self.assertEqual(recovery_callbacks, [])
        self.assertEqual(results[0]["screenshot_path"], "/tmp/screens/100000000001.png")

    def test_capture_low_price_result_screenshots_with_page_factory_reports_failures(self):
        results = [
            {"sku": "100000000001", "status": "success", "price": 5.45, "screenshot_path": None},
            {"sku": "100000000002", "status": "success", "price": 5.55, "screenshot_path": None},
        ]

        def page_factory(worker_index):
            page = FakeCrawlPage("about:blank")
            return page, lambda: None

        def fake_select(page, result):
            return result["sku"] == "100000000001"

        with patch("utils.jd_crawler.apply_page_zoom", return_value=True), \
             patch("utils.jd_crawler.move_mouse_to_safe_area", return_value=True), \
             patch("utils.jd_crawler.wait_for_price_ready", return_value=True), \
             patch("utils.jd_crawler.close_popups", return_value=None), \
             patch("utils.jd_crawler._select_low_price_detail_for_screenshot", side_effect=fake_select):
            summary = capture_low_price_result_screenshots_with_page_factory(
                results=results,
                screenshot_dir="/tmp/screens",
                threshold_price=6.0,
                page_factory=page_factory,
                worker_count=2,
            )

        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.captured, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.failed_skus, ["100000000002"])

    def test_capture_low_price_result_screenshots_with_page_factory_skips_when_no_work(self):
        calls = []
        results = [
            {"sku": "100000000001", "status": "success", "price": 7.0, "screenshot_path": None},
        ]

        summary = capture_low_price_result_screenshots_with_page_factory(
            results=results,
            screenshot_dir="/tmp/screens",
            threshold_price=6.0,
            page_factory=lambda worker_index: calls.append(worker_index),
            worker_count=3,
        )

        self.assertEqual(summary.total, 0)
        self.assertEqual(summary.captured, 0)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(calls, [])

    def test_capture_low_price_result_screenshots_with_page_factory_returns_promptly_when_stopped_during_capture(self):
        stop_event = threading.Event()
        capture_started = threading.Event()
        release_capture = threading.Event()
        results = [
            {"sku": "100000000001", "status": "success", "price": 5.45, "screenshot_path": None},
        ]
        summary_holder = []

        def blocked_capture(**kwargs):
            capture_started.set()
            release_capture.wait(timeout=2)
            return 1

        runner_thread = threading.Thread(
            target=lambda: summary_holder.append(
                capture_low_price_result_screenshots_with_page_factory(
                    results=results,
                    screenshot_dir="/tmp/screens",
                    threshold_price=6.0,
                    page_factory=lambda worker_index: (FakeCrawlPage("about:blank"), lambda: None),
                    worker_count=1,
                    should_stop=stop_event.is_set,
                )
            )
        )

        with patch("utils.jd_crawler.capture_low_price_result_screenshots", side_effect=blocked_capture):
            runner_thread.start()
            self.assertTrue(capture_started.wait(timeout=1))
            stop_event.set()
            try:
                runner_thread.join(timeout=0.3)
                self.assertFalse(runner_thread.is_alive())
                self.assertEqual(summary_holder[0].total, 1)
                self.assertEqual(summary_holder[0].captured, 0)
            finally:
                release_capture.set()
                runner_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
