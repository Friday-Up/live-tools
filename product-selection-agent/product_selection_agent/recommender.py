"""可解释规则回退 + 可选真实 LLM 类目选品。

没有配置 AI 网关时，输出会明确标记 ``explainable_scoring``，不会把模板规则
冒充成 AI。配置 SELECTION_AI_API_URL / KEY / MODEL 后，每个类目的全部候选只
调用一次兼容 OpenAI Chat Completions 协议的模型，由模型筛选、排序并生成文案。
"""
from __future__ import annotations

import json
import math
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config


_MODEL_NETWORK_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    socket.timeout,
    ConnectionError,
)

_MODEL_REQUEST_ERRORS = _MODEL_NETWORK_ERRORS + (
    KeyError,
    ValueError,
    json.JSONDecodeError,
)

_AI_RATE_LOCK = threading.Lock()
_AI_REQUEST_TIMES: deque[float] = deque()


def _wait_for_ai_rate_slot() -> None:
    """限制滚动 1 秒内的模型请求数，补偿重试也遵守同一上限。"""
    while True:
        with _AI_RATE_LOCK:
            now = time.monotonic()
            while _AI_REQUEST_TIMES and now - _AI_REQUEST_TIMES[0] >= 1.0:
                _AI_REQUEST_TIMES.popleft()
            if len(_AI_REQUEST_TIMES) < config.AI_RPS_LIMIT:
                _AI_REQUEST_TIMES.append(now)
                return
            wait_seconds = max(0.01, 1.0 - (now - _AI_REQUEST_TIMES[0]))
        time.sleep(wait_seconds)


def recommendation_mode() -> str:
    if config.AI_API_URL and config.AI_API_KEY and config.AI_MODEL:
        return "llm_enhanced"
    return "explainable_scoring"


def _prefilter_candidates(
    category_name: str,
    candidates: list[dict],
) -> tuple[list[dict], dict[str, str]]:
    """使用已确认的平台类目 ID 排除确定串类项，未知情况不做猜测。"""
    allowed_ids = config.CATEGORY_ID2_ALLOWLIST.get(category_name)
    if not allowed_ids:
        return candidates, {}
    allowed: list[dict] = []
    excluded: dict[str, str] = {}
    for item in candidates:
        category_id2 = str(item.get("category_id2") or "")
        sku_id = str(item.get("sku_id") or "")
        if category_id2 and category_id2 not in allowed_ids:
            excluded[sku_id] = f"平台类目ID与{category_name}不匹配"
        else:
            allowed.append(item)
    return allowed, excluded


def _sales_score(value: int, maximum: int) -> float | None:
    if value <= 0 or maximum <= 0:
        return None
    return math.log1p(value) / math.log1p(maximum)


def _price_score(value: float, prices: list[float]) -> float | None:
    if value <= 0 or not prices:
        return None
    low, high = min(prices), max(prices)
    if high == low:
        return 0.7
    # 只表示“同一页面类目候选中的相对价格竞争力”，不等价于质量或利润率。
    return 1 - (value - low) / (high - low)


def _page_rank_score(rank: int, size: int) -> float | None:
    if rank <= 0 or rank >= 999999:
        return None
    return 1.0 if size <= 1 else max(0.0, 1 - (rank - 1) / (size - 1))


def _score_item(item: dict, items: list[dict]) -> tuple[float, dict]:
    maximum_sales = max((row.get("sales_num", 0) for row in items), default=0)
    prices = [
        row.get("display_price") or row.get("jd_price") or 0
        for row in items
        if (row.get("display_price") or row.get("jd_price") or 0) > 0
    ]
    price = item.get("display_price") or item.get("jd_price") or 0
    discount = item.get("discount_ratio", 0) or 0
    good_rate = item.get("good_rate", 0) or 0

    components = {
        "sales": (_sales_score(item.get("sales_num", 0), maximum_sales), 0.40),
        "discount": (min(discount / 0.6, 1.0) if discount > 0 else None, 0.20),
        "relative_price": (_price_score(price, prices), 0.15),
        "page_rank": (_page_rank_score(item.get("source_rank", 999999), len(items)), 0.15),
        "good_rate": (good_rate if good_rate > 0 else None, 0.10),
    }
    available_weight = sum(weight for value, weight in components.values() if value is not None)
    if not available_weight:
        return 0.0, {"available": [], "note": "无可评分指标"}
    score = sum(value * weight for value, weight in components.values() if value is not None) / available_weight
    detail = {
        key: round(value, 4)
        for key, (value, _weight) in components.items()
        if value is not None
    }
    detail["available_weight"] = round(available_weight, 2)
    return round(score, 4), detail


