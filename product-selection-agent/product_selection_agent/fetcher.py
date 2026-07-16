"""四来源抓取适配器。

京东活动页虽然都长得像 Babel 页面，但真实数据结构不同：

* 国家补贴：类目 Tab + qryJediPcBabelFloors.goodsList
* 黑色星期五：window.__react_data__ 中的 flexData（当前无业务类目 Tab）
* 排行榜：类目 Tab -> 榜单卡片 -> 榜单详情 productList
* 京东特价：类目 Tab + queryPcBabelFeeds.flexData

本模块只负责把不同来源规整成 parser 能消费的“类 goodsList”记录，不做
跨来源排序，也不会把一个来源的延迟响应误标成另一个来源。
"""
from __future__ import annotations

import os
import re
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from . import config
from .runtime import RunContext


def _walk_dicts(value) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _extract_goods_from_body(body: dict) -> list[dict]:
    """提取 qryJediPcBabelFloors 的所有 goodsList。"""
    goods: list[dict] = []
    floor_response = body.get("floorResponse") or {}
    for floor in floor_response.values():
        if not isinstance(floor, dict):
            continue
        feeds = (floor.get("providerData") or {}).get("feeds") or {}
        floor_goods = feeds.get("goodsList") or []
        if isinstance(floor_goods, list):
            goods.extend(g for g in floor_goods if isinstance(g, dict))
    return goods


def _sku_from_group(group: dict) -> str:
    jump = ((group.get("clickEvent") or {}).get("jump") or {})
    sku = (jump.get("params") or {}).get("skuId")
    if sku:
        return str(sku)
    add_cart = (((group.get("flexData") or {}).get("addCart") or {}).get("addCart") or {})
    sku = add_cart.get("skuId")
    if sku:
        return str(sku)
    material_id = str(group.get("materialId") or "")
    return material_id if material_id.isdigit() else ""


def _scalar(fd: dict, preferred: tuple[str, ...], key_predicate=None):
    for key in preferred:
        value = fd.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return value
    if key_predicate:
        for key, value in fd.items():
            if key_predicate(key.lower()) and isinstance(value, (str, int, float)) and str(value).strip():
                return value
    return ""


def _normalise_image(url: str) -> str:
    url = str(url or "")
    return "https:" + url if url.startswith("//") else url


def _flex_group_to_goods(group: dict, tab_name: str, source_rank: int) -> dict | None:
    """把 Babel flexData 商品卡转换成通用原始记录。"""
    fd = group.get("flexData") or {}
    sku = _sku_from_group(group)
    name = _scalar(
        fd,
        ("wname", "name", "name2", "name4", "skuName", "goodsName"),
        lambda key: key.startswith("name"),
    )
    if not sku or not name:
        return None

    price = _scalar(
        fd,
        ("displayPrice", "PriceSuperPurchasePrice6", "PriceSuperPurchasePrice1", "purchasePrice", "jdPrice"),
        lambda key: "price" in key and "pic" not in key and "image" not in key,
    )
    image = _scalar(
        fd,
        ("imageUrl", "picUrl0", "clarityPic0", "img"),
        lambda key: ("pic" in key or "image" in key) and "price" not in key,
    )
    sales_text = _scalar(
        fd,
        ("saleQttyWholeDesc1", "salesText", "saleAmountText"),
        lambda key: "sale" in key and ("desc" in key or "qty" in key or "amount" in key),
    )
    good_rate = _scalar(fd, ("goodRate0", "goodRate"), lambda key: "goodrate" in key)

    points: list[str] = []
    point_markers = ("tag", "sellpoint", "promo", "compensate", "tsfw", "goodrate")
    for key, value in fd.items():
        if not isinstance(value, (str, int, float)):
            continue
        lower_key = key.lower()
        text = str(value).strip()
        if text and any(marker in lower_key for marker in point_markers) and not text.startswith("//"):
            points.append(text)

    benefit = []
    if sales_text:
        benefit.append({"subType": "SALE_AMOUNT", "benifitText": str(sales_text)})

    return {
        "skuId": sku,
        "wname": str(name),
        "displayPrice": price,
        "imageUrl": _normalise_image(str(image)),
        "tab_category": tab_name,
        "takeoutBenefitList": benefit,
        "newThirdBenefitList": [{"benifitText": p} for p in dict.fromkeys(points)],
        "source_rank": source_rank,
        "good_rate": str(good_rate or ""),
        "category_source": "page_tab" if tab_name else "unavailable",
        "raw_format": "babel_flex",
    }


