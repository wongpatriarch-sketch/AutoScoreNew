"""退出速度实测:启动打包版 -> 发送 WM_CLOSE -> 计时直到进程全部退出。

运行:python tools/verify_exit_speed.py
"""

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dist_new", "GHD-Score.exe")
WM_CLOSE = 0x0010


def find_hwnd() -> int:
    user32 = ctypes.windll.user32
    return user32.FindWindowW(None, "国旗护卫队积分管理 · GHD Score")


def pids_of(name: str) -> set:
    out = set()
    r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}.exe",
                        "/FO", "CSV", "/NH"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and name.lower() in parts[0].lower():
            try:
                out.add(int(parts[1]))
            except ValueError:
                pass
    return out


def main() -> int:
    # PID 快照:忽略测试前已存在的进程(如其他探针孤儿化的 flet 客户端)
    pre = pids_of("GHD-Score") | pids_of("flet")
    p = subprocess.Popen([EXE], close_fds=True)
    hwnd = 0
    for _ in range(40):          # 最多等 20s 出窗
        time.sleep(0.5)
        hwnd = find_hwnd()
        if hwnd:
            break
    if not hwnd:
        print("window never appeared")
        return 1
    print(f"window up (hwnd={hwnd}), sending WM_CLOSE ...")
    user32 = ctypes.windll.user32
    t0 = time.perf_counter()
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    # 轮询:窗口消失 + 相关进程退出
    deadline = time.perf_counter() + 15
    closed_at = None
    while time.perf_counter() < deadline:
        time.sleep(0.1)
        if not user32.IsWindow(hwnd):
            closed_at = time.perf_counter() - t0
            break
    print(f"window closed after {closed_at:.2f}s" if closed_at
          else "window still open after 15s!")
    # 进程退出检查(再等最多 3s,只看本次启动的进程)
    left = []
    for _ in range(30):
        time.sleep(0.1)
        cur = (pids_of("GHD-Score") | pids_of("flet")) - pre
        left = list(cur)
        if not left:
            break
    total = time.perf_counter() - t0
    if left:
        print(f"processes still alive after {total:.2f}s: {left[:2]}")
        print("RESULT: SLOW / STUCK")
        # 清理
        subprocess.run(["taskkill", "/F", "/IM", "GHD-Score.exe"],
                       capture_output=True)
        subprocess.run(["taskkill", "/F", "/IM", "flet.exe"], capture_output=True)
        return 1
    print(f"all processes exited at {total:.2f}s")
    print("RESULT: FAST EXIT" if total < 3 else "RESULT: EXIT OK (>3s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
