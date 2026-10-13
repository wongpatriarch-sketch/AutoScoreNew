"""全局常量:Excel 列契约、正则、计分规则、颜色。"""

import re

# ---------------------------------------------------------------------------
# 主数据表格(总积分表)列契约 —— 列号从 1 开始(A=1)
# ---------------------------------------------------------------------------
COL_NAME = 1              # A: 姓名(花名册,含界别分隔行)
COL_DAILY_TRAINING = 2    # B: 夜训周训(日常训练考勤)
COL_FLAG_DUTY = 3         # C: 升降旗
COL_LOGISTICS = 4         # D: 后勤部
COL_COMPREHENSIVE = 5     # E: 综办部
COL_TOTAL = 6             # F: 汇总(总分)
COL_EVENT_START = 7       # G 起:活动动态列(追加)

HEADER_ROW = 1

COLUMN_LABELS = {
    COL_NAME: "姓名",
    COL_DAILY_TRAINING: "夜训周训",
    COL_FLAG_DUTY: "升降旗",
    COL_LOGISTICS: "后勤部",
    COL_COMPREHENSIVE: "综办部",
    COL_TOTAL: "汇总",
}

# ---------------------------------------------------------------------------
# 界别分隔行正则:--30届-- / -- 30 届 -- 等
# ---------------------------------------------------------------------------
# 界别分隔行:兼容 --30届-- / --30届 / 30届-- / 第30届 / 第 30 届 / 30届
GENERATION_RE = re.compile(r"^\s*-{0,2}\s*第?\s*(\d+)\s*届\s*-{0,2}\s*$")

# ---------------------------------------------------------------------------
# 名单分隔符(6 种):中文逗号 / 英文逗号 / 中文顿号 / 半角空格 / 全角空格 / 换行
# ---------------------------------------------------------------------------
NAME_SPLIT_RE = re.compile(r"[,，、\n\r \u3000]+")

# ---------------------------------------------------------------------------
# 计分法则
# ---------------------------------------------------------------------------
CHIEF_INSTRUCTOR_BONUS = 2.0   # 每位主教官固定 +2.0
FIELD_DUTY_BONUS = 0.5         # 场务固定 +0.5(与活动时长无关)
HOUR_SCORE = 1.0               # 1 小时 = 1.0 分(训练/彩排/正式出旗)
CHIEF_MAX_COUNT = 5            # 主教官 1~5 位
DURATION_MIN = 0.5             # 时长范围 0.5 ~ 4.0 小时
DURATION_MAX = 4.0
DURATION_STEP = 0.5

# 升降旗导入倍率
FLAG_DUTY_RATES = {
    "daily": 0.5,        # 日常升降旗:单次 0.5 分
    "holiday": 1.0,      # 节假日升降旗:单次 1.0 分
}

# 日常训练导入默认单次分值
DAILY_TRAIN_DEFAULT_SCORE = 1.0

# ---------------------------------------------------------------------------
# 文件与目录
# ---------------------------------------------------------------------------
PROJECT_EXT = ".ghd.json"
LOCK_PREFIX = ".~"
OFFICE_LOCK_PREFIX = "~$"     # Office 打开 xlsx 时的属主文件
BACKUP_DIR = ".backups"
BACKUP_KEEP = 20              # 滚动备份保留份数

# 事务类型
TX_EVENT_CREATE = "event_create"      # 新建大型活动
TX_EVENT_EDIT = "event_edit"          # 修改大型活动
TX_DAILY_TRAINING = "daily_training"  # 日常训练
TX_FLAG_DUTY = "flag_duty"            # 升降旗
TX_DEPARTMENT = "department"          # 部门积分(后勤/综办)

TX_TYPE_LABELS = {
    TX_EVENT_CREATE: "新建大型活动",
    TX_EVENT_EDIT: "修改大型活动",
    TX_DAILY_TRAINING: "日常训练",
    TX_FLAG_DUTY: "升降旗",
    TX_DEPARTMENT: "部门积分",
}

# 批次状态
ST_ACTIVE = "active"      # 活跃(栈顶,可修改/可撤销)
ST_LOCKED = "locked"      # 锁定(被更新的记录压栈)
ST_UNDONE = "undone"      # 已撤销

STATUS_LABELS = {
    ST_ACTIVE: "活跃",
    ST_LOCKED: "锁定",
    ST_UNDONE: "已撤销",
}

# 模板文件名(打包进 resources/templates)
TEMPLATE_MAIN = "总积分模板.xlsx"
TEMPLATE_DAILY_TRAIN = "日常训练考勤模板.xlsx"
TEMPLATE_FLAG_DUTY = "升降旗考勤模板.xlsx"
TEMPLATE_DEPARTMENT = "部门积分模板.xlsx"
