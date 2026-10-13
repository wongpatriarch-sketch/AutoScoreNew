"""批次落盘 / 部分修改 / 撤销 的 Excel + JSON 双向原子操作。

所有函数:
- 接收已加载的 config(内存结算),完成 Excel 增量写入与 history 追加/状态流转;
- Excel 写入失败时抛出 ExcelWriteError,调用方负责 Snackbar 提示(不落 JSON)。
"""

from . import excel_io
from .constants import (COL_COMPREHENSIVE, COL_DAILY_TRAINING, COL_EVENT_START,
                        COL_FLAG_DUTY, COL_LOGISTICS, COL_TOTAL,
                        ST_ACTIVE, ST_LOCKED, ST_UNDONE,
                        TX_DEPARTMENT, TX_DAILY_TRAINING, TX_EVENT_CREATE,
                        TX_EVENT_EDIT, TX_FLAG_DUTY)
from .project import active_tx, append_history, make_tx, relabel_stack
from .roster import parse_roster


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------

class ProjectContext:
    """已打开项目的工作上下文:工程配置 + Excel 路径 + 花名册缓存。"""

    def __init__(self, config_path: str, config: dict):
        self.config_path = config_path
        self.config = config
        self.excel_path: str = config["meta"]["excel_path"]

    def roster(self, max_col: int = 64):
        """读取主表并解析花名册(预读)。"""
        matrix = excel_io.read_matrix(self.excel_path, max_col=max_col)
        return parse_roster(matrix[0], matrix[1:])

    def save(self) -> None:
        from .project import save_config
        save_config(self.config_path, self.config)


# ---------------------------------------------------------------------------
# 通用:对花名册对象执行增量(C/F 或指定列)
# ---------------------------------------------------------------------------

def _column_delta_updates(roster, deltas: dict[str, float], col_idx: int):
    """把 {姓名: delta} 映射为 {物理行号: delta};未知姓名忽略并返回。"""
    updates: dict[int, float] = {}
    unknown: list[str] = []
    for name, d in deltas.items():
        members = roster.by_name.get(name)
        if not members:
            unknown.append(name)
            continue
        if len(members) > 1:
            # 同名成员:仅落到第一条(与预览高亮预警呼应,不静默分摊)
            members = members[:1]
        updates[members[0].row] = d
    return updates, unknown


# ---------------------------------------------------------------------------
# 模块四:活动积分落盘(新建)
# ---------------------------------------------------------------------------

def commit_event(ctx: ProjectContext, activity_name: str, scores: dict[str, float]) -> dict:
    """新建大型活动:追加活动列 + 累加 F 列 + 追加事务日志。

    - 列追加:现有数据列最右侧创建新列,列名 = 活动名称
    - 单人分值填入该新列对应队员行
    - 汇总列(F)实时同步:原总分 + 本次新增(空按 0)
    """
    wb = excel_io.read_workbook(ctx.excel_path)
    ws = wb.active
    roster = parse_roster([ws.cell(row=1, column=c).value for c in range(1, 64)], [])

    # 重新用完整矩阵解析(保证行号正确)
    matrix = excel_io.read_matrix(ctx.excel_path, max_col=64)
    roster = parse_roster(matrix[0], matrix[1:])

    updates, unknown = _column_delta_updates(roster, scores, 0)
    if unknown:
        # 理论上预览阶段已过滤;防御性兜底
        raise ValueError("检测到未在名单库中的人员：" + "、".join(unknown))

    new_col = excel_io.append_column(wb, activity_name, updates)
    # 汇总(F)自动重算 = B~E + 所有活动列之和(保证恒等于求和)
    excel_io.recompute_totals(ws)
    try:
        excel_io.atomic_save(wb, ctx.excel_path)
    except excel_io.ExcelWriteError:
        raise

    tx = make_tx(
        TX_EVENT_CREATE, activity_name, scores,
        stack_key=f"activity:{activity_name}",
        activity=activity_name,
        excel_column=new_col,
        is_first=True,
    )
    append_history(ctx.config, tx)
    relabel_stack(ctx.config, tx["stack_key"])
    ctx.save()
    return tx


# ---------------------------------------------------------------------------
# 通用:批量导入(日常训练 / 升降旗 / 部门)
# ---------------------------------------------------------------------------

def commit_batch(ctx: ProjectContext, tx_type: str, label: str,
                 deltas: dict[str, float], target_col: int, **extra) -> dict:
    """批量导入落盘:指定列 + F 列增量累加 + 事务日志。

    - 空值安全:原单元格为空按 0 运算,严禁写 NaN
    - 部门导入同时置状态锁
    """
    matrix = excel_io.read_matrix(ctx.excel_path, max_col=64)
    roster = parse_roster(matrix[0], matrix[1:])
    updates, unknown = _column_delta_updates(roster, deltas, target_col)
    if unknown:
        raise ValueError("检测到未在名单库中的人员：" + "、".join(unknown))

    wb = excel_io.read_workbook(ctx.excel_path)
    ws = wb.active
    excel_io.increment_cells(ws, updates, target_col)
    # 汇总(F)自动重算 = B~E + 所有活动列之和
    excel_io.recompute_totals(ws)
    excel_io.atomic_save(wb, ctx.excel_path)

    stack_key = extra.pop("stack_key", None) or f"{tx_type}:{label}"
    tx = make_tx(tx_type, label, deltas, target_col=target_col,
                 stack_key=stack_key, **extra)
    if tx_type == TX_DEPARTMENT:
        dept = extra.get("department")
        ctx.config["state"]["is_logistics_imported" if dept == "logistics"
                            else "is_comprehensive_imported"] = True
    append_history(ctx.config, tx)
    relabel_stack(ctx.config, stack_key)
    ctx.save()
    return tx