def _build_reason(item: dict) -> str:
    parts: list[str] = []
    if item.get("sales_text"):
        parts.append(item["sales_text"])
    elif item.get("sales_num", 0):
        parts.append(f"销量口径 {item['sales_num']:,}")
    if item.get("discount_ratio", 0) > 0:
        parts.append(f"较划线价优惠约 {item['discount_ratio'] * 100:.0f}%")
    price = item.get("display_price") or item.get("jd_price") or 0
    if price > 0:
        parts.append(f"当前展示价 {price:g} 元")
    if item.get("source_rank", 999999) < 999999:
        label = "榜单名次" if item.get("rank_board") else "页面原始位次"
        parts.append(f"{label}第 {item['source_rank']} 位")
    if item.get("good_rate", 0) > 0:
        parts.append(f"好评率 {item['good_rate'] * 100:.0f}%")
    if item.get("rank_board"):
        parts.append(f"来自《{item['rank_board']}》")
    if item.get("selling_points"):
        points = item["selling_points"].split(" | ")[:3]
        parts.append("卖点：" + "、".join(points))
    if item.get("data_quality"):
        parts.append("数据说明：" + item["data_quality"])
    return "；".join(parts) if parts else "页面信息有限，按来源原始顺序保留"


def _build_copy(item: dict) -> str:
    price = item.get("display_price") or item.get("jd_price") or 0
    sales = item.get("sales_text") or ""
    suffix = "｜".join(part for part in ((f"到手 {price:g} 元" if price else ""), sales) if part)
    return f"【类目优选】{item.get('name', '').strip()}" + (f"｜{suffix}" if suffix else "")


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].lstrip()
    decoder = json.JSONDecoder()
    values: list[object] = []
    position = 0
    while position < len(text):
        object_start = min(
            (index for index in (text.find("{", position), text.find("[", position)) if index >= 0),
            default=-1,
        )
        if object_start < 0:
            break
        try:
            value, object_end = decoder.raw_decode(text, object_start)
        except json.JSONDecodeError:
            position = object_start + 1
            continue
        values.append(value)
        position = object_end

    if not values:
        raise ValueError("AI 响应中没有完整 JSON 对象")

    selection_values = [
        value
        for value in values
        if isinstance(value, dict) and isinstance(value.get("selected"), list)
    ]
    if selection_values:
        selected: list = []
        rejected: list = []
        shortfall_reason = ""
        for value in selection_values:
            selected.extend(value.get("selected", []))
            if isinstance(value.get("rejected"), list):
                rejected.extend(value["rejected"])
            if value.get("shortfall_reason"):
                shortfall_reason = str(value["shortfall_reason"])
        return {
            "selected": selected,
            "rejected": rejected,
            "shortfall_reason": shortfall_reason,
        }

    merged_items: dict[str, dict] = {}
    for value in values:
        candidates = value.get("items", []) if isinstance(value, dict) else value
        if not isinstance(candidates, list):
            continue
        for item in candidates:
            if isinstance(item, dict) and item.get("sku_id"):
                merged_items[str(item["sku_id"])] = item
    if merged_items:
        return {"items": list(merged_items.values())}
    if len(values) == 1 and isinstance(values[0], dict):
        return values[0]
    return {"items": []}


