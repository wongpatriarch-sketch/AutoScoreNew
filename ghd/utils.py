"""通用工具:PyInstaller 资源路径、时间戳、BatchID、安全数值转换、文件签名。"""

import hashlib
import os
import sys
import uuid
from datetime import datetime


def resource_path(relative: str) -> str:
    """解析打包后资源的绝对路径。

    PyInstaller 单文件模式下,资源解压到 sys._MEIPASS 临时目录;
    开发模式下回落到源码根目录。加载图片/模板等静态资源必须经由本函数,
    严禁直接使用相对路径。
    """
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def now_str() -> str:
    """当前时间戳(秒级,文件名安全)。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp() -> str:
    """紧凑时间戳,用于备份文件名:YYYYMMDD_HHMMSS。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def new_batch_id() -> str:
    """事务批次 ID:时间前缀 + 短 UUID,保证唯一且可读。"""
    return f"TX-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def to_num(value, default: float = 0.0) -> float:
    """防御性数值转换:None/NaN/非数字一律回落为 default,严禁 NaN 进入运算。"""
    if value is None:
        return float(default)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return float(default)
    if f != f:  # NaN
        return float(default)
    return f


def clean_str(value) -> str:
    """防御性字符串转换:None 转 '',其余 strip。"""
    if value is None:
        return ""
    return str(value).strip()


def file_signature(path: str) -> str:
    """文件特征签名:路径哈希 + 大小 + 修改时间,用于绑定一致性校验。"""
    sha = hashlib.sha256(os.path.abspath(path).lower().encode("utf-8")).hexdigest()[:16]
    try:
        st = os.stat(path)
        tail = f"{st.st_size}-{int(st.st_mtime)}"
    except OSError:
        tail = "missing"
    return f"{sha}:{tail}"


def format_score(value: float) -> str:
    """分值显示:整数不带小数点,其余保留 1 位。"""
    v = round(float(value) + 0.0, 2)
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:g}"
