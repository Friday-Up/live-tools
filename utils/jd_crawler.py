"""
京东价格爬取模块
负责打开 SKU 页面、提取价格、截图、关闭弹窗
支持多种价格类型抓取
支持多系列多规格遍历（新版京东商品页）
"""

import os
import time
import random
import re


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
        # 策略5: 规格分组标签
        '.specification-group-label',
    ]

    for strategy in strategies:
        try:
            elements = page.locator(strategy).all()
            if elements:
                tabs = []
                for i, el in enumerate(elements):
                    text = el.text_content().strip()
                    # 过滤掉无效标签（如评价、详情等导航标签）
                    if text and len(text) < 20 and text not in ['买家评价', '商品详情', '售后保障', '推荐']:
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
    strategies = [
        # 策略1: 新版京东规格项（如：【原生高钙4.0g蛋白】200mL*24盒）
        '.specification-item-sku',
        # 策略2: 旧版京东
        '.p-choose-item',
        # 策略3: 通用规格
        '[class*="sku-item"]',
        # 策略4: 选择项
        '.choose-item',
    ]

    for strategy in strategies:
        try:
            elements = page.locator(strategy).all()
            if elements:
                items = []
                for i, el in enumerate(elements):
                    # 尝试获取文本（可能是图片+文字结构）
                    text_el = el.locator('[class*="text"], .name, .title').first
                    if text_el.count() > 0:
                        text = text_el.text_content().strip()
                    else:
                        text = el.text_content().strip()
                    # 过滤无货项
                    if text and '无货' not in text and '缺货' not in text:
                        items.append((i, el, text))
                if items:
                    return items
        except:
            continue

    return []


