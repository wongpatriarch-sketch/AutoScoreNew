"""打包版启动最终验证:启动 exe -> 检查窗口标题 -> 像素检测错误页 -> 按 PID 清理。

运行:python tools/verify_packaged_final.py
"""

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dist_new", "GHD-Score.exe")


def titles_with(*keys: str) -> list[str]:
    user32 = ctypes.windll.user32
    out: list[str] = []

    def cb(h, l):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                if any(k in buf.value for k in keys):
                    out.append(buf.value)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def main() -> int:
    import flet_desktop  # noqa: F401  确认打包环境
    p = subprocess.Popen([EXE], close_fds=True)
    time.sleep(14)
    titles = titles_with("GHD", "国旗", "Error")
    print("titles:", titles)
    ok_title = any("国旗护卫队积分管理" in t and "Error" not in t for t in titles)

    from PIL import ImageGrab
    img = ImageGrab.grab().convert("RGB")
    w, h = img.size
    px = img.load()
    red = total = 0
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            r, g, b = px[x, y]
            total += 1
            if r > 180 and g < 90 and b < 90:
                red += 1
    ratio = red / total
    print(f"red={ratio:.3f} -> {'ERROR PAGE' if ratio > 0.3 else 'NORMAL UI'}")

    # 按 PID 树清理自己的实例
    try:
        import psutil
        parent = psutil.Process(p.pid)
        for proc in [parent, *parent.children(recursive=True)]:
            proc.kill()
    except ImportError:
        p.kill()
    print("instance closed, PID", p.pid)
    return 0 if ok_title and ratio <= 0.3 else 1


if __name__ == "__main__":
    sys.exit(main())
