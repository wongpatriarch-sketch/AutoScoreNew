"""批量导入数据契约解析:升降旗 / 日常训练 / 部门积分(智能夹心提取)。

统一返回 rows = [(姓名, 总次数或总积分)],已做空值清洗:
- 姓名为空的行直接过滤
- 总次数/总积分为空(NaN/None/非数字)强制转 0
"""

import openpyxl

from .constants import COL_DAILY_TRAINING, COL_FLAG_DUTY, COL_LOGISTICS, COL_COMPREHENSIVE
from .utils import clean_str, to_num


def _read_first_sheet(path: str) -> list[list]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    return rows


def _header_index(header: list, name: str) -> int:
    """严格匹配列名,返回列下标(0 起);找不到抛 ValueError。"""
    for i, v in enumerate(header):
        if clean_str(v) == name:
            return i
    raise ValueError(f"缺少必需的列「{name}」")


def parse_count_sheet(path: str) -> list[tuple[str, float]]:
    """升降旗 / 日常训练考勤契约:严格提取「姓名」列与「总次数」列。

    - 列名必须严格匹配「姓名」「总次数」
    - 姓名为空的无效行过滤;总次数为空(NaN/None)强制转 0
    """
    rows = _read_first_sheet(path)
    if not rows:
        raise ValueError("文件内容为空")
    header = rows[0]
    i_name = _header_index(header, "姓名")
    i_count = _header_index(header, "总次数")
    out: list[tuple[str, float]] = []
    for r in rows[1:]:
        name = clean_str(r[i_name]) if i_name < len(r) else ""
        if not name:
            continue
        count = to_num(r[i_count] if i_count < len(r) else None, 0.0)
        out.append((name, count))
    if not out:
        raise ValueError("未解析到有效数据行（姓名列全为空）")
    return out


def parse_department_sheet(path: str) -> list[tuple[str, float]]:
    """部门积分契约(智能夹心提取)。

    - 首列严格匹配「姓名」,尾列严格匹配「总积分」
    - 中间 0~N 列明细完全忽略
    - 姓名为空行跳过;总积分为 NaN/None 强制转 0
    """
    rows = _read_first_sheet(path)
    if not rows:
        raise ValueError("文件内容为空")
    header = rows[0]
    i_name = _header_index(header, "姓名")
    i_total = _header_index(header, "总积分")
    out: list[tuple[str, float]] = []
    for r in rows[1:]:
        name = clean_str(r[i_name]) if i_name < len(r) else ""
        if not name:
            continue
        total = to_num(r[i_total] if i_total < len(r) else None, 0.0)
        out.append((name, total))
    if not out:
        raise ValueError("未解析到有效数据行（姓名列全为空）")
    return out


def target_col_for_scenes(scene: str) -> int:
    """场景 -> 主表目标列:日常训练 B / 升降旗 C / 后勤 D / 综办 E。"""
    return {
        "daily_training": COL_DAILY_TRAINING,
        "flag_duty": COL_FLAG_DUTY,
        "logistics": COL_LOGISTICS,
        "comprehensive": COL_COMPREHENSIVE,
    }[scene]
