"""
京东价格爬取模块
负责打开 SKU 页面、提取价格、截图、关闭弹窗
支持多种价格类型抓取
支持多系列多规格遍历（新版京东商品页）
"""

import os
import queue
import time
import re
import threading
from urllib.parse import urlparse


PRICE_SELECTORS = [
    ".product-price--value",
    ".p-price .price",
    ".price-now .price",
    "[class*='price'] [class*='value']"
]

SPEC_ITEM_SELECTORS = [
    ".specification-item-sku",
    ".p-choose-item",
    "[class*='sku-item']",
    ".choose-item",
]

CLICK_TIMEOUT_MS = 2500
FAST_CLICK_TIMEOUT_MS = 800
PRICE_SETTLE_MIN_WAIT_MS = 2600
PRICE_STABLE_MS = 900
PRICE_CHANGE_TIMEOUT_MS = 6000
FAST_PRICE_RESPONSE_TIMEOUT_MS = 3500
WARE_RESPONSE_POLL_MS = 50
ELEMENT_TEXT_TIMEOUT_MS = 700
PAGE_ZOOM = "75%"
SELECTED_CLASS_KEYWORDS = ("selected", "active", "current", "checked")
THREAD_JOIN_POLL_SECONDS = 0.05
STOP_JOIN_GRACE_SECONDS = 0.05

INVALID_SERIES_LABELS = {'买家评价', '商品详情', '售后保障', '推荐'}
INVALID_SERIES_KEYWORDS = ('进店逛逛', '联系客服', '商品详情', '本品由', '买家评价', '问大家', '我要提问')
SUPPORTED_ITEM_NETLOCS = {
    "item.jd.com",
    "item.jingdonghealth.cn",
    "npcitem.jd.hk",
}
RISK_HANDLER_NETLOCS = {
    "cfe.m.jd.com",
}
UNAVAILABLE_PRODUCT_MARKERS = (
    '商品已下架',
    '商品已停售',
    '商品已下柜',
    '该商品已下架',
    '该商品已下柜',
    '商品不存在',
    '商品已售罄',
    '您查看的商品不存在',
)
UNAVAILABLE_PRODUCT_SELECTORS = (
    '.page-right-itemOver',
    '[class*="itemOver"]',
    '.page-right-content',
    '.page-right-information',
    '.page-right-wrap',
)


def wait_for_price_ready(page, timeout=5000):
    """
    等待价格 DOM 就绪。失败时返回 False，由调用方决定是否继续兜底。
    """
    try:
        page.locator(", ".join(PRICE_SELECTORS)).first.wait_for(state="attached", timeout=timeout)
        return True
    except Exception:
        return False


def wait_for_spec_items_ready(page, timeout=1500):
    """
    等待规格 DOM 就绪，避免每次点击系列后固定等待。
    """
    try:
        page.locator(", ".join(SPEC_ITEM_SELECTORS)).first.wait_for(state="attached", timeout=timeout)
        return True
    except Exception:
        return False


def apply_page_zoom(page, zoom=PAGE_ZOOM):
    """
    将商品页缩放到 75%，减少规格项被右侧购买栏或浮层遮住的概率。
    """
    try:
        page.evaluate(
            """zoom => {
                const applyZoom = () => {
                    if (document.documentElement) {
                        document.documentElement.style.zoom = zoom;
                    }
                };
                applyZoom();
                requestAnimationFrame(applyZoom);
            }""",
            zoom,
        )
        return True
    except Exception:
        return False


def move_mouse_to_safe_area(page):
    """
    避免人工鼠标停在主图上触发放大/悬浮层，导致后续规格点击被遮挡。
    这里只做鼠标移开动作，不再固定等待 100ms；每个规格省一次等待，
    对 600 SKU x 20 规格的规模可节省大量时间。
    """
    if not page:
        return False

    try:
        viewport_size = getattr(page, "viewport_size", None) or {}
        width = viewport_size.get("width", 1600)
        page.mouse.move(max(width - 20, 20), 20)
        return True
    except Exception:
        return False


def get_price_text(page):
    for selector in PRICE_SELECTORS:
        try:
            element = page.locator(selector).first
            if element.count() > 0:
                text = element.text_content().strip()
                if text:
                    return text
        except Exception:
            continue
    return ""


def _element_text_content(element, timeout=ELEMENT_TEXT_TIMEOUT_MS):
    try:
        return element.text_content(timeout=timeout).strip()
    except TypeError:
        try:
            return element.text_content().strip()
        except Exception:
            return ""
    except Exception:
        return ""


def _element_class_name(element, timeout=ELEMENT_TEXT_TIMEOUT_MS):
    expression = "el => typeof el.className === 'string' ? el.className : String(el.className)"
    try:
        return element.evaluate(expression, timeout=timeout)
    except TypeError:
        try:
            return element.evaluate(expression)
        except Exception:
            return ""
    except Exception:
        return ""


