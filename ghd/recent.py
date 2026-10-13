"""历史项目列表(Recent Projects):应用级持久化,展示/载入/清除失效项。"""

import json
import os
import tempfile

from .utils import now_str

RECENT_FILE = os.path.join(tempfile.gettempdir(), "..", "ghd_score_tool_recent.json")
RECENT_FILE = os.path.abspath(RECENT_FILE)
MAX_RECENT = 15


def _load_all() -> list[dict]:
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_all(items: list[dict]) -> None:
    tmp = RECENT_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp, RECENT_FILE)
    except OSError:
        pass


def list_recent() -> list[dict]:
    """最近项目列表,按最后打开时间倒序。

    每项:{name, config_path, excel_path, last_opened, last_modified}
    """
    items = _load_all()
    for it in items:
        try:
            it["exists"] = os.path.isfile(it.get("config_path", "")) and \
                os.path.isfile(it.get("excel_path", ""))
            it["last_modified"] = now_str()
            try:
                import datetime
                mt = datetime.datetime.fromtimestamp(
                    os.path.getmtime(it.get("config_path", "")))
                it["last_modified"] = mt.strftime("%Y-%m-%d %H:%M")
            except OSError:
                pass
        except Exception:
            it["exists"] = False
    items.sort(key=lambda x: x.get("last_opened", ""), reverse=True)
    return items


def add_recent(config_path: str, name: str, excel_path: str) -> None:
    """载入项目成功后登记/更新到列表最前。"""
    config_path = os.path.abspath(config_path)
    excel_path = os.path.abspath(excel_path)
    items = [it for it in _load_all()
             if os.path.abspath(it.get("config_path", "")) != config_path]
    items.insert(0, {
        "name": name,
        "config_path": config_path,
        "excel_path": excel_path,
        "last_opened": now_str(),
    })
    _save_all(items[:MAX_RECENT])


def remove_recent(config_path: str) -> None:
    """从列表中清除指定项(含失效项)。"""
    config_path = os.path.abspath(config_path)
    items = [it for it in _load_all()
             if os.path.abspath(it.get("config_path", "")) != config_path]
    _save_all(items)


def clear_invalid() -> int:
    """一键清除所有失效项(工程文件或 Excel 已不存在);返回清除数量。"""
    items = _load_all()
    kept = [it for it in items
            if os.path.isfile(it.get("config_path", ""))
            and os.path.isfile(it.get("excel_path", ""))]
    removed = len(items) - len(kept)
    _save_all(kept)
    return removed
