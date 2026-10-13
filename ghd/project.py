"""工程配置(.ghd.json)持久化、事务日志、占用锁系统、部门状态锁。"""

import json
import os
import uuid

from .constants import (LOCK_PREFIX, OFFICE_LOCK_PREFIX, PROJECT_EXT,
                        ST_ACTIVE, ST_LOCKED, ST_UNDONE)
from .utils import new_batch_id, now_str


# ---------------------------------------------------------------------------
# 工程配置文件
# ---------------------------------------------------------------------------

def default_config(project_name: str, excel_path: str) -> dict:
    """新建工程配置:元数据 + 空 history + 部门状态锁。"""
    return {
        "meta": {
            "project_name": project_name,
            "created_at": now_str(),
            "updated_at": now_str(),
            "excel_path": os.path.abspath(excel_path),
            "excel_signature": "",
        },
        "state": {
            "is_logistics_imported": False,       # 后勤部单次互斥锁
            "is_comprehensive_imported": False,   # 综办部单次互斥锁
        },
        "history": [],  # 流水事务日志(原子批次)
    }


def load_config(path: str) -> dict:
    """读取工程配置文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path: str, config: dict) -> None:
    """原子写工程配置:先写临时文件再替换。

    - 临时文件名带进程号与随机后缀,避免残留锁定文件阻塞
    - PermissionError 时给出明确中文说明(目录权限/杀毒软件拦截)
    """
    path = os.path.abspath(path)
    config.setdefault("meta", {})["updated_at"] = now_str()
    tmp = f"{path}.{os.getpid()}_{uuid.uuid4().hex[:8]}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except PermissionError as ex:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        d = os.path.dirname(path)
        raise PermissionError(
            f"无法在以下目录写入工程配置文件（权限被拒绝）：\n{d}\n\n"
            "可能的原因与解决办法：\n"
            "① 目录受权限保护 —— 请在「工程配置保存目录」中选择其他可写目录"
            "（如桌面、文档）；\n"
            "② 杀毒软件/勒索防护拦截 —— 请将本程序加入白名单；\n"
            "③ 若仍失败，右键本程序选择「以管理员身份运行」。"
        ) from ex


def dir_writable(path: str) -> tuple[bool, str]:
    """目录可写探针:实际写入并删除一个探针文件。

    返回 (是否可写, 不可写时的说明)。
    """
    if not os.path.isdir(path):
        return False, f"目录不存在：\n{path}"
    probe = os.path.join(path, f".ghd_write_test_{os.getpid()}_{uuid.uuid4().hex[:6]}")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("probe")
        os.remove(probe)
        return True, ""
    except PermissionError:
        return False, (
            f"该目录不可写（权限被拒绝）：\n{path}\n\n"
            "可能的原因与解决办法：\n"
            "① 目录受权限保护 —— 请选择其他可写目录（如桌面、文档）；\n"
            "② 杀毒软件/勒索防护拦截 —— 请将本程序加入白名单；\n"
            "③ 右键本程序选择「以管理员身份运行」。"
        )
    except OSError as ex:
        return False, f"该目录不可写：\n{path}\n\n{ex}"


def config_path_for(directory: str, project_name: str) -> str:
    """默认工程文件路径:<目录>/<项目名>.ghd.json。"""
    safe = "".join(c for c in project_name if c not in '\\/:*?"<>|').strip() or "未命名项目"
    return os.path.join(directory, safe + PROJECT_EXT)


# ---------------------------------------------------------------------------
# 事务日志
# ---------------------------------------------------------------------------

def append_history(config: dict, tx: dict) -> None:
    """追加一条事务批次到 history 节点。"""
    config.setdefault("history", []).append(tx)


def make_tx(tx_type: str, label: str, changes: dict[str, float], **extra) -> dict:
    """构造一条事务批次:Batch ID、时间戳、类型、明细 {姓名: 分值变化}、撤销状态。

    - changes: {姓名: 本次实际分值变化量}(撤销后 undo 时填负值明细)
    - extra: 关联活动名 / 导入文件名 / 倍率 / Excel 列号等上下文
    """
    tx = {
        "batch_id": new_batch_id(),
        "time": now_str(),
        "type": tx_type,
        "label": label,
        "changes": {k: round(float(v), 2) for k, v in changes.items()},
        "status": ST_ACTIVE,
        "is_first": True,     # 栈底(初次创建)标记;修改记录为 False
        "undo_of": None,      # 若为修改记录,指向其基于的批次 batch_id
        "count": len(changes),
    }
    tx.update(extra)
    return tx


def stack_for(config: dict, stack_key: str) -> list[dict]:
    """取某个操作对象的版本栈(按时间序):例如 activity:国庆出旗 / dept:logistics。

    单线继承规则:同一操作对象的所有记录构成一个栈,只有栈顶可操作。
    """
    return [tx for tx in config.get("history", [])
            if tx.get("stack_key") == stack_key]


def active_tx(config: dict, stack_key: str) -> dict | None:
    """栈顶(最新且未撤销)记录;没有则 None。"""
    stack = [tx for tx in stack_for(config, stack_key) if tx.get("status") != ST_UNDONE]
    return stack[-1] if stack else None


def relabel_stack(config: dict, stack_key: str) -> None:
    """重算某栈的锁定状态:栈顶 active,其余 locked(未撤销的)。"""
    stack = [tx for tx in stack_for(config, stack_key) if tx.get("status") != ST_UNDONE]
    for i, tx in enumerate(stack):
        tx["status"] = ST_ACTIVE if i == len(stack) - 1 else ST_LOCKED


# ---------------------------------------------------------------------------
# 占用锁系统(Lock System)
# ---------------------------------------------------------------------------

def excel_lock_path(excel_path: str) -> str:
    """轻量锁标志:Excel 同级目录下 .~[filename].lock。"""
    d = os.path.dirname(os.path.abspath(excel_path))
    name = os.path.basename(excel_path)
    return os.path.join(d, LOCK_PREFIX + name + ".lock")


def is_pid_alive(pid: int) -> bool:
    """进程是否存活(Windows 用 OpenProcess 查询,其他平台用信号 0 探测)。"""
    if not pid or pid <= 0:
        return False
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            k32.CloseHandle(handle)
            return True
        return False
    except Exception:
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False
        except NotImplementedError:
            return True   # 无法判断时保守认为存活


def read_lock_info(lock_path: str) -> dict | None:
    """读取锁文件内容:{pid, time, host}。

    旧版本/损坏锁文件(无法解析为 JSON)返回 None,视为残留。
    """
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and "pid" in data else None
    except (OSError, ValueError):
        return None


def acquire_lock(excel_path: str) -> tuple[bool, str]:
    """项目打开时建立占用锁。

    返回 (是否成功, 冲突/说明信息):
    - 检测 Office 属主文件 ~$xxx.xlsx(第三方 Office 独占)
    - 检测本软件锁标志 .~xxx.xlsx.lock:
      · 锁内 PID 已死亡 / 是当前进程 / 无法解析(旧版残留) -> 视为残留锁,自动清理后继续
      · 锁内 PID 存活 -> 真实冲突,阻断
    """
    excel_path = os.path.abspath(excel_path)
    d = os.path.dirname(excel_path)
    name = os.path.basename(excel_path)
    office_lock = os.path.join(d, OFFICE_LOCK_PREFIX + name)
    if os.path.exists(office_lock):
        return False, f"检测到第三方 Office 独占锁定（{OFFICE_LOCK_PREFIX}{name}），目标表格已被占用，请先释放占用或关闭对应文件"
    lock = excel_lock_path(excel_path)
    note = ""
    if os.path.exists(lock):
        info = read_lock_info(lock)
        stale = False
        if info is None:
            stale = True   # 旧版本/损坏锁文件
        elif int(info.get("pid") or 0) == os.getpid():
            stale = True   # 当前进程自己(上次未正常释放)
            note = "检测到本进程上次未释放的锁,已自动清理。"
        elif not is_pid_alive(int(info.get("pid") or 0)):
            stale = True   # 持锁进程已死亡(窗口被强制关闭/崩溃残留)
            note = (f"检测到上次未正常关闭留下的残留锁（原 PID {info.get('pid')}）,"
                    "已自动清理。")
        if stale:
            try:
                os.remove(lock)
            except OSError:
                return False, ("检测到残留锁标志且无法自动清理，请手动删除：\n" + lock)
        else:
            return False, ("目标表格已被本软件的其他项目/实例占用，请先释放占用或关闭对应项目"
                           f"（持锁进程 PID {info.get('pid')}，建立于 {info.get('time', '')}）。"
                           "\n若确认没有其他窗口在用，可点【强制解锁并继续】。")
    try:
        with open(lock, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "pid": os.getpid(),
                "time": now_str(),
                "host": os.environ.get("COMPUTERNAME", ""),
            }, ensure_ascii=False))
    except OSError:
        return False, "无法创建占用锁标志（目录不可写）"
    return True, note


def release_lock(excel_path: str) -> None:
    """释放本软件锁标志(静默)。"""
    try:
        lock = excel_lock_path(excel_path)
        if os.path.exists(lock):
            os.remove(lock)
    except OSError:
        pass


def check_third_party_lock(excel_path: str) -> str | None:
    """运行期间检测第三方 Office 独占;返回冲突说明或 None。"""
    excel_path = os.path.abspath(excel_path)
    office_lock = os.path.join(os.path.dirname(excel_path),
                               OFFICE_LOCK_PREFIX + os.path.basename(excel_path))
    if os.path.exists(office_lock):
        return "目标表格已被占用，请先释放占用或关闭对应文件"
    return None
