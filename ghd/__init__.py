"""
GHD Score Tool — 国旗护卫队积分管理与统计工具 核心包。

模块划分:
- constants:   列映射、正则、计分规则等常量
- utils:       resource_path、时间戳、BatchID、安全数值转换
- backups:     静默滚动备份(.backups,保留最新 20 份)
- name_parser: 名单分隔符清洗器
- roster:      花名册解析(届别状态机、同名检测)
- excel_io:    Excel 读取 / 原子写回 / 列追加与删除 / 模板生成
- scoring:     活动积分结算引擎(纯计算)
- project:     工程配置(.ghd.json)持久化、事务日志、锁系统
- history_ops: 批次落盘 / 修改 / 撤销 的 Excel+JSON 双向操作
- recent:      历史项目列表(Recent Projects)
"""

__version__ = "1.0.0"
