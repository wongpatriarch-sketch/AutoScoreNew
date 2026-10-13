"""打包版启动验证:启动 exe、跟踪进程、像素检测错误页。

运行:python tools/verify_packaged.py [exe路径]
"""

import subprocess
import sys
import time

from PIL import ImageGrab

EXE = sys.argv[1] if len(sys.argv) > 1 else r"E:\大三\国护队\26秋\AutoScoreNew\dist\GHD-Score.exe"


def analyze(tag: str) -> None:
    img = ImageGrab.grab().convert("RGB")
    w, h = img.size
    px = img.load()
    red = dark = total = 0
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            r, g, b = px[x, y]
            total += 1
            if r > 150 and g < 90 and b < 90:
                red += 1
            elif r < 70 and g < 70 and b < 90:
                dark += 1
    verdict = "ERROR PAGE" if red / total > 0.3 else "NORMAL UI"
    print(f"[{tag}] red={red/total:.3f} dark={dark/total:.3f} -> {verdict}", flush=True)


def procs() -> tuple[bool, bool, str]:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process GHD-Score,flet -ErrorAction SilentlyContinue | "
         "ForEach-Object { \"$($_.ProcessName)|$($_.MainWindowTitle)\" }"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    lines = [l for l in out.splitlines() if l.strip()]
    exe = any(l.startswith("GHD-Score|") for l in lines)
    flet = [l for l in lines if l.startswith("flet|")]
    return exe, bool(flet), (flet[0].split("|", 1)[1] if flet else "")


def main() -> None:
    subprocess.Popen([EXE], close_fds=True)
    for i in range(6):
        time.sleep(5)
        exe, flet, title = procs()
        print(f"t={(i + 1) * 5}s exe={exe} flet_client={flet} title=[{title}]", flush=True)
        if flet and i >= 2:
            analyze("final")
            return
    analyze("final")


if __name__ == "__main__":
    main()
