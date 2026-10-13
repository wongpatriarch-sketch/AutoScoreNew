"""Excel I/O:读取 / 原子写回(含备份)/ 列追加与物理删除 / 模板生成。

一切修改遵循"预读 -> 内存结算 -> 预览确认 -> 原子写回(含文件备份)"。
"""

import os

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from . import backups
from .constants import (COL_COMPREHENSIVE, COL_DAILY_TRAINING, COL_EVENT_START,
                        COL_FLAG_DUTY, COL_LOGISTICS, COL_NAME, COL_TOTAL,
                        HEADER_ROW)
from .utils import clean_str, to_num


class ExcelWriteError(Exception):
    """写入失败(如目标 Excel 正被其他软件占用)。"""

    def __init__(self, message: str = "写入失败：目标 Excel 正被其他软件占用，请关闭后重试"):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------

def read_workbook(path: str) -> openpyxl.Workbook:
    """只读方式加载工作簿。"""
    try:
        return openpyxl.load_workbook(path)
    except PermissionError:
        raise ExcelWriteError("读取失败：目标 Excel 正被其他软件占用，请关闭后重试")


def read_matrix(path: str, sheet: str | None = None, max_col: int = 64) -> list[list]:
    """读取整表为二维列表(含表头行),用于花名册解析与渲染。"""
    wb = read_workbook(path)
    ws = wb[sheet] if sheet else wb.active
    max_row = ws.max_row or 1
    matrix: list[list] = []
    for r in range(1, max_row + 1):
        row = []
        for c in range(1, max_col + 1):
            row.append(ws.cell(row=r, column=c).value)
        matrix.append(row)
    wb.close()
    return matrix


def get_header_names(path: str, sheet: str | None = None) -> list[str]:
    """读取第一行全部表头。"""
    wb = read_workbook(path)
    ws = wb[sheet] if sheet else wb.active
    names = []
    for c in range(1, (ws.max_column or 1) + 1):
        v = ws.cell(row=HEADER_ROW, column=c).value
        names.append(clean_str(v))
    wb.close()
    return names


# ---------------------------------------------------------------------------
# 原子写回
# ---------------------------------------------------------------------------

def atomic_save(wb: openpyxl.Workbook, path: str) -> None:
    """原子写回:先备份 -> 写临时文件 -> 成功后替换;任何失败不碰原文件。"""
    path = os.path.abspath(path)
    backups.make_backup(path)
    tmp = path + ".tmp_save"
    try:
        wb.save(tmp)
    except PermissionError:
        _safe_remove(tmp)
        raise ExcelWriteError()
    except OSError as e:
        _safe_remove(tmp)
        raise ExcelWriteError(f"写入失败：{e}")
    try:
        os.replace(tmp, path)  # 原子替换(Windows 下同盘等价于 MoveFileEx REPLACE_EXISTING)
    except PermissionError:
        _safe_remove(tmp)
        raise ExcelWriteError()
    except OSError as e:
        _safe_remove(tmp)
        raise ExcelWriteError(f"写入失败：{e}")


def _safe_remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 列操作
# ---------------------------------------------------------------------------

def append_column(wb: openpyxl.Workbook, title: str,
                  values: dict[int, float], sheet: str | None = None) -> int:
    """在最右侧数据列之后追加新列。

    - 列名为 title(用户输入的活动名称)
    - values: {物理行号: 分值};未提及的行留空
    - 返回新列的列号
    """
    ws = wb[sheet] if sheet else wb.active
    new_col = _last_data_column(ws) + 1
    cell = ws.cell(row=HEADER_ROW, column=new_col)
    cell.value = title
    cell.font = Font(bold=True)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    for row, score in values.items():
        ws.cell(row=row, column=new_col).value = round(float(score), 2)
    return new_col


def delete_column(wb: openpyxl.Workbook, col_idx: int, sheet: str | None = None) -> None:
    """物理删除整列(右侧列自动左移)。"""
    ws = wb[sheet] if sheet else wb.active
    ws.delete_cols(col_idx)


def find_column_by_header(wb: openpyxl.Workbook, title: str,
                          sheet: str | None = None) -> int | None:
    """按表头名精确查找列号;找不到返回 None。"""
    ws = wb[sheet] if sheet else wb.active
    for c in range(1, (ws.max_column or 1) + 1):
        if clean_str(ws.cell(row=HEADER_ROW, column=c).value) == title:
            return c
    return None


def _last_data_column(ws) -> int:
    """最右侧非空表头列号;空表返回 F 列。"""
    last = 0
    for c in range(1, (ws.max_column or 1) + 1):
        if clean_str(ws.cell(row=HEADER_ROW, column=c).value):
            last = c
    return max(last, COL_TOTAL)


