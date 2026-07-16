"""京东多来源选品 Agent 配置。"""
from __future__ import annotations

import json
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_PATH = os.getenv(
    "JD_AUTH_PATH",
    os.path.join(BASE_DIR, "..", "live-sku-price-audit", "jd_auth.json"),
)
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# adapter 是关键配置：四个页面的数据结构并不相同，不能共用一个接口解析器。
SOURCES = [
    {
        "key": "gov_subsidy",
        "name": "国家补贴",
        "adapter": "babel_tabs",
        "url": "https://pro.jd.com/mall/active/4Shss3oaLuW1RMisVg4JgpsUsRzN/index.html?babelChannel=ttt1",
        "tab_selector": ".level-1-tab .__j9uV2S:visible",
        "api_keyword": "qryJediPcBabelFloors",
    },
    {
        "key": "black_friday",
        "name": "黑色星期五",
        "adapter": "embedded_flex",
        "url": "https://pro.jd.com/mall/active/JAjtcpqK8RDvB8A4k1ZBgViBKAL/index.html?babelChannel=ttt106",
        # 2026-07-15 实测该页没有业务类目 Tab，按页面精选流处理。
        "fallback_category": "全场精选（页面无类目Tab）",
    },
    {
        "key": "rank_list",
        "name": "排行榜",
        "adapter": "rank_drilldown",
        "url": "https://pro.jd.com/mall/active/3J13cRc4KPMNqXPVuVFY9aDKsBJy/index.html?babelChannel=ttt2",
        "tab_selector": ".mmt-tabitem:visible",
    },
    {
        "key": "jd_special",
        "name": "京东特价",
        "adapter": "flex_feed_tabs",
        "url": "https://pro.jd.com/mall/active/49pNiBvgfNMAAELMNNA1Krxyu6TA/index.html",
        "tab_selector": ".tab_item:visible",
        "api_keyword": "queryPcBabelFeeds",
    },
]

SKIP_TABS = {"推荐", "其他", "猜你喜欢"}
TOP_N_PER_CATEGORY = 10

# 活动页偶尔把相邻大类商品混入同一 Tab。这里仅配置已从真实数据确认、且含义
# 稳定的京东二级类目 ID；缺少 ID 或未配置的 Tab 仍交给 AI 判断，避免误杀。
CATEGORY_ID2_ALLOWLIST = {
    "医疗器械": {"9197", "13893"},
    "电动车": {"27509"},
}

# AI 每个类目最终最多选择 10 个；合格候选不足时不强行补齐。
RECOMMEND_TOP_PER_CATEGORY = TOP_N_PER_CATEGORY

# 普通活动页不是严格榜单，需要保留一个完整候选池交给 AI；默认抓 30 个，
# 避免每个类目无边界滚动到近百个。排行榜已有 rankNum，仍只抓前 10。
MAX_CANDIDATES_PER_CATEGORY = max(
    TOP_N_PER_CATEGORY,
    int(os.getenv("SELECTION_MAX_CANDIDATES_PER_CATEGORY", "30")),
)

# 同步 Playwright Page 不能跨线程共享，因此每个来源 worker 各自启动浏览器。
FETCH_WORKERS = max(1, int(os.getenv("SELECTION_FETCH_WORKERS", "4")))

# 每个类目的全部候选只发起一次模型请求。模型未返回的 SKU 代表未入选，
# 不再按缺失项拆分补发。5 RPS 是上限，不需要为了用满额度拆请求。
AI_RPS_LIMIT = max(1, int(os.getenv("SELECTION_AI_RPS_LIMIT", "5")))
# 每个 worker 处理一个完整类目；默认同时推荐 5 个类目，正好匹配 5 RPS。
AI_CATEGORY_WORKERS = max(1, int(os.getenv("SELECTION_AI_CATEGORY_WORKERS", "5")))
AI_CIRCUIT_FAILURE_THRESHOLD = max(
    1,
    int(os.getenv("SELECTION_AI_CIRCUIT_FAILURE_THRESHOLD", "3")),
)

PAGE_TIMEOUT_MS = int(os.getenv("SELECTION_PAGE_TIMEOUT_MS", "60000"))
PAGE_READY_SECONDS = float(os.getenv("SELECTION_PAGE_READY_SECONDS", "4"))
TAB_TIMEOUT_SECONDS = float(os.getenv("SELECTION_TAB_TIMEOUT_SECONDS", "8"))
TAB_QUIET_SECONDS = float(os.getenv("SELECTION_TAB_QUIET_SECONDS", "1.2"))
# 点击新 Tab 后，旧 Tab 的懒加载请求仍可能延迟 1~2 秒到达。先排空再清桶，
# 否则会稳定出现“当前类目拿到上一个类目商品”的串类。
TAB_SETTLE_SECONDS = float(os.getenv("SELECTION_TAB_SETTLE_SECONDS", "3"))
RANK_TAB_RENDER_SECONDS = float(os.getenv("SELECTION_RANK_TAB_RENDER_SECONDS", "2"))
SCROLL_INTERVAL_SECONDS = float(os.getenv("SELECTION_SCROLL_INTERVAL_SECONDS", "0.6"))
SCROLL_TIMES = int(os.getenv("SELECTION_SCROLL_TIMES", "5"))

# 排行榜一级类目下面是多个“榜单卡片”，而非商品。本实现进入每个类目当前
# 排在第一位的榜单，再取该榜单商品第 1~10 名。
RANK_BOARDS_PER_CATEGORY = 1

# 可选真实 LLM 推荐。环境变量优先；未设置时读取项目本地私密配置文件。
# 本地文件已加入 .gitignore，避免将密钥提交到仓库。
AI_CONFIG_PATH = os.getenv(
    "SELECTION_AI_CONFIG_PATH",
    os.path.join(BASE_DIR, "model-config.local.json"),
)


def _load_local_ai_config() -> dict[str, str]:
    if not os.path.exists(AI_CONFIG_PATH):
        return {}
    try:
        with open(AI_CONFIG_PATH, encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取模型配置文件 {AI_CONFIG_PATH}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"模型配置文件必须是 JSON 对象: {AI_CONFIG_PATH}")
    return {str(key): str(value) for key, value in data.items() if value is not None}


_LOCAL_AI_CONFIG = _load_local_ai_config()


def _ai_setting(name: str) -> str:
    return os.getenv(name, _LOCAL_AI_CONFIG.get(name, "")).strip()


# 兼容 OpenAI Chat Completions 协议的内部/外部网关。
AI_API_URL = _ai_setting("SELECTION_AI_API_URL")
AI_API_KEY = _ai_setting("SELECTION_AI_API_KEY")
AI_MODEL = _ai_setting("SELECTION_AI_MODEL")
AI_TIMEOUT_SECONDS = int(os.getenv("SELECTION_AI_TIMEOUT_SECONDS", "90"))
