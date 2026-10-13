"""名单分隔符清洗器:6 种分隔符解析、去空、去重、保序。"""

import re

from .constants import NAME_SPLIT_RE


def parse_names(raw: str) -> list[str]:
    """解析长文本人名串。

    - 支持 6 种分隔符:中文逗号，/ 英文逗号, / 中文顿号、/ 半角空格 / 全角空格 / 换行
    - 自动剥离每个姓名首尾多余空格
    - 过滤空项;单次卡片内自动去重(保持首次出现顺序)
    """
    if not raw:
        return []
    parts = [p.strip() for p in NAME_SPLIT_RE.split(str(raw))]
    seen: set[str] = set()
    names: list[str] = []
    for p in parts:
        if not p:
            continue
        if p in seen:
            continue
        seen.add(p)
        names.append(p)
    return names


def find_unknown(names: list[str], roster: set[str]) -> list[str]:
    """返回名单中不在花名册里的人名(保序)。"""
    return [n for n in names if n not in roster]


def find_duplicates(raw: str) -> list[str]:
    """返回原始串中重复出现的人名(用于同名错加预警)。"""
    if not raw:
        return []
    parts = [p.strip() for p in NAME_SPLIT_RE.split(str(raw)) if p.strip()]
    seen: set[str] = set()
    dup: list[str] = []
    for p in parts:
        if p in seen and p not in dup:
            dup.append(p)
        seen.add(p)
    return dup