def wait_for_price_change(page, previous_text, timeout=PRICE_CHANGE_TIMEOUT_MS):
    """
    点击系列/规格后等待价格文本稳定。

    京东页会出现连续两次价格刷新：先刷系列默认规格，再刷目标规格。
    这里按 extract_price 使用的选择器顺序读取第一个非空价格，并要求价格稳定一段时间后再继续。
    若新旧规格真实同价，等待最小稳定窗口后放行。
    """
    if not previous_text:
        return wait_for_price_ready(page, timeout=timeout)

    state_key = f"__jdPriceWait_{time.time_ns()}"
    try:
        page.wait_for_function(
            """({ selectors, previousText, stateKey, stableMs, changedMinWaitMs, noChangeMinWaitMs }) => {
                const currentText = (() => {
                    for (const selector of selectors) {
                        const element = document.querySelector(selector);
                        const text = element ? element.textContent.trim() : "";
                        if (text) {
                            return text;
                        }
                    }
                    return "";
                })();
                const now = Date.now();
                let state = window[stateKey];
                if (!state) {
                    state = {
                        startedAt: now,
                        lastText: currentText,
                        lastChangedAt: now,
                        changedFromPrevious: Boolean(currentText && currentText !== previousText)
                    };
                    window[stateKey] = state;
                    return false;
                }
                if (currentText && currentText !== state.lastText) {
                    state.lastText = currentText;
                    state.lastChangedAt = now;
                    if (currentText !== previousText) {
                        state.changedFromPrevious = true;
                    }
                }
                const elapsed = now - state.startedAt;
                const stableFor = now - state.lastChangedAt;
                if (state.changedFromPrevious) {
                    return elapsed >= changedMinWaitMs && stableFor >= stableMs;
                }
                return Boolean(currentText) && elapsed >= noChangeMinWaitMs;
            }""",
            arg={
                "selectors": PRICE_SELECTORS,
                "previousText": previous_text,
                "stateKey": state_key,
                "stableMs": PRICE_STABLE_MS,
                "changedMinWaitMs": PRICE_SETTLE_MIN_WAIT_MS,
                "noChangeMinWaitMs": PRICE_SETTLE_MIN_WAIT_MS,
            },
            timeout=timeout,
        )
        return True
    except Exception:
        return wait_for_price_ready(page, timeout=300)
    finally:
        try:
            page.evaluate("key => { try { delete window[key]; } catch(e) {} }", state_key)
        except Exception:
            pass


def _parse_price_value(value):
    if value is None:
        return None
    numbers = re.findall(r'-?\d+\.?\d*', str(value))
    if not numbers:
        return None
    price = float(numbers[0])
    if price < 0:
        return None
    return price


def extract_price_from_ware_business(response):
    """
    从京东 pc_detailpage_wareBusiness 响应中直接取当前售价，避免等待页面 DOM 慢更新。
    """
    data = response.json()

    for path in (
        ("price", "p"),
        ("miaoshaInfo", "promoPrice"),
    ):
        current = data
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        price = _parse_price_value(current)
        if price is not None:
            return price

    price_items = (
        data.get("warePriceGatherVO", {}).get("priceItemList", [])
        if isinstance(data, dict)
        else []
    )
    if isinstance(price_items, list):
        for item in price_items:
            if isinstance(item, dict):
                price = _parse_price_value(item.get("price"))
                if price is not None:
                    return price

    return None


def is_ware_business_response(response):
    return "functionId=pc_detailpage_wareBusiness" in getattr(response, "url", "")


def _ware_business_has_price(response):
    """
    expect_response 的谓词：只匹配带有效价格的 wareBusiness 响应。
    这样 Playwright 无需把每个响应事件都送到 Python 处理，降低 Windows IPC 开销。
    """
    if not is_ware_business_response(response):
        return False
    try:
        return extract_price_from_ware_business(response) is not None
    except Exception:
        return False


def safe_extract_price(page, price_type='current'):
    try:
        return extract_price(page, price_type)
    except Exception:
        return None


def close_popups(page):
    """
    关闭页面上的登录弹窗和遮罩层
    """
    page.evaluate("""() => {
        const selectors = [
            '.ui-dialog', '.login-modal', '[class*="login"]', '[class*="modal"]',
            '.dialog', '.popup', '.mask', '.overlay', '[class*="mask"]', '[class*="overlay"]',
            '.model', '.layer', '.login-form', '.login-tab', '.login-box', '.qrcode-login'
        ];
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                if(el && el.style) {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    el.style.opacity = '0';
                    try { el.remove(); } catch(e) {}
                }
            });
        });
        document.body.style.overflow = 'auto';
        return 'popups closed';
    }""")


def extract_price(page, price_type='current'):
    """
    从页面提取价格

    Args:
        page: Playwright page 对象
        price_type: 价格类型
            - 'current': 当前售价（默认，最稳定）
            - 'origin': 原价/定价
            - 'plus': Plus会员价
            - 'deal': 到手价/补贴价
            - 'all': 返回所有价格信息

    Returns:
        float or dict: 价格数值或价格信息字典
    """
    if price_type == 'all':
        return extract_all_prices(page)

    # 定义各价格类型的选择器
    selectors = {
        'current': PRICE_SELECTORS,
        'origin': [
            ".product-price--origin",
            ".p-price .del",
            ".price-orig",
            "[class*='origin']",
            "[class*='old']"
        ],
        'plus': [
            ".plus-price",
            ".p-price-plus",
            "[class*='plus'][class*='price']"
        ],
        'deal': [
            ".deal-price",
            "[class*='deal']",
            "[class*='到手']"
        ]
    }

    # 获取对应类型的选择器列表
    type_selectors = selectors.get(price_type, selectors['current'])

    for selector in type_selectors:
        try:
            element = page.locator(selector).first
            if element.count() > 0:
                price_text = element.text_content().strip()
                price = _parse_price_value(price_text)
                if price is not None:
                    return price
        except:
            continue

    # 如果指定类型未找到，fallback 到当前售价
    if price_type != 'current':
        return extract_price(page, 'current')

    raise Exception(f"无法提取价格，尝试的选择器: {type_selectors}")


def extract_all_prices(page):
    """
    提取页面上的所有价格信息
    返回字典包含各种价格类型
    """
    result = {
        'current': None,   # 当前售价
        'origin': None,    # 原价
        'plus': None,      # Plus价
        'deal': None,      # 到手价
        'promo': None      # 促销信息
    }

    # 1. 当前售价
    try:
        result['current'] = extract_price(page, 'current')
    except:
        pass

    # 2. 原价
    try:
        result['origin'] = extract_price(page, 'origin')
    except:
        pass

    # 3. Plus价
    try:
        result['plus'] = extract_price(page, 'plus')
    except:
        pass

    # 4. 到手价/补贴价（从页面文本中提取）
    try:
        page_text = page.locator(".product-price-panel, .page-right-price").first.text_content()
        # 匹配"到手价¥xx"或"补贴价¥xx"
        deal_match = re.search(r'(到手价|补贴价)[¥\s]*(\d+\.?\d*)', page_text)
        if deal_match:
            result['deal'] = float(deal_match.group(2))
    except:
        pass

    # 5. 促销信息
    try:
        promo = page.locator(".promo-words, .promotion").first
        if promo.count() > 0:
            result['promo'] = promo.text_content().strip()[:100]
    except:
        pass

    return result


