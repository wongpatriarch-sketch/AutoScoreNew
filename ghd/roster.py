"""花名册解析:A 列读取、届别状态机打标、空行过滤、同名检测。"""

from dataclasses import dataclass, field

from .constants import COL_NAME, COL_TOTAL, GENERATION_RE


@dataclass
class Member:
    """内存中的队员对象(隐式追加 generation 届数属性)。"""
    row: int          # Excel 物理行号(1 起)
    name: str
    generation: int | None = None   # 所属届数(由最近的界别分隔行决定)
    scores: dict = field(default_factory=dict)  # 列号 -> 数值
    total: float = 0.0


@dataclass
class Roster:
    """花名册解析结果。"""
    members: list[Member] = field(default_factory=list)
    generation_of: dict[int, int] = field(default_factory=dict)  # 行号 -> 界别数字
    by_name: dict[str, list[Member]] = field(default_factory=dict)
    duplicate_names: list[str] = field(default_factory=list)

    @property
    def names(self) -> set[str]:
        return set(self.by_name.keys())

    def unique_members(self, name: str) -> list[Member]:
        return self.by_name.get(name, [])


def parse_roster(header_row: list, rows: list[list]) -> Roster:
    """解析主表 A 列。

    - 检测 `^--(\\d+)届--$` 界别行:提取数字更新状态变量,不作为人员展示
    - 界别行之后的正常人员隐式追加 generation 属性
    - 剔除 A 列为空的占位行
    - 同名检测:by_name 中同名成员 > 1 即记入 duplicate_names
    """
    roster = Roster()
    current_gen: int | None = None
    for ridx, row in enumerate(rows):
        # rows 不含表头行:表头在 Excel 第 1 行,数据从第 2 行起,
        # 因此 rows[ridx] 的物理行号 = ridx + 2(此前 +1 是 off-by-one,
        # 导致所有积分写入/读取落在上一行,汇总与各列之和对不上)。
        r = ridx + 2  # 物理行号(1 起,含表头行)
        a = row[COL_NAME - 1] if len(row) >= COL_NAME else None
        name = "" if a is None else str(a).strip()
        if not name:
            continue
        m = GENERATION_RE.match(name)
        if m:
            roster.generation_of[r] = int(m.group(1))
            current_gen = int(m.group(1))
            continue
        total = row[COL_TOTAL - 1] if len(row) >= COL_TOTAL else None
        try:
            total_v = float(total)
            if total_v != total_v:
                total_v = 0.0
        except (TypeError, ValueError):
            total_v = 0.0
        mem = Member(row=r, name=name, generation=current_gen, total=total_v)
        roster.members.append(mem)
        roster.by_name.setdefault(name, []).append(mem)

    roster.duplicate_names = sorted(n for n, lst in roster.by_name.items() if len(lst) > 1)
    return roster