def _extract_flex_goods(body: dict, tab_name: str = "") -> list[dict]:
    goods: list[dict] = []
    rank = 0
    for node in _walk_dicts(body):
        if not isinstance(node.get("flexData"), dict):
            continue
        item = _flex_group_to_goods(node, tab_name, rank + 1)
        if item:
            rank += 1
            item["source_rank"] = rank
            goods.append(item)
    return _dedup_goods(goods)


def _dedup_goods(goods: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for item in goods:
        jump = item.get("jump") or {}
        sku = str(
            item.get("skuId")
            or (jump.get("params") or {}).get("skuId")
            or jump.get("srv")
            or ""
        )
        tab = str(item.get("tab_category") or "")
        if not sku or (tab, sku) in seen:
            continue
        seen.add((tab, sku))
        out.append(item)
    return out


def _wait_for_quiet(bucket: list, timeout: float | None = None) -> None:
    """等待响应列表停止增长；比每个 Tab 固定 sleep 更快也更稳定。"""
    timeout = timeout or config.TAB_TIMEOUT_SECONDS
    deadline = time.monotonic() + timeout
    last_len = len(bucket)
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(0.2)
        current = len(bucket)
        if current != last_len:
            last_len = current
            last_change = time.monotonic()
        if current and time.monotonic() - last_change >= config.TAB_QUIET_SECONDS:
            return


def _tab_names(page: Page, selector: str) -> list[str]:
    locator = page.locator(selector)
    names: list[str] = []
    for index in range(locator.count()):
        try:
            names.append(" ".join(locator.nth(index).inner_text(timeout=1500).split()))
        except Exception:
            names.append("")
    return names


def _scroll_feed(
    page: Page,
    bucket: list[dict] | None = None,
    max_candidates: int | None = None,
) -> None:
    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    for _ in range(config.SCROLL_TIMES):
        try:
            page.mouse.wheel(0, 2400)
        except Exception:
            break
        time.sleep(config.SCROLL_INTERVAL_SECONDS)
        if bucket is not None and max_candidates:
            if len(_dedup_goods(bucket)) >= max_candidates:
                break


def _limit_candidates(goods: list[dict]) -> list[dict]:
    return _dedup_goods(goods)[: config.MAX_CANDIDATES_PER_CATEGORY]


def _fetch_babel_tabs(page: Page, source: dict, context: RunContext) -> list[dict]:
    bucket: list[dict] = []

    def on_response(response):
        if source["api_keyword"] not in response.url:
            return
        try:
            bucket.extend(_extract_goods_from_body(response.json()))
        except Exception:
            return

    page.on("response", on_response)
    try:
        page.goto(source["url"], wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
        time.sleep(config.PAGE_READY_SECONDS)
        names = _tab_names(page, source["tab_selector"])
        if not names:
            raise RuntimeError("未发现国家补贴类目 Tab")
        expected_categories = {name for name in names if name and name not in config.SKIP_TABS}
        context.log(f"[fetch] {source['name']} 发现 {len(names)} 个 Tab: {names}")
        collected: list[dict] = []
        for index, name in enumerate(names):
            context.check_cancelled()
            if not name or name in config.SKIP_TABS:
                continue
            time.sleep(0.4)  # 先让上一个 Tab 的尾部响应自然结束
            bucket.clear()
            tab = page.locator(source["tab_selector"]).nth(index)
            try:
                tab.scroll_into_view_if_needed(timeout=3000)
                tab.click(timeout=5000)
                time.sleep(config.TAB_SETTLE_SECONDS)
                # 丢弃点击瞬间到达的旧 Tab 尾部响应；当前 Tab 的 feed 会在随后
                # 从页顶滚动时重新触发。
                bucket.clear()
                _scroll_feed(page, bucket, config.MAX_CANDIDATES_PER_CATEGORY)
                _wait_for_quiet(bucket)
            except Exception as exc:
                context.log(f"[fetch]   {source['name']}/{name} 失败: {exc}")
                continue
            tab_goods = _limit_candidates([
                {**item, "tab_category": name, "category_source": "page_tab", "source_rank": pos}
                for pos, item in enumerate(bucket, 1)
            ])
            collected.extend(tab_goods)
            context.log(
                f"[fetch]   {source['name']}/{name}: 候选 {len(tab_goods)} 个"
                f"（上限 {config.MAX_CANDIDATES_PER_CATEGORY}）"
            )
        actual_categories = {str(item.get("tab_category") or "") for item in collected}
        missing_categories = sorted(expected_categories - actual_categories)
        if missing_categories:
            raise RuntimeError(f"以下类目未抓到商品: {', '.join(missing_categories)}")
        return _dedup_goods(collected)
    finally:
        page.remove_listener("response", on_response)


def _fetch_embedded_flex(page: Page, source: dict, context: RunContext) -> list[dict]:
    context.check_cancelled()
    page.goto(source["url"], wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
    time.sleep(config.PAGE_READY_SECONDS)
    react_data = page.evaluate("window.__react_data__ || null")
    if not isinstance(react_data, dict):
        raise RuntimeError("页面不存在 window.__react_data__")
    category = source.get("fallback_category", "未分类")
    goods = _limit_candidates(_extract_flex_goods(react_data, category))
    for item in goods:
        item["category_source"] = "source_fallback_no_tab"
        item["data_quality"] = "页面未提供销量与类目字段，保留页面原始排序"
    context.log(f"[fetch] {source['name']}/{category}: 候选 {len(goods)} 个")
    return goods


def _fetch_flex_feed_tabs(page: Page, source: dict, context: RunContext) -> list[dict]:
    bucket: list[dict] = []

    def on_response(response):
        if source["api_keyword"] not in response.url:
            return
        try:
            bucket.extend(_extract_flex_goods(response.json()))
        except Exception:
            return

    page.on("response", on_response)
    try:
        page.goto(source["url"], wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
        time.sleep(config.PAGE_READY_SECONDS)
        names = _tab_names(page, source["tab_selector"])
        if not names:
            raise RuntimeError("未发现京东特价类目 Tab")
        expected_categories = {name for name in names if name and name not in config.SKIP_TABS}
        context.log(f"[fetch] {source['name']} 发现 {len(names)} 个 Tab: {names}")
        collected: list[dict] = []
        for index, name in enumerate(names):
            context.check_cancelled()
            if not name or name in config.SKIP_TABS:
                continue
            time.sleep(0.4)
            bucket.clear()
            tab = page.locator(source["tab_selector"]).nth(index)
            try:
                tab.scroll_into_view_if_needed(timeout=3000)
                tab.click(timeout=5000)
                time.sleep(config.TAB_SETTLE_SECONDS)
                bucket.clear()
                _scroll_feed(page, bucket, config.MAX_CANDIDATES_PER_CATEGORY)
                _wait_for_quiet(bucket)
            except Exception as exc:
                context.log(f"[fetch]   {source['name']}/{name} 失败: {exc}")
                continue
            tab_goods = _limit_candidates([
                {**item, "tab_category": name, "category_source": "page_tab", "source_rank": pos}
                for pos, item in enumerate(bucket, 1)
            ])
            collected.extend(tab_goods)
            context.log(
                f"[fetch]   {source['name']}/{name}: 候选 {len(tab_goods)} 个"
                f"（上限 {config.MAX_CANDIDATES_PER_CATEGORY}）"
            )
        actual_categories = {str(item.get("tab_category") or "") for item in collected}
        missing_categories = sorted(expected_categories - actual_categories)
        if missing_categories:
            raise RuntimeError(f"以下类目未抓到商品: {', '.join(missing_categories)}")
        return _dedup_goods(collected)
    finally:
        page.remove_listener("response", on_response)


def _rank_product_to_goods(product: dict, tab_name: str, board_name: str, board_url: str) -> dict:
    price = product.get("price") or {}
    sales_tags = product.get("skuBenefitTags") or []
    sales_text = ""
    for tag in sales_tags:
        text = str(tag.get("text") or "")
        if "售" in text:
            sales_text = text
            break

    points: list[str] = []
    for tag in product.get("skuInfoTags") or []:
        ext = tag.get("ext") or {}
        points.extend(str(p) for p in ext.get("sellPoints") or [] if p)
        if tag.get("text"):
            points.append(str(tag["text"]))
    for key in ("subPriceTags", "skuServiceIconList", "intelligentSellingPoints"):
        for tag in product.get(key) or []:
            text = tag.get("text") or tag.get("name")
            if text:
                points.append(str(text))

    return {
        "skuId": str(product.get("skuId") or ""),
        "wname": product.get("name") or "",
        "displayPrice": price.get("purchasePrice") or price.get("jdPrice") or "",
        "jdPrice": price.get("jdPrice") or "",
        "linePrice": price.get("jdPrice") or "",
        "imageUrl": _normalise_image(product.get("img") or ""),
        "tab_category": tab_name,
        "category_id": str(product.get("threeCategory") or ""),
        "shopId": str(product.get("storeId") or ""),
        "jxSelf": str(product.get("zyTag") or "") == "1",
        "takeoutBenefitList": [{"subType": "SALE_AMOUNT", "benifitText": sales_text}] if sales_text else [],
        "newThirdBenefitList": [{"benifitText": p} for p in dict.fromkeys(points)],
        "source_rank": int(product.get("rankNum") or 999999),
        "rank_board": board_name,
        "rank_board_url": board_url,
        "stock_status": product.get("stockStatus"),
        "category_source": "page_tab_and_rank_detail",
        "raw_format": "rank_product",
    }


def _rank_detail_products(detail_page: Page, tab_name: str, board_name: str) -> list[dict]:
    time.sleep(config.PAGE_READY_SECONDS)
    react_data = detail_page.evaluate("window.__react_data__ || null")
    if not isinstance(react_data, dict):
        raise RuntimeError("榜单详情缺少 window.__react_data__")
    product_lists: list[list] = []
    for node in _walk_dicts(react_data):
        product_list = ((node.get("providerData") or {}).get("result") or {}).get("productList")
        if isinstance(product_list, list) and product_list:
            product_lists.append(product_list)
    if not product_lists:
        raise RuntimeError("榜单详情未找到 productList")
    products = max(product_lists, key=len)
    products = sorted(products, key=lambda item: int(item.get("rankNum") or 999999))
    goods: list[dict] = []
    seen_skus: set[str] = set()
    for product in products:
        sku = str(product.get("skuId") or "")
        if not sku or not product.get("name") or sku in seen_skus:
            continue
        seen_skus.add(sku)
        goods.append(_rank_product_to_goods(product, tab_name, board_name, detail_page.url))
        if len(goods) >= config.TOP_N_PER_CATEGORY:
            break
    return goods


def _fetch_rank_drilldown(page: Page, source: dict, context: RunContext) -> list[dict]:
    page.goto(source["url"], wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
    time.sleep(config.PAGE_READY_SECONDS)
    names = _tab_names(page, source["tab_selector"])
    if not names:
        raise RuntimeError("未发现排行榜类目 Tab")
    expected_categories = {name for name in names if name and name not in config.SKIP_TABS}
    context.log(f"[fetch] {source['name']} 发现 {len(names)} 个 Tab: {names}")
    collected: list[dict] = []

    for index, name in enumerate(names):
        context.check_cancelled()
        if not name or name in config.SKIP_TABS:
            continue
        try:
            tab = page.locator(source["tab_selector"]).nth(index)
            tab.scroll_into_view_if_needed(timeout=3000)
            tab.click(timeout=5000)
            time.sleep(config.RANK_TAB_RENDER_SECONDS)
            rank_root = page.locator(".rankFlex:visible").first
            titles = [
                " ".join(text.split())
                for text in rank_root.locator("span").all_inner_texts()
                if " ".join(text.split()).endswith("榜")
            ]
            if not titles:
                raise RuntimeError("当前类目没有可见榜单卡片")
            board_name = titles[0]
            card = rank_root.get_by_text(board_name, exact=True).first.locator("xpath=../..")
            with page.context.expect_page(timeout=7000) as popup:
                card.locator("img").first.click(timeout=5000)
            detail_page = popup.value
            try:
                detail_page.wait_for_load_state("domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
                goods = _rank_detail_products(detail_page, name, board_name)
            finally:
                detail_page.close()
            collected.extend(goods)
            context.log(f"[fetch]   {source['name']}/{name}/{board_name}: {len(goods)} 个")
        except (PlaywrightTimeoutError, Exception) as exc:
            context.log(f"[fetch]   {source['name']}/{name} 下钻失败: {exc}")
            continue
    actual_categories = {str(item.get("tab_category") or "") for item in collected}
    missing_categories = sorted(expected_categories - actual_categories)
    if missing_categories:
        raise RuntimeError(f"以下类目下钻失败: {', '.join(missing_categories)}")
    return _dedup_goods(collected)


ADAPTERS = {
    "babel_tabs": _fetch_babel_tabs,
    "embedded_flex": _fetch_embedded_flex,
    "rank_drilldown": _fetch_rank_drilldown,
    "flex_feed_tabs": _fetch_flex_feed_tabs,
}


def fetch_source(page: Page, source: dict, context: RunContext | None = None) -> list[dict]:
    context = context or RunContext()
    context.check_cancelled()
    adapter_name = source.get("adapter")
    adapter = ADAPTERS.get(adapter_name)
    if not adapter:
        raise ValueError(f"未知来源适配器: {adapter_name}")
    context.log(f"[fetch] {source['name']} -> {adapter_name}")
    return adapter(page, source, context)


def _fetch_source_isolated(
    source: dict,
    headless: bool,
    auth_path: str,
    context: RunContext | None = None,
) -> list[dict]:
    """在线程内部创建并使用 Playwright，避免同步 Page 跨线程共享。"""
    run_context = context or RunContext()
    run_context.check_cancelled()
    context_options = {"viewport": {"width": 1440, "height": 900}}
    if os.path.exists(auth_path):
        context_options["storage_state"] = auth_path

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        browser_context = browser.new_context(**context_options)
        page = browser_context.new_page()
        try:
            return fetch_source(page, source, run_context)
        finally:
            page.close()
            browser_context.close()
            browser.close()


def fetch_all(
    headless: bool = False,
    allow_partial: bool = False,
    context: RunContext | None = None,
) -> dict:
    """抓取全部来源；默认任一来源为空就失败，避免静默生成残缺报表。"""
    context = context or RunContext()
    context.check_cancelled()
    auth_path = os.path.abspath(config.AUTH_PATH)
    if os.path.exists(auth_path):
        context.log(f"[auth] 使用登录态: {auth_path}")
    else:
        context.log(f"[auth] 未找到登录态，使用匿名访问: {auth_path}")

    worker_count = min(config.FETCH_WORKERS, len(config.SOURCES))
    context.log(f"[fetch] 启用 {worker_count} 个独立浏览器并发（按来源隔离）")
    completed: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="selection-fetch") as executor:
        future_sources = {
            executor.submit(_fetch_source_isolated, source, headless, auth_path, context): source
            for source in config.SOURCES
        }
        for future in as_completed(future_sources):
            context.check_cancelled()
            source = future_sources[future]
            error = ""
            try:
                goods = future.result()
            except Exception as exc:
                goods = []
                error = f"{type(exc).__name__}: {exc}"
                context.log(f"[fetch] {source['name']} 失败: {error}")
            categories = sorted({str(g.get("tab_category") or "未分类") for g in goods})
            completed[source["key"]] = {
                "name": source["name"],
                "adapter": source["adapter"],
                "status": "ok" if goods else "empty",
                "error": error,
                "categories": categories,
                "goods": goods,
            }

    # 并发完成顺序不稳定，按配置顺序组织输出，保证 JSON/Excel 可复现。
    result = {source["key"]: completed[source["key"]] for source in config.SOURCES}

    empty_sources = [payload["name"] for payload in result.values() if not payload["goods"]]
    if empty_sources and not allow_partial:
        raise RuntimeError(f"以下来源没有抓到商品，拒绝生成残缺报表: {', '.join(empty_sources)}")
    return result
