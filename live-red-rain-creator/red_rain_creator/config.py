"""红包雨批量创建配置。"""

RED_RAIN_URL = "https://jlive.jd.com/my/redRain"

COLUMN_ACTIVITY_NAME = "活动名称"
COLUMN_START_TIME = "开始时间"
COLUMN_END_TIME = "结束时间"
COLUMN_ISSUE_METHOD = "红包发放方式"
COLUMN_RED_PACKET_ID = "红包ID"
COLUMN_WIN_PROBABILITY = "中奖概率"

ACTIVITY_NAME_ALIASES = [COLUMN_ACTIVITY_NAME, "红包雨名称", "名称"]
START_TIME_ALIASES = [COLUMN_START_TIME, "活动开始时间", "开始日期"]
END_TIME_ALIASES = [COLUMN_END_TIME, "活动结束时间", "结束日期"]
ISSUE_METHOD_ALIASES = [COLUMN_ISSUE_METHOD, "发放方式", "活动类型"]
RED_PACKET_ID_ALIASES = [COLUMN_RED_PACKET_ID, "红包Id", "红包id", "红包 ID"]
WIN_PROBABILITY_ALIASES = [COLUMN_WIN_PROBABILITY, "概率", "中奖率"]

ISSUE_METHOD_NORMAL = "普通发放"
ISSUE_METHOD_AUDIENCE = "按人群策略发放"
VALID_ISSUE_METHODS = [ISSUE_METHOD_NORMAL, ISSUE_METHOD_AUDIENCE]

ACTIVITY_NAME_MAX_LENGTH = 15
PROBABILITY_MIN = 1
PROBABILITY_MAX = 100

DATETIME_INPUT_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
]

RESULT_COLUMNS = [
    "原始行号",
    COLUMN_ACTIVITY_NAME,
    COLUMN_START_TIME,
    COLUMN_END_TIME,
    COLUMN_ISSUE_METHOD,
    COLUMN_RED_PACKET_ID,
    COLUMN_WIN_PROBABILITY,
    "创建状态",
    "活动ID",
    "失败原因",
]
