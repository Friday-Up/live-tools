"""把四种来源适配器的类 goodsList 记录解析成统一商品结构。"""
from __future__ import annotations

import re


def _to_float(value, default=0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def _to_int(value, default=0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError):
        return default


def parse_quantity_text(text: str) -> int:
    """解析“30日售出1万件 / 5000+ / 2.3万人买过”等展示口径。"""
    text = str(text or "").replace(",", "")
    matches = list(re.finditer(r"(\d+(?:\.\d+)?)\s*([万亿]?)", text))
    if not matches:
        return 0
    # 展示文案常带时间窗，如“30日售出1万件”；销量是最后一个数字而非 30。
    match = matches[-1]
    value = float(match.group(1))
    multiplier = {"": 1, "万": 10_000, "亿": 100_000_000}[match.group(2)]
    return int(value * multiplier)


def _extract_sales(goods: dict) -> tuple[int, str]:
    for benefit in goods.get("takeoutBenefitList") or []:
        subtype = str(benefit.get("subType") or "")
        if subtype in ("SALE_AMOUNT", "orderNum") or benefit.get("type") == "orderNum":
            text = str(benefit.get("benifitText") or benefit.get("benefitText") or "")
            raw = benefit.get("realBenefitValue")
            return (_to_int(raw) if raw is not None else parse_quantity_text(text), text)
    return 0, ""


def _extract_selling_points(goods: dict) -> str:
    points: list[str] = []
    for key in ("newThirdBenefitList", "firstBenefitList"):
        for benefit in goods.get(key) or []:
            text = benefit.get("benifitText") or benefit.get("benefitText") or benefit.get("prefix") or ""
            values = benefit.get("benefitValues") or []
            if text:
                points.append(str(text) + ("".join(str(value) for value in values) if values else ""))
    return " | ".join(dict.fromkeys(point for point in points if point))


def _extract_sku_id(goods: dict) -> str:
    sku = goods.get("skuId")
    if sku:
        return str(sku)
    jump = goods.get("jump") or {}
    params = jump.get("params") or {}
    return str(params.get("skuId") or jump.get("srv") or "")


def _parse_good_rate(value: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", str(value or ""))
    return float(match.group(1)) / 100 if match else 0.0


def parse_goods(goods: dict, source_key: str, source_name: str) -> dict:
    sales_num, sales_text = _extract_sales(goods)
    sku_id = _extract_sku_id(goods)
    display_price = _to_float(goods.get("displayPrice") or goods.get("purchasePrice"))
    jd_price = _to_float(goods.get("jdPrice"))
    line_price = _to_float(goods.get("linePrice"))
    return {
        "source_key": source_key,
        "source_name": source_name,
        "sku_id": sku_id,
        "tab_category": str(goods.get("tab_category") or ""),
        "name": str(goods.get("wname") or goods.get("name") or ""),
        "display_price": display_price,
        "jd_price": jd_price,
        "line_price": line_price,
        "sales_num": sales_num,
        "sales_text": sales_text,
        "category_id1": str(goods.get("category_id1") or ""),
        "category_id2": str(goods.get("category_id2") or ""),
        "category_id3": str(goods.get("category_id") or ""),
        "shop_name": str(goods.get("shopName") or ""),
        "shop_id": str(goods.get("shopId") or ""),
        "jx_self": bool(goods.get("jxSelf")),
        "selling_points": _extract_selling_points(goods),
        "image_url": str(goods.get("imageUrl") or ""),
        "url": f"https://item.jd.com/{sku_id}.html" if sku_id else "",
        "source_rank": _to_int(goods.get("source_rank"), 999999),
        "rank_board": str(goods.get("rank_board") or ""),
        "rank_board_url": str(goods.get("rank_board_url") or ""),
        "stock_status": goods.get("stock_status"),
        "good_rate": _parse_good_rate(goods.get("good_rate") or ""),
        "category_source": str(goods.get("category_source") or "unknown"),
        "data_quality": str(goods.get("data_quality") or ""),
        "raw_format": str(goods.get("raw_format") or "goods_list"),
    }


def parse_all(raw_data: dict) -> list[dict]:
    items: list[dict] = []
    for source_key, payload in raw_data.items():
        source_name = payload.get("name", source_key)
        for goods in payload.get("goods", []):
            item = parse_goods(goods, source_key, source_name)
            if item["sku_id"] and item["name"]:
                items.append(item)
    return items