def _contains_unavailable_marker(text):
    normalized = re.sub(r'\s+', '', text or '')
    return any(marker in normalized for marker in UNAVAILABLE_PRODUCT_MARKERS)


def _first_locator_text(page, selector, timeout=1000):
    try:
        locator = page.locator(selector).first
        if locator.count() <= 0:
            return ""
        try:
            return locator.text_content(timeout=timeout).strip()
        except TypeError:
            return locator.text_content().strip()
    except Exception:
        return ""


def check_product_unavailable(page):
    """
    检查主商品是否已下架/停售/不存在。

    京东下架页仍可能展示右侧推荐商品价格，必须在提取价格前拦截。
    """
    for selector in UNAVAILABLE_PRODUCT_SELECTORS:
        if _contains_unavailable_marker(_first_locator_text(page, selector)):
            return True

    body_text = _first_locator_text(page, 'body')
    normalized_body = re.sub(r'\s+', '', body_text or '')
    has_purchase_action = any(action in normalized_body for action in ('加入购物车', '立即购买'))
    return _contains_unavailable_marker(body_text) and not has_purchase_action


def is_expected_item_page(page, sku):
    """
    确认当前页面仍是输入 SKU 的京东商品页。

    错误 SKU 会跳到京东首页，首页/推荐区也有价格，不能继续走通用价格提取。
    """
    try:
        parsed = urlparse(page.url or "")
    except Exception:
        return False

    return (
        parsed.netloc in SUPPORTED_ITEM_NETLOCS
        and parsed.path.rstrip("/") == f"/{sku}.html"
    )


def is_jd_risk_handler_page(page):
    try:
        parsed = urlparse(page.url or "")
    except Exception:
        return False

    return (
        parsed.netloc in RISK_HANDLER_NETLOCS
        and "/privatedomain/risk_handler/" in parsed.path
    )


def check_need_login(page):
    """
    检查页面是否需要登录
    """
    # 检查 URL 是否跳转到登录页
    if "passport.jd.com" in page.url:
        return True

    # 检查是否有登录表单
    try:
        if page.locator(".login-form").count() > 0:
            return True
    except:
        pass

    # 检查页面标题是否包含登录；跳转页偶发二次导航时 title 读取会失败，不能因此中断测价。
    try:
        if "登录" in page.title():
            return True
    except Exception:
        pass

    return False


def get_series_tabs(page):
    """
    获取页面上的所有系列标签
    支持多种选择器策略，兼容不同版本的京东页面

    Returns:
        list: [(index, element, text), ...] 系列标签列表
    """
    # 策略1: 新版京东 - 系列标签通常是 .left-tabs-item 或类似结构
    # 策略2: 可能是 .p-choose 下的系列选择
    # 策略3: 可能是 .sku-series 或 [class*="series"]
    # 策略4: 可能是 .item 中带有特定文本的元素

    strategies = [
        # 策略1: 新版京东系列标签（如：镇店爆款、品质纯奶、限时直降）
        '.specification-series-item',
        # 策略2: 旧版京东系列标签
        '.left-tabs-item',
        # 策略3: 通用 tab 结构
        '[class*="tab"][class*="item"]',
        # 策略4: 系列相关
        '[class*="series"]',
    ]

    for strategy in strategies:
        try:
            elements = page.locator(strategy).all()
            if elements:
                tabs = []
                for i, el in enumerate(elements):
                    text = _element_text_content(el)
                    # 过滤掉无效标签（如评价、详情等导航标签）
                    if (
                        text
                        and len(text) < 20
                        and text not in INVALID_SERIES_LABELS
                        and not any(keyword in text for keyword in INVALID_SERIES_KEYWORDS)
                    ):
                        tabs.append((i, el, text))
                if tabs:
                    return tabs
        except:
            continue

    return []


def get_spec_items(page):
    """
    获取当前系列下的所有规格选项
    支持多种选择器策略

    Returns:
        list: [(index, element, text), ...] 规格选项列表
    """
    strategies = SPEC_ITEM_SELECTORS

    for strategy in strategies:
        try:
            elements = page.locator(strategy).all()
            if elements:
                items = []
                for i, el in enumerate(elements):
                    # 尝试获取文本（可能是图片+文字结构）
                    text_el = el.locator('[class*="text"], .name, .title').first
                    if text_el.count() > 0:
                        text = _element_text_content(text_el)
                    else:
                        text = _element_text_content(el)
                    # 过滤无货项
                    if text and '无货' not in text and '缺货' not in text:
                        items.append((i, el, text))
                if items:
                    return items
        except:
            continue

    return []


def normalize_option_text(text):
    return re.sub(r'\s+', ' ', (text or '').strip())


def find_item_by_text(items, target_text):
    target = normalize_option_text(target_text)
    for item in items:
        if normalize_option_text(item[2]) == target:
            return item
    return None


def is_element_selected(element):
    try:
        class_name = _element_class_name(element)
        class_name = (class_name or "").lower()
        return any(keyword in class_name for keyword in SELECTED_CLASS_KEYWORDS)
    except Exception:
        return False


def wait_for_item_selected(page, get_items_func, item_text, timeout=2500):
    deadline = time.time() + timeout / 1000
    while True:
        item = find_item_by_text(get_items_func(page), item_text)
        if item and is_element_selected(item[1]):
            return True

        if time.time() >= deadline:
            return False

        try:
            page.wait_for_timeout(100)
        except Exception:
            time.sleep(0.1)