def _coerce_ai_selection_payload(parsed: dict) -> dict:
    """把旧 items/纯数组响应转换为当前 selected 协议。"""
    if isinstance(parsed.get("selected"), list):
        return parsed
    items = parsed.get("items")
    if not isinstance(items, list):
        raise ValueError("AI 响应缺少 selected 数组")
    selected = []
    for rank, item in enumerate(items, 1):
        if isinstance(item, dict):
            selected.append({**item, "rank": item.get("rank") or rank})
    return {
        "selected": selected,
        "rejected": parsed.get("rejected", []),
        "shortfall_reason": parsed.get("shortfall_reason", ""),
        "_protocol_warnings": ["模型返回兼容旧 items 协议，已自动转换为 selected"],
    }


def _normalize_ai_selection(
    parsed: dict,
    candidates: list[dict],
    limit: int,
) -> dict:
    """校验 AI 选品协议，只保留候选池中的唯一 SKU 并规范排名。"""
    candidate_skus = {str(item.get("sku_id")) for item in candidates if item.get("sku_id")}
    warnings = [str(item) for item in parsed.get("_protocol_warnings", [])]
    valid_selected: list[tuple[int, int, dict]] = []
    seen: set[str] = set()

    selected = parsed.get("selected", []) if isinstance(parsed, dict) else []
    if not isinstance(selected, list):
        selected = []
        warnings.append("selected 不是数组")
    for position, decision in enumerate(selected, 1):
        if not isinstance(decision, dict):
            warnings.append(f"忽略第 {position} 条非对象入选结果")
            continue
        sku_id = str(decision.get("sku_id") or "")
        if sku_id not in candidate_skus:
            warnings.append(f"忽略未知 SKU: {sku_id or '<empty>'}")
            continue
        if sku_id in seen:
            warnings.append(f"忽略重复 SKU: {sku_id}")
            continue
        reason = str(decision.get("reason") or "").strip()
        copy = str(decision.get("copy") or "").strip()
        if not reason or not copy:
            warnings.append(f"忽略缺少 reason/copy 的 SKU: {sku_id}")
            continue
        try:
            requested_rank = int(decision.get("rank") or position)
        except (TypeError, ValueError):
            requested_rank = position
        seen.add(sku_id)
        valid_selected.append(
            (
                requested_rank,
                position,
                {"sku_id": sku_id, "reason": reason, "copy": copy},
            )
        )

    valid_selected.sort(key=lambda entry: (entry[0], entry[1]))
    if len(valid_selected) > limit:
        warnings.append(f"AI 入选 {len(valid_selected)} 个，超过上限 {limit}，已截断")
    normalized_selected = []
    for rank, (_requested_rank, _position, decision) in enumerate(valid_selected[:limit], 1):
        normalized_selected.append({**decision, "rank": rank})

    selected_skus = {item["sku_id"] for item in normalized_selected}
    rejected_reasons: dict[str, str] = {}
    rejected = parsed.get("rejected", []) if isinstance(parsed, dict) else []
    if isinstance(rejected, list):
        for decision in rejected:
            if not isinstance(decision, dict):
                continue
            sku_id = str(decision.get("sku_id") or "")
            reason = str(decision.get("reason") or "").strip()
            if sku_id in candidate_skus and sku_id not in selected_skus and reason:
                rejected_reasons[sku_id] = reason
    for sku_id in candidate_skus - selected_skus:
        rejected_reasons.setdefault(sku_id, "AI 未入选（未返回详细理由）")

    shortfall_reason = str(parsed.get("shortfall_reason") or "").strip()
    if (
        shortfall_reason
        and "相关有效商品达到" in shortfall_reason
        and "必须选择" in shortfall_reason
    ):
        warnings.append("不足说明疑似复制提示词，已忽略")
        shortfall_reason = ""
    elif len(normalized_selected) >= limit and shortfall_reason:
        warnings.append("入选已达上限，已忽略矛盾的合格不足说明")
        shortfall_reason = ""

    return {
        "selected": normalized_selected,
        "rejected": rejected_reasons,
        "shortfall_reason": shortfall_reason,
        "warnings": warnings,
    }