def click_element_safely(page, element, timeout=5000):
    """
    安全点击元素，处理可能的拦截问题
    """
    try:
        # 先尝试普通点击
        element.click(timeout=timeout)
        return True
    except Exception as e:
        # 如果被拦截，尝试通过 JS 点击
        try:
            element.evaluate('el => el.click()')
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

    try:
        if should_stop():
            return _stopped_result(sku)

        # 1. 打开页面
        print(f"  📦 正在处理 SKU: {sku}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # 2. 随机延迟，模拟人工操作
        delay = random.uniform(delay_min, delay_max)
        time.sleep(delay)
        if should_stop():
            return _stopped_result(sku)

        # 3. 检查是否需要登录
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
        time.sleep(0.5)

        # 5. 获取系列标签
        series_tabs = get_series_tabs(page)
        print(f"  🏷️  发现 {len(series_tabs)} 个系列标签")

        all_spec_prices = []  # 收集所有规格的价格
        lowest_price = None
        lowest_spec_info = None
        screenshot_path = None  # 截图路径（发现低于门槛时立即截图）

        if not series_tabs:
            # 没有系列标签，按单规格处理
            print(f"  ℹ️  该 SKU 无多系列，直接提取当前价格")
            try:
                price = extract_price(page, price_type)
                all_spec_prices.append({
                    'series': '默认',
                    'spec': '默认规格',
                    'price': price
                })
                lowest_price = price
                lowest_spec_info = {'series': '默认', 'spec': '默认规格'}

                # 立即判断是否需要截图
                if threshold_price is not None and price < threshold_price:
                    os.makedirs(screenshot_dir, exist_ok=True)
                    screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
                    page.screenshot(path=screenshot_path, full_page=False)
                    print(f"  📸 截图已保存: {screenshot_path}（¥{price} < ¥{threshold_price}）")

            except Exception as e:
                print(f"  ⚠️  提取价格失败: {e}")
        else:
            # 遍历每个系列标签
            for series_idx, series_el, series_name in series_tabs:
                if should_stop():
                    return _stopped_result(sku)
                print(f"\n  📂 系列 [{series_idx + 1}/{len(series_tabs)}]: {series_name}")

                # 点击系列标签（每个系列都点击，确保规格列表正确刷新）
                click_success = click_element_safely(page, series_el)
                if click_success:
                    print(f"     已点击系列: {series_name}")
                    time.sleep(1.5)  # 等待规格列表更新
                else:
                    print(f"     ⚠️ 点击系列失败，跳过")
                    continue

                # 获取该系列下的所有规格（等待 DOM 更新）
                spec_items = get_spec_items(page)
                # 如果获取不到，再试一次
                if not spec_items:
                    time.sleep(1)
                    spec_items = get_spec_items(page)
                print(f"     发现 {len(spec_items)} 个规格选项")

                if not spec_items:
                    # 尝试直接提取当前价格
                    try:
                        price = extract_price(page, price_type)
                        all_spec_prices.append({
                            'series': series_name,
                            'spec': '默认',
                            'price': price
                        })
                        if lowest_price is None or price < lowest_price:
                            lowest_price = price
                            lowest_spec_info = {'series': series_name, 'spec': '默认'}
                        print(f"     💰 价格: ¥{price}")

                        # 立即判断是否需要截图
                        if threshold_price is not None and price < threshold_price and screenshot_path is None:
                            os.makedirs(screenshot_dir, exist_ok=True)
                            screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
                            page.screenshot(path=screenshot_path, full_page=False)
                            print(f"     📸 截图已保存: {screenshot_path}（¥{price} < ¥{threshold_price}）")

                    except Exception as e:
                        print(f"     ⚠️ 提取价格失败: {e}")
                    continue

                # 遍历每个规格
                for spec_idx, spec_el, spec_name in spec_items:
                    if should_stop():
                        return _stopped_result(sku)
                    print(f"     🔘 规格 [{spec_idx + 1}/{len(spec_items)}]: {spec_name}", end='')

                    # 点击规格（每个规格都点击，确保价格正确刷新）
                    click_success = click_element_safely(page, spec_el)
                    if click_success:
                        time.sleep(0.8)  # 等待价格更新
                    else:
                        print(" - 点击失败，跳过")
                        continue

                    # 提取价格
                    try:
                        price = extract_price(page, price_type)
                        all_spec_prices.append({
                            'series': series_name,
                            'spec': spec_name,
                            'price': price
                        })

                        # 更新最低价
                        if lowest_price is None or price < lowest_price:
                            lowest_price = price
                            lowest_spec_info = {'series': series_name, 'spec': spec_name}

                        print(f" - ¥{price}")

                        # 立即判断是否需要截图（发现低于门槛价时立即截图，确保截图与价格一致）
                        if threshold_price is not None and price < threshold_price and screenshot_path is None:
                            os.makedirs(screenshot_dir, exist_ok=True)
                            screenshot_path = os.path.join(screenshot_dir, f"{sku}.png")
                            # 截图前滚动到页面顶部，确保价格在可视区域
                            page.evaluate('() => window.scrollTo(0, 0)')
                            time.sleep(0.3)
                            page.screenshot(path=screenshot_path, full_page=False)
                            print(f"     📸 截图已保存: {screenshot_path}（¥{price} < ¥{threshold_price}）")
                            print(f"     🛑 发现低于门槛价，停止遍历该 SKU")
                            # 跳出规格循环
                            break

                        # 随机延迟，模拟人工
                        time.sleep(random.uniform(0.3, 0.8))

                    except Exception as e:
                        print(f" - 提取失败: {e}")

                # 如果已经截图，跳出系列循环
                if screenshot_path is not None:
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
            else:
                # 设置了门槛价但没有低于门槛的
                print(f"  ⏭️  所有规格价格均 ≥ 门槛价 ¥{threshold_price}，跳过截图")

        return {
            'sku': sku,
            'price': lowest_price,
            'all_prices': {'current': lowest_price},
            'spec_details': all_spec_prices,
            'screenshot_path': screenshot_path,
            'status': 'success',
            'message': f"检测 {len(all_spec_prices)} 个规格，最低 ¥{lowest_price}"
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
            'message': str(e)
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
