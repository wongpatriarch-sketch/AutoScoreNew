"""清理 PyInstaller 单文件模式残留的 _MEIxxxxx 解包目录。

原理:GHD-Score.exe(单文件模式,runtime_tmpdir=".")每次运行会在
exe 所在目录/工作目录创建 _MEI<随机> 解包目录(约 160MB,内含 flet 桌面
客户端)。正常退出时 PyInstaller 引导程序会自动删除;进程被强杀或崩溃
时会残留。本脚本安全清理:

- 枚举运行中的 GHD-Score / flet 进程,跳过它们正在使用的目录
  (通过命令行路径与目录创建时间匹配);
- 其余目录全部删除。

运行:python tools/cleanup_mei.py [目录]
不传目录时默认清理脚本所在工作目录。
"""

import os
import re
import shutil
import subprocess
import sys


def running_ghd_dirs() -> set[str]:
    """返回运行中 GHD-Score/flet 进程正在使用的 _MEI 目录绝对路径集合。"""
    live: set[str] = set()
    try:
        out = subprocess.run(
            ["wmic", "process", "where",
             "name like 'GHD%' or name like 'flet%'",
             "get", "CommandLine"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-Process GHD-Score, flet -ErrorAction SilentlyContinue | "
                 "ForEach-Object { (Get-CimInstance Win32_Process -Filter "
                 "\"ProcessId=$($_.Id)\").CommandLine }"],
                capture_output=True, text=True, timeout=15,
            ).stdout
        except Exception:
            return live
    for m in re.finditer(r"(.+?)_MEI[0-9a-f]+", out):
        d = m.group(0)
        if os.path.isdir(d):
            live.add(os.path.abspath(d))
    return live


def cleanup(base: str) -> int:
    live = running_ghd_dirs()
    freed = 0
    count = 0
    for name in sorted(os.listdir(base)):
        if not re.fullmatch(r"_MEI[0-9a-f]+", name):
            continue
        path = os.path.abspath(os.path.join(base, name))
        if not os.path.isdir(path):
            continue
        if path in live:
            print(f"[跳过] {name} —— 正被运行中的进程使用")
            continue
        try:
            size = sum(
                os.path.getsize(os.path.join(r, f))
                for r, _, fs in os.walk(path) for f in fs
            )
            shutil.rmtree(path, ignore_errors=True)
            if os.path.exists(path):
                print(f"[失败] {name} —— 文件被占用,请关闭所有 GHD-Score 窗口后重试")
                continue
            freed += size
            count += 1
            print(f"[删除] {name}  {size / 1048576:.1f} MB")
        except OSError as ex:
            print(f"[失败] {name} —— {ex}")
    print(f"\n共清理 {count} 个目录,回收 {freed / 1048576:.0f} MB")
    return 0


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    sys.exit(cleanup(base))