def _read_stream_content(response) -> str:
    """读取 OpenAI 兼容 SSE，将 choices[].delta.content 拼成完整文本。"""
    assembled = ""

    def append_fragment(fragment: str) -> None:
        nonlocal assembled
        # 标准 OpenAI 返回增量片段；部分兼容网关返回从开头到当前时刻的累计快照。
        if fragment.startswith(assembled):
            assembled = fragment
        elif not assembled.startswith(fragment):
            assembled += fragment

    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        event = json.loads(data)
        choices = event.get("choices") or []
        if not choices:
            continue
        choice = choices[0]
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str) and content:
            append_fragment(content)
            continue
        # 少数兼容网关虽然声明 stream，仍在 message 中一次性返回正文。
        message_content = (choice.get("message") or {}).get("content")
        if isinstance(message_content, str) and message_content:
            append_fragment(message_content)
    content = assembled.strip()
    if not content:
        raise ValueError("模型流式响应没有正文")
    return content


def _candidate_facts(candidates: list[dict]) -> list[dict]:
    """只把页面已抓取事实发送给模型。"""
    return [
        {
            "sku_id": item["sku_id"],
            "name": item["name"],
            "price": item.get("display_price") or item.get("jd_price") or 0,
            "jd_price": item.get("jd_price") or 0,
            "line_price": item.get("line_price") or 0,
            "sales_text": item.get("sales_text") or "",
            "sales_num": item.get("sales_num") or 0,
            "discount_ratio": item.get("discount_ratio", 0),
            "page_rank": item.get("source_rank"),
            "good_rate": item.get("good_rate") or 0,
            "jx_self": bool(item.get("jx_self")),
            "selling_points": (item.get("selling_points") or "")[:200],
            "shop_name": item.get("shop_name") or "",
            "rank_board": item.get("rank_board") or "",
        }
        for item in candidates
    ]


def _build_selection_prompt(
    source_name: str,
    category_name: str,
    candidates: list[dict],
    limit: int,
) -> str:
    facts = _candidate_facts(candidates)
    return (
        "你是京东选品分析助手。先判断候选是否为当前类目的真实商品，再对合格商品排序。\n"
        "硬过滤只允许四类原因：①明显属于其他类目；②凑单专属、服务链接；"
        "③赠品、非商品；④同一商品的重复变体。除此之外不得淘汰。\n"
        "特别重要：低销量、高价格、折扣弱、缺少好评率、非自营，只能影响排序，不能作为淘汰理由。"
        "只要商品属于当前类目且是真实商品，即使商业指标较弱也仍然合格。\n"
        f"相关有效商品达到{limit}个时必须选择{limit}个；不足{limit}个时选择全部合格商品，"
        "并在 shortfall_reason 说明硬过滤后只剩多少个。不得因为想只选爆款而少选。\n"
        "判断示例：血压计、电动轮椅属于医疗器械，黑芝麻丸属于食品；"
        "格力、小米、美的空调即使价格高或销量低，仍属于空调，只能降低排名，不能淘汰。\n"
        "全场精选等无具体商品类目的页面不做串类过滤，只排除非商品并按商业指标排序。\n"
        "排序时仅依据输入中的销量、价格、折扣、页面或榜单位次、好评率、自营和卖点。"
        "只能使用输入事实，不得虚构销量、最低价、补贴金额、功效或促销。\n"
        "返回严格 JSON："
        "{\"selected\":[{\"sku_id\":\"...\",\"rank\":1,\"reason\":\"...\",\"copy\":\"...\"}],"
        "\"rejected\":[{\"sku_id\":\"...\",\"reason\":\"硬过滤原因\"}],"
        "\"shortfall_reason\":\"不足上限时说明原因\"}。"
        "rejected 只列出被硬过滤的候选；正常相关但未进入 Top10 的商品不必列出。\n"
        f"来源={source_name}；类目={category_name}；候选={json.dumps(facts, ensure_ascii=False)}"
    )


