"""直播批量创建配置。"""
from __future__ import annotations

# 输入列名推荐（支持别名）
COLUMN_TITLE = "直播标题"
COLUMN_COVER = "直播封面"
COLUMN_START_TIME = "开播时间"
COLUMN_LIVE_FORM = "直播形式"
COLUMN_LIVE_DIRECTION = "画面方向"
COLUMN_LIVE_LOCATION = "直播地点"
COLUMN_LIVE_CATEGORY = "直播品类"

TITLE_COLUMN_ALIASES = [COLUMN_TITLE, "标题", "直播间标题", "直播名称"]
COVER_COLUMN_ALIASES = [COLUMN_COVER, "封面", "直播封面链接"]
START_TIME_COLUMN_ALIASES = [COLUMN_START_TIME, "开播", "直播时间", "开始时间", "直播开始时间"]
FORM_COLUMN_ALIASES = [COLUMN_LIVE_FORM, "形式", "直播形式（正式/测试）"]
DIRECTION_COLUMN_ALIASES = [COLUMN_LIVE_DIRECTION, "方向", "横竖屏", "屏幕方向"]
LOCATION_COLUMN_ALIASES = [COLUMN_LIVE_LOCATION, "地点", "直播地点"]
CATEGORY_COLUMN_ALIASES = [COLUMN_LIVE_CATEGORY, "品类", "直播品类"]

# 默认值
DEFAULT_LIVE_FORM = "正式直播"
DEFAULT_LIVE_DIRECTION = "竖屏"
DEFAULT_LIVE_LOCATION = "不显示地点"
DEFAULT_LIVE_CATEGORY = "多品类无法确定品类选此项"

# 字段取值约束
VALID_LIVE_FORMS = ["正式直播", "测试直播"]
VALID_LIVE_DIRECTIONS = ["竖屏", "横屏"]
VALID_LIVE_CATEGORIES = [
    "多品类无法确定品类选此项",
    "家电",
    "母婴",
    "居家",
    "电脑数码",
    "时尚",
    "美食",
    "手机",
    "美妆",
    "图书文教",
]
VALID_LIVE_LOCATIONS = ["不显示地点"]

# 业务侧简称到页面真实选项的映射
CATEGORY_OPTION_MAP = {
    "多品类": "多品类无法确定品类选此项",
    "无法确定品类": "多品类无法确定品类选此项",
}

# 业务限制
DAILY_CREATE_LIMIT = 30
TITLE_MIN_LENGTH = 5
TITLE_MAX_LENGTH = 15

# 页面元素 selector（基于 2026-06-30 京东直播后台结构）
SELECTORS = {
    "formal_live_tab": '.jd-tabs-tab:has-text("正式直播"), .ant-tabs-tab:has-text("正式直播")',
    "create_button": 'button:has-text("创建直播")',
    "drawer": '.jd-drawer-content',
    "title_input": '#createRoom_title input',
    "title_container": '#createRoom_title',
    "publish_time_input": '#createRoom_publishTime',
    "live_form_select": '#createRoom_test',
    "screen_direction_select": '#createRoom_screen',
    "location_region_select": '#createRoom_region',
    "location_address_select": '#createRoom_addressText',
    "category_select": '#createRoom_type',
    "submit_button": '.jd-drawer-footer button:has-text("创建"), .ant-drawer-footer button:has-text("创建")',
    "cancel_button": '.jd-drawer-footer button:has-text("取消"), .ant-drawer-footer button:has-text("取消")',
    "select_dropdown": '.jd-select-dropdown',
    "select_option": '.jd-select-item',
    "cascader_dropdown": '.jd-cascader-menus',
    "cascader_option": '.jd-cascader-menu-item',
    "picker_popup": '.jd-picker-dropdown',
    "picker_ok_button": '.jd-picker-footer .jd-btn-primary',
}

# 开播时间输入/显示格式（尝试多种）
DATETIME_INPUT_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d",
]

# 输出结果列
RESULT_COLUMNS = [
    "原始行号",
    "直播标题",
    "开播时间",
    "直播形式",
    "画面方向",
    "直播地点",
    "直播品类",
    "创建状态",
    "失败原因",
]
