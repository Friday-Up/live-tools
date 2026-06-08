"""
京东价格爬取模块
负责打开 SKU 页面、提取价格、截图、关闭弹窗
支持多种价格类型抓取
"""

import os
import time
import random


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
        'current': [
            ".product-price--value",
            ".p-price .price",
            ".price-now .price",
            "[class*='price'] [class*='value']"
        ],
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
                # 提取数字部分
                import re
                numbers = re.findall(r'\d+\.?\d*', price_text)
                if numbers:
                    return float(numbers[0])
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
        import re
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

    # 检查页面标题是否包含登录
    if "登录" in page.title():
        return True

    return False


def crawl_sku(page, sku, screenshot_dir, delay_min=1, delay_max=3, price_type='current'):
    """
    爬取单个 SKU 的价格和截图

    Args:
        page: Playwright page 对象
        sku: SKU 编号
        screenshot_dir: 截图保存目录
        delay_min: 最小延迟（秒）
        delay_max: 最大延迟（秒）
        price_type: 抓取的价格类型 ('current', 'origin', 'plus', 'deal', 'all')

    Returns:
        dict: {
            'sku': sku,
            'price': float or None,        # 主价格（用于门槛判定）
            'all_prices': dict or None,    # 所有价格信息（price_type='all'时）
            'screenshot_path': str or None,
            'status': str,                 # 'success' / 'need_login' / 'error'
            'message': str
        }
    """
    url = f"https://item.jd.com/{sku}.html"

    try:
        # 1. 打开页面
        print(f"  📦 正在处理 SKU: {sku}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # 2. 随机延迟，模拟人工操作
        delay = random.uniform(delay_min, delay_max)
        time.sleep(delay)

        # 3. 检查是否需要登录
        if check_need_login(page):
            return {
                'sku': sku,
                'price': None,
                'all_prices': None,
                'screenshot_path': None,
                'status': 'need_login',
                'message': '登录态已失效，请删除 jd_auth.json 后重新运行并登录'
            }

        # 4. 关闭弹窗
        close_popups(page)
        time.sleep(0.5)

        # 5. 提取价格
        if price_type == 'all':
            all_prices = extract_all_prices(page)
            price = all_prices.get('current')  # 使用当前售价作为门槛判定依据
            print(f"  💰 当前售价: ¥{price}")
            if all_prices.get('plus'):
                print(f"     Plus价: ¥{all_prices['plus']}")
            if all_prices.get('deal'):
                print(f"     到手价: ¥{all_prices['deal']}")
        else:
            all_prices = None
            price = extract_price(page, price_type)
            print(f"  💰 价格: ¥{price}")

        # 6. 截图（仅截取浏览器可视区域）
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
        page.screenshot(path=screenshot_path, full_page=False)
        print(f"  📸 截图已保存: {screenshot_path}")

        return {
            'sku': sku,
            'price': price,
            'all_prices': all_prices,
            'screenshot_path': screenshot_path,
            'status': 'success',
            'message': '抓取成功'
        }

    except Exception as e:
        print(f"  ❌ 处理失败: {e}")
        return {
            'sku': sku,
            'price': None,
            'all_prices': None,
            'screenshot_path': None,
            'status': 'error',
            'message': str(e)
        }
