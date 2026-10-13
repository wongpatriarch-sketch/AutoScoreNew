"""静默滚动备份机制:落盘前拷贝备份到隐藏 .backups,永远只保留最新 20 份。"""

import os
import shutil
from datetime import datetime

from .constants import BACKUP_DIR, BACKUP_KEEP


def _stamp_ms() -> str:
    """带微秒的时间戳,避免同一秒内多次备份互相覆盖。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def backup_dir_for(excel_path: str) -> str:
    """备份目录:Excel 同级的隐藏 .backups 文件夹。"""
    return os.path.join(os.path.dirname(os.path.abspath(excel_path)), BACKUP_DIR)


def make_backup(excel_path: str) -> str | None:
    """修改落盘前执行文件拷贝备份。

    命名:YYYYMMDD_HHMMSS_文件名.xlsx;失败静默(不阻断主流程),返回 None。
    """
    src = os.path.abspath(excel_path)
    if not os.path.isfile(src):
        return None
    bdir = backup_dir_for(src)
    try:
        os.makedirs(bdir, exist_ok=True)
        _hide_dir(bdir)
        name = os.path.basename(src)
        dest = os.path.join(bdir, f"{_stamp_ms()}_{name}")
        shutil.copy2(src, dest)
        _cleanup(bdir, keep=BACKUP_KEEP)
        return dest
    except OSError:
        return None


def list_backups(excel_path: str) -> list[str]:
    """按时间倒序列出该 Excel 的全部备份文件路径。"""
    bdir = backup_dir_for(excel_path)
    if not os.path.isdir(bdir):
        return []
    name = os.path.basename(os.path.abspath(excel_path))
    files = [f for f in os.listdir(bdir) if f.endswith("_" + name)]
    files.sort(reverse=True)
    return [os.path.join(bdir, f) for f in files]


def _hide_dir(path: str) -> None:
    """Windows 下将目录设为隐藏(其他平台静默跳过)。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(path, 0x02)  # FILE_ATTRIBUTE_HIDDEN
    except Exception:
        pass


def _cleanup(bdir: str, keep: int) -> None:
    """滚动清理:只保留最新 keep 份备份。"""
    try:
        files = [f for f in os.listdir(bdir) if f.endswith(".xlsx")]
        files.sort(reverse=True)
        for old in files[keep:]:
            try:
                os.remove(os.path.join(bdir, old))
            except OSError:
                pass
    except OSError:
        pass