# ---------------------------------------------------------------------------
# 模块九 操作 A:部分修改(Delta Update)
# ---------------------------------------------------------------------------

def commit_edit(ctx: ProjectContext, base_tx: dict, new_scores: dict[str, float],
                editor_label: str = "") -> dict:
    """对【活跃】记录的部分修改。

    1. 对比新旧分数,计算差值 Delta = 新 - 旧
    2. 在该活动对应列 + F 列增量累加差值
    3. 追加全新"修改记录",原记录锁定
    """
    old_scores: dict[str, float] = dict(base_tx.get("changes", {}))
    col = base_tx.get("excel_column") or base_tx.get("target_col")
    stack_key = base_tx.get("stack_key")
    label = base_tx.get("label", "")

    deltas: dict[str, float] = {}
    all_names = set(old_scores) | set(new_scores)
    for name in all_names:
        d = round(float(new_scores.get(name, 0.0)) - float(old_scores.get(name, 0.0)), 2)
        if abs(d) > 1e-9:
            deltas[name] = d

    if deltas:
        matrix = excel_io.read_matrix(ctx.excel_path, max_col=64)
        roster = parse_roster(matrix[0], matrix[1:])
        updates, unknown = _column_delta_updates(roster, deltas, col or 0)
        if unknown:
            raise ValueError("检测到未在名单库中的人员：" + "、".join(unknown))
        wb = excel_io.read_workbook(ctx.excel_path)
        ws = wb.active
        if col:
            # 活动记录:活动列;批次记录:目标列(B/C/D/E)
            excel_io.increment_cells(ws, updates, col)
        # 汇总(F)自动重算 = B~E + 所有活动列之和
        excel_io.recompute_totals(ws)
        excel_io.atomic_save(wb, ctx.excel_path)

    tx = make_tx(
        TX_EVENT_EDIT, label, deltas,
        stack_key=stack_key,
        activity=label,
        excel_column=base_tx.get("excel_column"),
        target_col=base_tx.get("target_col"),
        is_first=False,
        undo_of=base_tx.get("batch_id"),
        editor=editor_label,
    )
    append_history(ctx.config, tx)
    relabel_stack(ctx.config, stack_key)
    ctx.save()
    return tx


# ---------------------------------------------------------------------------
# 模块九 操作 B:撤销
# ---------------------------------------------------------------------------

def undo_tx(ctx: ProjectContext, tx: dict) -> None:
    """对【活跃】记录执行撤销(分支 1 / 分支 2)。

    分支 1(初次创建):
      - F 列精准扣除该批次增加的所有分数
      - 大型活动:物理删除该活动整列(右侧列左移)
      - 部门积分:释放对应状态锁
    分支 2(修改记录):
      - 按差值在活动列 + F 列反向扣减,恢复上一版本
    状态流转:当前记录标记已撤销,上一级记录解锁(由 relabel_stack 完成)。
    """
    changes: dict[str, float] = dict(tx.get("changes", {}))
    reverse = {name: -val for name, val in changes.items()}
    tx_type = tx.get("type")
    stack_key = tx.get("stack_key")

    matrix = excel_io.read_matrix(ctx.excel_path, max_col=64)
    roster = parse_roster(matrix[0], matrix[1:])

    wb = excel_io.read_workbook(ctx.excel_path)
    ws = wb.active

    if tx_type == TX_EVENT_CREATE and tx.get("excel_column"):
        # 分支 1:物理删除该活动整列,F 由重算得出(无需反向扣减)
        col = tx["excel_column"]
        header = ws.cell(row=1, column=col).value
        cur = (header or "").strip() if header is not None else ""
        expect = (tx.get("label") or "").strip()
        if cur == expect:
            excel_io.delete_column(wb, col)
        else:
            # 表头不匹配(列被手动改动):保守按反向差值清空本批次分值(保留列)
            updates, unknown = _column_delta_updates(roster, reverse, col)
            if unknown:
                raise ValueError("检测到未在名单库中的人员：" + "、".join(unknown))
            excel_io.increment_cells(ws, updates, col)
    elif tx_type == TX_EVENT_EDIT and tx.get("excel_column"):
        # 分支 2:活动列反向差值扣减
        col = tx["excel_column"]
        updates, unknown = _column_delta_updates(roster, reverse, col)
        if unknown:
            raise ValueError("检测到未在名单库中的人员：" + "、".join(unknown))
        excel_io.increment_cells(ws, updates, col)
    else:
        # 批次导入类(日常训练/升降旗/部门):指定列反向扣减
        col = tx.get("target_col") or tx.get("excel_column")
        updates, unknown = _column_delta_updates(roster, reverse, col or 0)
        if unknown:
            raise ValueError("检测到未在名单库中的人员：" + "、".join(unknown))
        if col:
            excel_io.increment_cells(ws, updates, col)

    # 汇总(F)自动重算 = B~E + 所有活动列之和(撤销后同样保证恒等于求和)
    excel_io.recompute_totals(ws)
    excel_io.atomic_save(wb, ctx.excel_path)

    # 状态流转 + 部门锁释放
    tx["status"] = ST_UNDONE
    if tx_type == TX_DEPARTMENT:
        dept = tx.get("department")
        if dept:
            ctx.config["state"]["is_logistics_imported" if dept == "logistics"
                                else "is_comprehensive_imported"] = False
    relabel_stack(ctx.config, stack_key)
    ctx.save()