def click_item_by_text(page, get_items_func, item_text, timeout=CLICK_TIMEOUT_MS):
    """
    每次点击前按文本重新获取 DOM，并等待该项进入 selected 状态。
    """
    item = find_item_by_text(get_items_func(page), item_text)
    if not item:
        return False

    _, element, _ = item
    if is_element_selected(element):
        return True

    if not click_element_safely(page, element, timeout=timeout):
        return False

    if wait_for_item_selected(page, get_items_func, item_text, timeout=timeout):
        return True

    # 某些元素第一次点击会被页面重排吞掉，重新取新 DOM 后再点一次。
    item = find_item_by_text(get_items_func(page), item_text)
    if not item:
        return False
    _, element, _ = item
    if not click_element_safely(page, element, timeout=timeout):
        return False
    return wait_for_item_selected(page, get_items_func, item_text, timeout=timeout)


def click_item_by_text_fast(page, get_items_func, item_text, timeout=FAST_CLICK_TIMEOUT_MS):
    """
    快扫模式只负责发出点击，不等待 selected 状态。

    Windows 上京东规格项 selected 状态更新慢或类名不稳定时，等待 selected
    会把每个规格拖慢数秒；快扫价格以 wareBusiness 响应为准。
    """
    item = find_item_by_text(get_items_func(page), item_text)
    if not item:
        return False

    _, element, _ = item
    if is_element_selected(element):
        return True

    return click_element_safely(page, element, timeout=timeout)


def selected_item_text(items):
    for _, element, text in items:
        if is_element_selected(element):
            return text
    return None


def select_item_and_read_price_fast(page, get_items_func, item_text, price_type='current',
                                    response_timeout=FAST_PRICE_RESPONSE_TIMEOUT_MS):
    """
    快扫模式：点击后优先等京东商品业务响应，直接从响应取价。

    这比等待页面 DOM 价格稳定快，且不会读到上一个规格残留价格。
    """
    item = find_item_by_text(get_items_func(page), item_text)
    if not item:
        return False, None, "missing"

    _, element, _ = item
    if is_element_selected(element):
        price = safe_extract_price(page, price_type)
        if price is None:
            wait_for_price_ready(page, timeout=1000)
            price = safe_extract_price(page, price_type)
        return True, price, "selected-dom"

    previous_price_text = get_price_text(page)
    clicked = False

    try:
        # 使用 expect_response + 价格谓词：只有命中 wareBusiness 且含有效价格的响应才会回调 Python。
        # 相比 page.on("response", ...) 全量监听，Windows 上可显著减少 IPC 事件量。
        with page.expect_response(_ware_business_has_price, timeout=response_timeout) as response_info:
            clicked = click_item_by_text_fast(page, get_items_func, item_text)

        if not clicked:
            return False, None, "click_failed"

        price = extract_price_from_ware_business(response_info.value)
        if price is not None:
            return True, price, "ware-business"
    except Exception:
        if not clicked:
            clicked = click_item_by_text_fast(page, get_items_func, item_text)
        if not clicked:
            return False, None, "click_failed"

    wait_for_price_change(page, previous_price_text)
    return True, safe_extract_price(page, price_type), "dom-fallback"


def click_element_safely(page, element, timeout=CLICK_TIMEOUT_MS):
    """
    安全点击元素，处理可能的拦截问题
    """
    move_mouse_to_safe_area(page)

    for state in ("visible", "stable", "enabled"):
        try:
            element.wait_for_element_state(state, timeout=timeout)
        except Exception:
            pass

    try:
        element.evaluate("el => el.scrollIntoView({block: 'center', inline: 'nearest'})", timeout=timeout)
    except Exception:
        pass

    try:
        try:
            element.scroll_into_view_if_needed(timeout=timeout)
        except Exception:
            pass
        # 先尝试普通点击
        element.click(timeout=timeout)
        return True
    except Exception as e:
        # 如果被拦截，尝试通过 JS 点击
        try:
            element.evaluate('el => el.click()', timeout=timeout)
            return True
        except:
            return False


def _stopped_result(sku):
    return {
        'sku': sku,
        'price': None,
        'all_prices': None,
        'spec_details': [],
        'screenshot_path': None,
        'status': 'stopped',
        'message': '用户停止测价'
    }


def _unavailable_result(sku):
    return {
        'sku': sku,
        'price': None,
        'all_prices': None,
        'spec_details': [],
        'screenshot_path': None,
        'status': 'unavailable',
        'message': '商品已下架或不可售'
    }


def _invalid_sku_result(sku, current_url):
    return {
        'sku': sku,
        'price': None,
        'all_prices': None,
        'spec_details': [],
        'screenshot_path': None,
        'status': 'invalid_sku',
        'message': f'SKU链接跳转到非商品页: {current_url or "未知页面"}'
    }


def _risk_verification_result(sku, current_url):
    return {
        'sku': sku,
        'price': None,
        'all_prices': None,
        'spec_details': [],
        'screenshot_path': None,
        'status': 'need_login',
        'message': (
            '京东触发风险验证，请在测价浏览器窗口完成验证后点击“我已登录，继续”；'
            f'当前页面: {current_url or "未知页面"}'
        )
    }


def _lowest_price_detail(result):
    lowest_detail = None
    lowest_price = None

    for detail in result.get('spec_details') or []:
        if not isinstance(detail, dict):
            continue
        price = _parse_price_value(detail.get('price'))
        if price is None:
            continue
        if lowest_price is None or price < lowest_price:
            lowest_price = price
            lowest_detail = detail

    return lowest_detail


def _is_default_series_label(label):
    return normalize_option_text(label) in ("", "默认", "当前页面")


def _is_default_spec_label(label):
    return normalize_option_text(label) in ("", "默认", "默认规格", "当前SKU")


def _needs_low_price_screenshot(result, threshold_price):
    if result.get('status') != 'success':
        return False
    price = result.get('price')
    if price is None or price >= threshold_price:
        return False
    if result.get('screenshot_path'):
        return False
    return bool(str(result.get('sku') or '').strip())