def increment_cells(ws, updates: dict[int, float], col_idx: int) -> None:
    """增量累加:新值 = 原单元格数值 + delta;空值按 0,严禁写 NaN。"""
    for row, delta in updates.items():
        cur = to_num(ws.cell(row=row, column=col_idx).value, 0.0)
        ws.cell(row=row, column=col_idx).value = round(cur + float(delta), 2)


def recompute_totals(ws) -> None:
    """重算全部队员行的汇总(F):F = B~E 之和 + 所有活动列(G+)之和。

    每次导入/修改/撤销后调用,保证「汇总 = 前面各列之和」恒成立,
    严禁 NaN(空值按 0 运算)。分隔行(--N届--)与非队员行跳过。
    """
    from .constants import (COL_COMPREHENSIVE, COL_DAILY_TRAINING, COL_EVENT_START,
                            COL_NAME, COL_TOTAL, GENERATION_RE)
    max_col = ws.max_column or COL_TOTAL
    max_row = ws.max_row or 1
    for r in range(2, max_row + 1):
        name = ws.cell(row=r, column=COL_NAME).value
        if name is None or not str(name).strip():
            continue
        if GENERATION_RE.match(str(name).strip()):
            continue
        total = 0.0
        for c in range(COL_DAILY_TRAINING, COL_COMPREHENSIVE + 1):   # B~E
            total += to_num(ws.cell(row=r, column=c).value, 0.0)
        for c in range(COL_EVENT_START, max_col + 1):                # G+
            total += to_num(ws.cell(row=r, column=c).value, 0.0)
        ws.cell(row=r, column=COL_TOTAL).value = round(total, 2)


# ---------------------------------------------------------------------------
# 模板生成
# ---------------------------------------------------------------------------

_THIN = Side(style="thin", color="B0B0B0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_CENTER = Alignment(horizontal="center", vertical="center")


def _style_header(ws, cols: int) -> None:
    for c in range(1, cols + 1):
        cell = ws.cell(row=HEADER_ROW, column=c)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER
    ws.column_dimensions["A"].width = 12
    for letter in "BCDEF":
        ws.column_dimensions[letter].width = 10


def create_main_template(path: str, names: list[str] | None = None) -> None:
    """创建总积分模板:姓名 A / 夜训周训 B / 升降旗 C / 后勤部 D / 综办部 E / 汇总 F。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "总积分"
    headers = ["姓名", "夜训周训", "升降旗", "后勤部", "综办部", "汇总"]
    for i, h in enumerate(headers, start=1):
        ws.cell(row=HEADER_ROW, column=i).value = h
    _style_header(ws, len(headers))
    for ridx, name in enumerate(names or [], start=2):
        ws.cell(row=ridx, column=COL_NAME).value = name
        for c in range(COL_DAILY_TRAINING, COL_TOTAL + 1):
            ws.cell(row=ridx, column=c).value = 0
    atomic_save(wb, path)


def create_daily_train_template(path: str, names: list[str] | None = None) -> None:
    """创建日常训练考勤模板:姓名 / 总次数。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "日常训练考勤"
    ws.cell(row=HEADER_ROW, column=1).value = "姓名"
    ws.cell(row=HEADER_ROW, column=2).value = "总次数"
    _style_header(ws, 2)
    for ridx, name in enumerate(names or [], start=2):
        ws.cell(row=ridx, column=1).value = name
        ws.cell(row=ridx, column=2).value = 0
    atomic_save(wb, path)


def create_flag_duty_template(path: str, names: list[str] | None = None) -> None:
    """创建升降旗考勤模板:姓名 / 总次数。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "升降旗考勤"
    ws.cell(row=HEADER_ROW, column=1).value = "姓名"
    ws.cell(row=HEADER_ROW, column=2).value = "总次数"
    _style_header(ws, 2)
    for ridx, name in enumerate(names or [], start=2):
        ws.cell(row=ridx, column=1).value = name
        ws.cell(row=ridx, column=2).value = 0
    atomic_save(wb, path)


def create_department_template(path: str, middle: list[str] | None = None,
                               names: list[str] | None = None) -> None:
    """创建部门积分模板:姓名 / [0..N 列明细] / 总积分(智能夹心契约)。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "部门积分"
    middle = middle or ["明细1", "明细2"]
    headers = ["姓名"] + list(middle) + ["总积分"]
    for i, h in enumerate(headers, start=1):
        ws.cell(row=HEADER_ROW, column=i).value = h
    _style_header(ws, len(headers))
    for ridx, name in enumerate(names or [], start=2):
        ws.cell(row=ridx, column=1).value = name
        ws.cell(row=ridx, column=len(headers)).value = 0
    atomic_save(wb, path)