def _llm_select_category(
    source_name: str,
    category_name: str,
    candidates: list[dict],
    limit: int,
) -> dict:
    prompt = _build_selection_prompt(source_name, category_name, candidates, limit)
    payload = {
        "model": config.AI_MODEL,
        "messages": [
            {"role": "system", "content": "输出必须是 JSON，不要 Markdown。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        # 网关对非流式复杂生成会等完整结果后才返回，容易触发客户端读超时。
        # 流式模式会尽快返回响应头并持续输出增量内容。
        "stream": True,
    }
    request = urllib.request.Request(
        config.AI_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.AI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    _wait_for_ai_rate_slot()
    with urllib.request.urlopen(request, timeout=config.AI_TIMEOUT_SECONDS) as response:
        content = _read_stream_content(response)
    try:
        parsed = _extract_json_object(content)
        parsed = _coerce_ai_selection_payload(parsed)
    except (ValueError, json.JSONDecodeError) as exc:
        preview = " ".join(content[:240].split())
        raise ValueError(f"{exc}；响应预览: {preview or '<empty>'}") from exc
    return _normalize_ai_selection(parsed, candidates, limit)


class _AICircuitBreaker:
    """并发类目共享的熔断器；有任一成功类目就清零连续失败计数。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._error = ""

    def current_error(self) -> str:
        with self._lock:
            return self._error

    def record(self, success: bool, error: str = "") -> str:
        with self._lock:
            if success:
                self._consecutive_failures = 0
                self._error = ""
                return ""
            self._consecutive_failures += 1
            if self._consecutive_failures >= config.AI_CIRCUIT_FAILURE_THRESHOLD:
                self._error = (
                    f"连续 {self._consecutive_failures} 个类目完全失败；最后错误: {error}"
                )
            return self._error


def _recommend_category(
    source_name: str,
    category_name: str,
    items: list[dict],
    recommend_top: int,
    mode: str,
    circuit: _AICircuitBreaker,
) -> dict:
    scored: list[dict] = []
    for item in items:
        row = dict(item)
        row["reco_score"], row["score_detail"] = _score_item(row, items)
        row["reason"] = _build_reason(row)
        row["copy"] = _build_copy(row)
        row["recommendation_mode"] = "explainable_scoring"
        scored.append(row)
    scored.sort(key=lambda row: (row["reco_score"], -row.get("source_rank", 999999)), reverse=True)
    ai_candidates, platform_excluded = _prefilter_candidates(category_name, scored)
    fallback_picks = ai_candidates[:recommend_top]
    picks = fallback_picks
    ai_error = ""
    shortfall_reason = ""
    protocol_warnings: list[str] = []
    candidate_decisions: dict[str, dict] = {}
    ai_succeeded = False
    network_failure = False
    if mode == "llm_enhanced" and scored:
        circuit_error = circuit.current_error()
        if circuit_error:
            ai_error = f"模型熔断，跳过调用: {circuit_error}"
            print(f"[recommend] {source_name}/{category_name}: {ai_error}")
        else:
            try:
                if platform_excluded:
                    print(
                        f"[recommend] {source_name}/{category_name}: "
                        f"平台类目ID预过滤 {len(platform_excluded)} 个串类候选"
                    )
                if not ai_candidates:
                    raise ValueError("平台类目ID预过滤后没有可供 AI 选择的候选")
                print(
                    f"[recommend] {source_name}/{category_name}: "
                    f"正在由 AI 从 {len(ai_candidates)} 个候选中筛选 Top{recommend_top}（本类目 1 次请求）"
                )
                decision = _llm_select_category(
                    source_name,
                    category_name,
                    ai_candidates,
                    recommend_top,
                )
                item_by_sku = {item["sku_id"]: item for item in scored}
                picks = []
                for selected in decision["selected"]:
                    item = dict(item_by_sku[selected["sku_id"]])
                    item["rank"] = selected["rank"]
                    item["reason"] = selected["reason"]
                    item["copy"] = selected["copy"]
                    item["recommendation_mode"] = "llm_enhanced"
                    picks.append(item)
                shortfall_reason = decision["shortfall_reason"]
                if len(picks) < recommend_top and not shortfall_reason:
                    shortfall_reason = (
                        f"AI 仅判定 {len(picks)} 个候选符合类目与选品要求"
                    )
                protocol_warnings = decision["warnings"]
                selected_rank = {item["sku_id"]: item["rank"] for item in picks}
                for item in scored:
                    sku_id = item["sku_id"]
                    candidate_decisions[sku_id] = {
                        "selected": sku_id in selected_rank,
                        "ai_rank": selected_rank.get(sku_id),
                        "rejection_reason": platform_excluded.get(sku_id)
                        or decision["rejected"].get(sku_id, ""),
                        "reco_score": item["reco_score"],
                        "score_detail": item["score_detail"],
                    }
                ai_succeeded = True
                print(
                    f"[recommend] {source_name}/{category_name}: "
                    f"AI 从 {len(ai_candidates)} 个候选中选出 {len(picks)} 个完成"
                )
                if shortfall_reason:
                    print(f"[recommend] {source_name}/{category_name}: {shortfall_reason}")
            except _MODEL_REQUEST_ERRORS as exc:
                ai_error = f"{type(exc).__name__}: {exc}"
                network_failure = isinstance(exc, _MODEL_NETWORK_ERRORS)
                print(f"[recommend] {source_name}/{category_name}: 模型失败，回退规则评分: {ai_error}")

            # JSON/字段格式错误说明模型网络仍可达，不能因此跳过后续所有类目。
            opened_error = circuit.record(not network_failure, ai_error)
            if opened_error:
                print(f"[recommend] 达到熔断阈值: {opened_error}")
    elif scored:
        print(f"[recommend] {source_name}/{category_name}: 规则推荐 {len(fallback_picks)} 个完成")

    if not ai_succeeded:
        picks = []
        selected_skus = {item["sku_id"] for item in fallback_picks}
        for rank, original in enumerate(fallback_picks, 1):
            item = dict(original)
            item["rank"] = rank
            picks.append(item)
        for item in scored:
            sku_id = item["sku_id"]
            candidate_decisions[sku_id] = {
                "selected": sku_id in selected_skus,
                "ai_rank": None,
                "rejection_reason": (
                    platform_excluded.get(sku_id)
                    or ("规则回退未入选" if sku_id not in selected_skus else "")
                ),
                "reco_score": item["reco_score"],
                "score_detail": item["score_detail"],
            }

    return {
        "products": picks,
        "top_pick": picks[0] if picks else None,
        "recommendation_mode": "llm_enhanced" if ai_succeeded else "explainable_scoring",
        "ai_error": ai_error,
        "shortfall_reason": shortfall_reason,
        "protocol_warnings": protocol_warnings,
        "candidate_decisions": candidate_decisions,
    }


def recommend(candidate_pool: dict, recommend_top: int | None = None) -> dict:
    recommend_top = recommend_top or config.RECOMMEND_TOP_PER_CATEGORY
    mode = recommendation_mode()
    jobs = [
        (source_name, category_name, items)
        for source_name, categories in candidate_pool.items()
        for category_name, items in categories.items()
        if items
    ]
    circuit = _AICircuitBreaker()
    completed: dict[tuple[str, str], dict] = {}

    if mode == "llm_enhanced" and jobs:
        worker_count = min(config.AI_CATEGORY_WORKERS, len(jobs))
        print(
            f"[recommend] 启用 {worker_count} 个类目并行；"
            f"每类目全部候选仅 1 次请求，最多选 Top{recommend_top}；"
            f"全局上限 {config.AI_RPS_LIMIT} RPS"
        )
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="selection-category") as executor:
            futures = {
                executor.submit(
                    _recommend_category,
                    source_name,
                    category_name,
                    items,
                    recommend_top,
                    mode,
                    circuit,
                ): (source_name, category_name)
                for source_name, category_name, items in jobs
            }
            for future in as_completed(futures):
                completed[futures[future]] = future.result()
    else:
        for source_name, category_name, items in jobs:
            completed[(source_name, category_name)] = _recommend_category(
                source_name,
                category_name,
                items,
                recommend_top,
                mode,
                circuit,
            )

    # 并发完成顺序不稳定，按候选池原顺序重建，保证 JSON/Excel 顺序稳定。
    result: dict = {}
    for source_name, categories in candidate_pool.items():
        result[source_name] = {}
        for category_name, items in categories.items():
            if items:
                result[source_name][category_name] = completed[(source_name, category_name)]
    return result