class ScreenshotCaptureSummary:
    def __init__(self, total=0, captured=0, failed_skus=None):
        self.total = total
        self.captured = captured
        self.failed_skus = failed_skus or []

    @property
    def failed(self):
        return len(self.failed_skus)


def _select_low_price_detail_for_screenshot(page, result):
    detail = _lowest_price_detail(result)
    if not detail:
        return True

    series_name = normalize_option_text(detail.get('series'))
    spec_name = normalize_option_text(detail.get('spec'))

    if not _is_default_series_label(series_name):
        previous_price_text = get_price_text(page)
        if click_item_by_text(page, get_series_tabs, series_name):
            wait_for_spec_items_ready(page, timeout=1500)
            wait_for_price_change(page, previous_price_text)
        else:
            print(f"  ⚠️ 补截图时未能选中系列: {series_name}")
            return False

    if not _is_default_spec_label(spec_name):
        previous_price_text = get_price_text(page)
        if click_item_by_text(page, get_spec_items, spec_name):
            wait_for_price_change(page, previous_price_text)
        else:
            print(f"  ⚠️ 补截图时未能选中规格: {spec_name}")
            return False

    return True


def capture_low_price_result_screenshots(page, results, screenshot_dir, threshold_price, should_stop=None):
    """
    测价结束后，为低于门槛且尚未截图的 SKU 补充截图。

    快扫阶段优先保证速度和价格判断，截图放到最后集中做，避免拖慢每个 SKU 的遍历。
    """
    should_stop = should_stop or (lambda: False)
    captured = 0

    for result in results:
        if should_stop():
            break

        if result.get('status') != 'success':
            continue
        price = result.get('price')
        if price is None or price >= threshold_price:
            continue
        if result.get('screenshot_path'):
            continue

        sku = str(result.get('sku') or '').strip()
        if not sku:
            continue

        screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
        try:
            os.makedirs(screenshot_dir, exist_ok=True)
            page.goto(f"https://item.jd.com/{sku}.html", wait_until="domcontentloaded", timeout=60000)
            apply_page_zoom(page)
            move_mouse_to_safe_area(page)
            wait_for_price_ready(page, timeout=5000)
            if not is_expected_item_page(page, sku):
                print(f"  ⚠️ 低价 SKU {sku} 补截图页面异常: {page.url}")
                continue
            if check_need_login(page):
                print(f"  ⚠️ 低价 SKU {sku} 补截图需要登录，跳过截图")
                continue
            if check_product_unavailable(page):
                print(f"  ⚠️ 低价 SKU {sku} 补截图时商品不可售，跳过截图")
                continue
            close_popups(page)
            if not _select_low_price_detail_for_screenshot(page, result):
                print(f"  ⚠️ 低价 SKU {sku} 未能定位到低价规格，跳过截图")
                continue
            page.evaluate('() => window.scrollTo(0, 0)')
            time.sleep(0.3)
            page.screenshot(path=screenshot_path, full_page=False)
            result['screenshot_path'] = screenshot_path
            captured += 1
            print(f"  📸 低价 SKU 截图已保存: {screenshot_path}")
        except Exception as e:
            print(f"  ⚠️ 低价 SKU {sku} 截图失败: {e}")

    return captured


def capture_low_price_result_screenshots_with_page_factory(
    results,
    screenshot_dir,
    threshold_price,
    page_factory,
    worker_count=3,
    should_stop=None,
):
    """
    测价结束后并发补低价截图。

    Playwright sync Page 必须在创建它的线程内使用，所以这里接收 page_factory，
    由每个 worker 在线程内创建并清理自己的页面。
    """
    should_stop = should_stop or (lambda: False)
    pending_results = [
        result for result in results
        if _needs_low_price_screenshot(result, threshold_price)
    ]

    if not pending_results or should_stop():
        return ScreenshotCaptureSummary()

    worker_count = max(1, min(worker_count, len(pending_results)))
    jobs = queue.Queue()
    for result in pending_results:
        jobs.put(result)

    captured = 0
    captured_lock = threading.Lock()

    def normalize_factory_result(factory_result):
        if isinstance(factory_result, tuple):
            if len(factory_result) >= 2:
                return factory_result[0], factory_result[1]
            if len(factory_result) == 1:
                return factory_result[0], None
        return factory_result, None

    def worker(worker_index):
        nonlocal captured
        page = None
        cleanup = None
        try:
            page, cleanup = normalize_factory_result(page_factory(worker_index))

            while not should_stop():
                try:
                    result = jobs.get_nowait()
                except queue.Empty:
                    return

                try:
                    count = capture_low_price_result_screenshots(
                        page=page,
                        results=[result],
                        screenshot_dir=screenshot_dir,
                        threshold_price=threshold_price,
                        should_stop=should_stop,
                    )
                    if should_stop():
                        return
                    if count:
                        with captured_lock:
                            captured += count
                finally:
                    jobs.task_done()
        except Exception as e:
            print(f"  ⚠️ 低价截图 worker {worker_index + 1} 失败: {e}")
        finally:
            if cleanup:
                try:
                    cleanup()
                except Exception:
                    pass

    threads = [
        threading.Thread(target=worker, args=(worker_index,), daemon=True)
        for worker_index in range(worker_count)
    ]
    for thread in threads:
        thread.start()

    while True:
        alive_threads = [thread for thread in threads if thread.is_alive()]
        if not alive_threads:
            break
        if should_stop():
            for thread in alive_threads:
                thread.join(timeout=STOP_JOIN_GRACE_SECONDS)
            break
        for thread in alive_threads:
            thread.join(timeout=THREAD_JOIN_POLL_SECONDS)

    failed_skus = [
        str(result.get('sku') or '').strip()
        for result in pending_results
        if _needs_low_price_screenshot(result, threshold_price)
    ]

    return ScreenshotCaptureSummary(
        total=len(pending_results),
        captured=captured,
        failed_skus=failed_skus,
    )


