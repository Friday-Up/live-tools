"""按「来源 × 页面类目」分组，每组取前 N。"""
from collections import defaultdict

from . import config

def _discount_ratio(item: dict) -> float:
    """折扣力度:1 - 到手价/划线价,越大越优惠。"""
    line = item.get("line_price") or 0
    price = item.get("display_price") or item.get("jd_price") or 0
    if line > 0 and 0 < price <= line:
        return round(1 - price / line, 4)
    return 0.0


def _sort_key(item: dict):
    # 销量与折扣是跨来源可比较的主要指标；字段缺失或相同则尊重页面原始顺序。
    # source_rank 越小越好，所以取负数后再整体 reverse=True。
    return (
        item.get("sales_num", 0),
        _discount_ratio(item),
        -int(item.get("source_rank") or 999999),
    )


def category_name(item: dict) -> str:
    """类目名直接取页面Tab类目,退化数据无Tab时回退未分类。"""
    return item.get("tab_category") or "未分类"


def _group_ranked(items: list, limit: int, rank_field: str) -> dict:
    # 按 (来源, 类目Tab, sku) 去重,同 sku 保留销量更高的一条
    dedup = {}
    for it in items:
        key = (it["source_key"], it.get("tab_category", ""), it["sku_id"])
        prev = dedup.get(key)
        if prev is None or it.get("sales_num", 0) > prev.get("sales_num", 0):
            dedup[key] = it
    items = list(dedup.values())

    # 分组:source_name -> 类目Tab名 -> [items]
    grouped = defaultdict(lambda: defaultdict(list))
    for it in items:
        grouped[it["source_name"]][category_name(it)].append(it)

    result = {}
    for source_name, cats in grouped.items():
        result[source_name] = {}
        for cat_name, cat_items in cats.items():
            ranked = sorted(cat_items, key=_sort_key, reverse=True)[:limit]
            enriched = []
            for idx, it in enumerate(ranked, 1):
                row = dict(it)
                row[rank_field] = idx
                row["discount_ratio"] = _discount_ratio(it)
                row["category_name"] = cat_name
                enriched.append(row)
            result[source_name][cat_name] = enriched
    return result


def build_candidate_pool(items: list, max_candidates: int = None) -> dict:
    """按来源和页面类目构建发送给 AI 的候选池。"""
    max_candidates = max_candidates or config.MAX_CANDIDATES_PER_CATEGORY
    return _group_ranked(items, max_candidates, "candidate_rank")


def select_top(items: list, top_n: int = None) -> dict:
    """
    规则回退选品。输入 parser 解后的商品列表，返回每类目规则 TopN。
    """
    top_n = top_n or config.TOP_N_PER_CATEGORY
    return _group_ranked(items, top_n, "rank")