def crawl_sku_with_series(page, sku, screenshot_dir, delay_min=1, delay_max=3,
                          price_type='current', threshold_price=None,
                          should_stop=None):
    """
    爬取单个 SKU 的所有系列和规格的价格
    遍历所有系列标签下的所有规格选项，收集最低价格
    发现低于门槛价的规格时立即截图，确保截图与价格一致

    Args:
        page: Playwright page 对象
        sku: SKU 编号
        screenshot_dir: 截图保存目录
        delay_min: 最小延迟（秒）
        delay_max: 最大延迟（秒）
        price_type: 抓取的价格类型
        threshold_price: 价格门槛

    Returns:
        dict: {
            'sku': sku,
            'price': float or None,           # 所有规格中的最低价格
            'all_prices': dict or None,
            'spec_details': list,              # 所有规格的详细价格信息
            'screenshot_path': str or None,    # 如果有低于门槛的规格，截图保存
            'status': str,
            'message': str
        }
    """
    url = f"https://item.jd.com/{sku}.html"
    should_stop = should_stop or (lambda: False)
    sku_started_at = time.monotonic()
    price_source_counts = {}

    def build_diagnostics(spec_count=0):
        return {
            'duration_ms': int((time.monotonic() - sku_started_at) * 1000),
            'spec_count': spec_count,
            'price_source_counts': dict(price_source_counts),
        }

    try:
        if should_stop():
            return _stopped_result(sku)

        # 1. 打开页面
        print(f"  📦 正在处理 SKU: {sku}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        apply_page_zoom(page)
        move_mouse_to_safe_area(page)
        if is_jd_risk_handler_page(page):
            return _risk_verification_result(sku, page.url)
        if not is_expected_item_page(page, sku):
            return _invalid_sku_result(sku, page.url)

        # 2. 检查登录和下架状态，下架页的推荐商品价格不能作为主商品价格。
        if check_need_login(page):
            return {
                'sku': sku,
                'price': None,
                'all_prices': None,
                'spec_details': [],
                'screenshot_path': None,
                'status': 'need_login',
                'message': '登录态已失效，请登录后继续'
            }
        if check_product_unavailable(page):
            return _unavailable_result(sku)

        # 3. 等待价格区域就绪，避免每个 SKU 固定等待 1-3 秒
        wait_for_price_ready(page, timeout=5000)
        if is_jd_risk_handler_page(page):
            return _risk_verification_result(sku, page.url)
        if not is_expected_item_page(page, sku):
            return _invalid_sku_result(sku, page.url)
        if should_stop():
            return _stopped_result(sku)

        if check_need_login(page):
            return {
                'sku': sku,
                'price': None,
                'all_prices': None,
                'spec_details': [],
                'screenshot_path': None,
                'status': 'need_login',
                'message': '登录态已失效，请登录后继续'
            }

        # 4. 关闭弹窗
        close_popups(page)
        apply_page_zoom(page)
        move_mouse_to_safe_area(page)
        if check_product_unavailable(page):
            return _unavailable_result(sku)
        wait_for_price_ready(page, timeout=1000)

        all_spec_prices = []  # 收集所有规格的价格
        lowest_price = None
        lowest_spec_info = None
        screenshot_path = None  # 截图路径（发现低于门槛时立即截图）
        fast_threshold_scan = threshold_price is not None and price_type == 'current'
        scan_incomplete = False
        incomplete_reasons = []

        def mark_incomplete(reason):
            nonlocal scan_incomplete
            scan_incomplete = True
            incomplete_reasons.append(reason)

        def record_spec_price(series_name, spec_name, price, price_source=None):
            nonlocal lowest_price, lowest_spec_info
            if price is None:
                return False

            if price_source:
                price_source_counts[price_source] = price_source_counts.get(price_source, 0) + 1

            all_spec_prices.append({
                'series': series_name,
                'spec': spec_name,
                'price': price
            })

            if lowest_price is None or price < lowest_price:
                lowest_price = price
                lowest_spec_info = {'series': series_name, 'spec': spec_name}

            return threshold_price is not None and price < threshold_price

        # 5. 获取系列标签。若后续系列点击失败，至少保留当前 SKU 页面已展示的主价格。
        series_tabs = get_series_tabs(page)
        print(f"  🏷️  发现 {len(series_tabs)} 个系列标签")

        found_below_threshold = False
        if series_tabs:
            current_page_price = safe_extract_price(page, price_type)
            if current_page_price is not None:
                print(f"  💰 当前页面价格: ¥{current_page_price}")
                found_below_threshold = record_spec_price('当前页面', '当前SKU', current_page_price, 'dom')
                if found_below_threshold:
                    print(f"  🛑 当前页面已低于门槛价 ¥{threshold_price}，停止遍历该 SKU")
            else:
                mark_incomplete("当前页面价格未提取")

        if not series_tabs:
            spec_items = get_spec_items(page)
            spec_names = [spec_name for _, _, spec_name in spec_items]

            if spec_names:
                print(f"  ℹ️  该 SKU 无系列标签，发现 {len(spec_names)} 个规格选项")
                selected_spec_names = [
                    spec_name for _, spec_el, spec_name in spec_items if is_element_selected(spec_el)
                ]
                recorded_selected_spec_names = []
                for selected_spec_name in selected_spec_names:
                    price = safe_extract_price(page, price_type)
                    if price is None:
                        print(f"     🔘 当前规格: {selected_spec_name} - 价格未提取，稍后重试")
                        continue
                    print(f"     🔘 当前规格: {selected_spec_name} - ¥{price} (selected-dom)")
                    recorded_selected_spec_names.append(selected_spec_name)
                    if record_spec_price('默认', selected_spec_name, price, 'selected-dom'):
                        print(f"     🛑 发现低于门槛价 ¥{threshold_price}，停止遍历该 SKU")
                        break

                if not (
                    fast_threshold_scan
                    and lowest_price is not None
                    and threshold_price is not None
                    and lowest_price < threshold_price
                ):
                    for spec_idx, spec_name in enumerate(spec_names):
                        if should_stop():
                            return _stopped_result(sku)
                        if any(
                            normalize_option_text(spec_name) == normalize_option_text(selected_name)
                            for selected_name in recorded_selected_spec_names
                        ):
                            continue

                        print(f"     🔘 规格 [{spec_idx + 1}/{len(spec_names)}]: {spec_name}", end='')
                        try:
                            if fast_threshold_scan:
                                click_success, price, price_source = select_item_and_read_price_fast(
                                    page,
                                    get_spec_items,
                                    spec_name,
                                    price_type=price_type,
                                )
                                if not click_success:
                                    print(" - 点击失败，跳过")
                                    mark_incomplete(f"规格「{spec_name}」点击失败")
                                    continue
                            else:
                                previous_price_text = get_price_text(page)
                                click_success = click_item_by_text(page, get_spec_items, spec_name)
                                if click_success:
                                    wait_for_price_change(page, previous_price_text)
                                else:
                                    print(" - 点击失败，跳过")
                                    mark_incomplete(f"规格「{spec_name}」点击失败")
                                    continue
                                price = extract_price(page, price_type)
                                price_source = "dom"

                            if price is None:
                                print(f" - 价格未提取 ({price_source})")
                                mark_incomplete(f"规格「{spec_name}」价格未提取")
                                continue

                            is_below_threshold = record_spec_price('默认', spec_name, price, price_source)
                            print(f" - ¥{price} ({price_source})")

                            if is_below_threshold and screenshot_path is None and not fast_threshold_scan:
                                os.makedirs(screenshot_dir, exist_ok=True)
                                screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
                                page.evaluate('() => window.scrollTo(0, 0)')
                                time.sleep(0.3)
                                page.screenshot(path=screenshot_path, full_page=False)
                                print(f"     📸 截图已保存: {screenshot_path}（¥{price} < ¥{threshold_price}）")

                            if is_below_threshold:
                                print(f"     🛑 发现低于门槛价，停止遍历该 SKU")
                                break
                        except Exception as e:
                            print(f" - 提取失败: {e}")
                            mark_incomplete(f"规格「{spec_name}」提取失败")
            else:
                # 没有系列和规格，按单规格处理
                print(f"  ℹ️  该 SKU 无多系列，直接提取当前价格")
                try:
                    price = extract_price(page, price_type)
                    record_spec_price('默认', '默认规格', price, 'dom')

                    # 立即判断是否需要截图
                    if threshold_price is not None and price < threshold_price and not fast_threshold_scan:
                        os.makedirs(screenshot_dir, exist_ok=True)
                        screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
                        page.screenshot(path=screenshot_path, full_page=False)
                        print(f"  📸 截图已保存: {screenshot_path}（¥{price} < ¥{threshold_price}）")

                except Exception as e:
                    print(f"  ⚠️  提取价格失败: {e}")
                    mark_incomplete("默认规格价格未提取")
        else:
            # 遍历每个系列标签。只缓存文本，每次点击前重新取 DOM，避免京东重渲染后句柄串规格。
            series_names = [series_name for _, _, series_name in series_tabs]
            if found_below_threshold and fast_threshold_scan:
                series_names = []
            for series_idx, series_name in enumerate(series_names):
                if should_stop():
                    return _stopped_result(sku)
                print(f"\n  📂 系列 [{series_idx + 1}/{len(series_names)}]: {series_name}")

                # 点击系列标签（每个系列都点击，确保规格列表正确刷新）
                series_default_price = None
                series_price_source = None
                if fast_threshold_scan:
                    click_success, series_default_price, series_price_source = select_item_and_read_price_fast(
                        page,
                        get_series_tabs,
                        series_name,
                        price_type=price_type,
                    )
                else:
                    previous_price_text = get_price_text(page)
                    click_success = click_item_by_text(page, get_series_tabs, series_name)
                if click_success:
                    print(f"     已点击系列: {series_name}")
                    wait_for_spec_items_ready(page, timeout=1500)
                    if not fast_threshold_scan:
                        wait_for_price_change(page, previous_price_text)
                else:
                    print(f"     ⚠️ 点击系列失败，跳过")
                    mark_incomplete(f"系列「{series_name}」点击失败")
                    continue

                # 获取该系列下的所有规格（等待 DOM 更新）
                spec_items = get_spec_items(page)
                # 如果获取不到，再试一次
                if not spec_items:
                    wait_for_spec_items_ready(page, timeout=700)
                    spec_items = get_spec_items(page)
                spec_names = [spec_name for _, _, spec_name in spec_items]
                selected_spec_name = selected_item_text(spec_items)
                print(f"     发现 {len(spec_names)} 个规格选项")

                if not spec_names:
                    # 尝试直接提取当前价格
                    try:
                        if fast_threshold_scan and series_default_price is not None:
                            price = series_default_price
                            price_source = series_price_source
                        else:
                            price = extract_price(page, price_type)
                            price_source = "dom"

                        is_below_threshold = record_spec_price(series_name, '默认', price, price_source)
                        print(f"     💰 价格: ¥{price} ({price_source})")

                        # 立即判断是否需要截图
                        if is_below_threshold and screenshot_path is None and not fast_threshold_scan:
                            os.makedirs(screenshot_dir, exist_ok=True)
                            screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
                            page.screenshot(path=screenshot_path, full_page=False)
                            print(f"     📸 截图已保存: {screenshot_path}（¥{price} < ¥{threshold_price}）")

                    except Exception as e:
                        print(f"     ⚠️ 提取价格失败: {e}")
                        mark_incomplete(f"系列「{series_name}」默认价格未提取")
                    continue

                if fast_threshold_scan and selected_spec_name and series_default_price is not None:
                    print(
                        f"     🔘 当前规格: {selected_spec_name} - ¥{series_default_price}"
                        f" ({series_price_source})"
                    )
                    if record_spec_price(series_name, selected_spec_name, series_default_price, series_price_source):
                        print(f"     🛑 发现低于门槛价 ¥{threshold_price}，停止遍历该 SKU")
                        break

                # 遍历每个规格
                for spec_idx, spec_name in enumerate(spec_names):
                    if should_stop():
                        return _stopped_result(sku)

                    if (
                        fast_threshold_scan
                        and selected_spec_name
                        and series_default_price is not None
                        and normalize_option_text(spec_name) == normalize_option_text(selected_spec_name)
                    ):
                        continue

                    print(f"     🔘 规格 [{spec_idx + 1}/{len(spec_names)}]: {spec_name}", end='')

                    # 点击前重新获取当前 DOM 元素；京东切规格后会重渲染列表，旧 element 可能串到别的规格。
                    # 点击规格（每个规格都点击，确保价格正确刷新）
                    try:
                        if fast_threshold_scan:
                            click_success, price, price_source = select_item_and_read_price_fast(
                                page,
                                get_spec_items,
                                spec_name,
                                price_type=price_type,
                            )
                            if not click_success:
                                print(" - 点击失败，跳过")
                                mark_incomplete(f"规格「{spec_name}」点击失败")
                                continue
                        else:
                            previous_price_text = get_price_text(page)
                            click_success = click_item_by_text(page, get_spec_items, spec_name)
                            if click_success:
                                wait_for_price_change(page, previous_price_text)
                            else:
                                print(" - 点击失败，跳过")
                                mark_incomplete(f"规格「{spec_name}」点击失败")
                                continue
                            price = extract_price(page, price_type)
                            price_source = "dom"

                        if price is None:
                            print(f" - 价格未提取 ({price_source})")
                            mark_incomplete(f"规格「{spec_name}」价格未提取")
                            continue

                        is_below_threshold = record_spec_price(series_name, spec_name, price, price_source)
                        print(f" - ¥{price} ({price_source})")

                        # 立即判断是否需要截图（发现低于门槛价时立即截图，确保截图与价格一致）
                        if is_below_threshold and screenshot_path is None and not fast_threshold_scan:
                            os.makedirs(screenshot_dir, exist_ok=True)
                            screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
                            # 截图前滚动到页面顶部，确保价格在可视区域
                            page.evaluate('() => window.scrollTo(0, 0)')
                            time.sleep(0.3)
                            page.screenshot(path=screenshot_path, full_page=False)
                            print(f"     📸 截图已保存: {screenshot_path}（¥{price} < ¥{threshold_price}）")

                        if is_below_threshold:
                            print(f"     🛑 发现低于门槛价，停止遍历该 SKU")
                            # 跳出规格循环
                            break

                    except Exception as e:
                        print(f" - 提取失败: {e}")
                        mark_incomplete(f"规格「{spec_name}」提取失败")

                # 如果已经截图或快扫已发现低价，跳出系列循环
                if screenshot_path is not None or (
                    fast_threshold_scan
                    and lowest_price is not None
                    and threshold_price is not None
                    and lowest_price < threshold_price
                ):
                    break

        # 6. 输出汇总
        print(f"\n  📊 SKU {sku} 价格汇总:")
        print(f"     共检测 {len(all_spec_prices)} 个规格")
        if lowest_price is not None:
            print(f"     最低价格: ¥{lowest_price} ({lowest_spec_info['series']} / {lowest_spec_info['spec']})")
        else:
            print(f"     ⚠️ 未能提取到任何价格")

        # 7. 最终截图判断（兼容未设置门槛价的情况）
        if screenshot_path is None and lowest_price is not None:
            if threshold_price is None:
                # 未设置门槛价时，默认截图（兼容旧逻辑）
                os.makedirs(screenshot_dir, exist_ok=True)
                screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
                page.screenshot(path=screenshot_path, full_page=False)
                print(f"  📸 截图已保存: {screenshot_path}")
            elif lowest_price < threshold_price:
                print(f"  🚫 已发现低于门槛价 ¥{threshold_price}，快扫模式不截图")
            elif scan_incomplete:
                print(f"  ⚠️ 部分系列/规格未完成检测，需人工复核")
            else:
                # 设置了门槛价但没有低于门槛的
                print(f"  ⏭️  所有规格价格均 ≥ 门槛价 ¥{threshold_price}，跳过截图")

        if lowest_price is not None:
            found_low = threshold_price is not None and lowest_price < threshold_price
            if scan_incomplete and not found_low:
                status = 'partial'
                message = f"需人工复核: 部分系列/规格未完成检测；已检测 {len(all_spec_prices)} 个规格，最低 ¥{lowest_price}"
            else:
                status = 'success'
                message = f"检测 {len(all_spec_prices)} 个规格，最低 ¥{lowest_price}"
        else:
            status = 'error'
            message = "未能提取到任何价格"

        return {
            'sku': sku,
            'price': lowest_price,
            'all_prices': {'current': lowest_price},
            'spec_details': all_spec_prices,
            'screenshot_path': screenshot_path,
            'status': status,
            'message': message,
            'diagnostics': build_diagnostics(len(all_spec_prices)),
        }

    except Exception as e:
        print(f"  ❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'sku': sku,
            'price': None,
            'all_prices': None,
            'spec_details': [],
            'screenshot_path': None,
            'status': 'error',
            'message': str(e),
            'diagnostics': build_diagnostics(),
        }


# 为了保持向后兼容，保留旧的 crawl_sku 函数
def crawl_sku(page, sku, screenshot_dir, delay_min=1, delay_max=3, price_type='current',
              threshold_price=None, should_stop=None):
    """
    兼容旧接口，实际调用新版多系列遍历逻辑
    """
    return crawl_sku_with_series(
        page=page,
        sku=sku,
        screenshot_dir=screenshot_dir,
        delay_min=delay_min,
        delay_max=delay_max,
        price_type=price_type,
        threshold_price=threshold_price,
        should_stop=should_stop
    )
