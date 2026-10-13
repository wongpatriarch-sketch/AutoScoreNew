"""程序入口:国旗护卫队积分管理与统计工具(GHD Score)。

启动:python main.py
打包:pyinstaller GHD-Score.spec
"""

import os
import sys
import traceback


def _log_path() -> str:
    """崩溃日志路径:优先 exe/脚本同目录,失败回落临时目录。"""
    try:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    except Exception:
        base = os.path.expanduser("~")
    p = os.path.join(base, "ghd_score_error.log")
    try:
        open(p, "a").close()
        return p
    except OSError:
        return os.path.join(os.path.expanduser("~"), "ghd_score_error.log")


def main() -> None:
    """带崩溃日志的启动入口。"""
    log = _log_path()
    try:
        import faulthandler
        with open(log, "a", encoding="utf-8") as f:
            faulthandler.enable(f)
    except Exception:
        pass
    try:
        import flet as ft

        from app.hub import Hub
        from app.theme import apply_theme
        from app.workspace import Workspace

        from ghd.history_ops import ProjectContext

        def run(page: ft.Page) -> None:
            apply_theme(page)

            holder = ft.Container(expand=True)
            page.add(holder)

            picker = ft.FilePicker()
            page.overlay.append(picker)
            page.update()   # 立即同步 overlay,确保 pick_files 可用

            current_ws = []   # 当前工作台(存在即持有占用锁)

            def open_workspace(config_path: str, cfg: dict) -> None:
                """进入项目工作台。"""
                ctx = ProjectContext(config_path, cfg)
                ws = Workspace(page, ctx, exit_cb=exit_workspace, picker=picker)
                current_ws.clear()
                current_ws.append(ws)
                holder.content = ws.render()
                page.update()

            def exit_workspace() -> None:
                """返回欢迎页:释放占用锁(工作台 _exit 已释放,此处兜底)。"""
                current_ws.clear()
                holder.content = hub.render()
                hub.refresh()
                page.update()

            def release_all_locks() -> None:
                """窗口关闭时释放全部占用锁(兜底,防残留)。"""
                for ws in current_ws:
                    try:
                        from ghd import project
                        project.release_lock(ws.ctx.excel_path)
                    except Exception:
                        pass

            # 重要:本版本 flet 桌面端 prevent_close=True 是个陷阱——拦截 ✕ 后,
            # 程序调用 window.destroy()/close() 都无法真正关窗,客户端要等内部
            # 超时(实测约 15 秒)才强制关闭,表现为"退出卡住,等好一会"。
            # 因此不拦截 ✕,让系统原生关窗;改用看门狗线程监测窗口消失,
            # 窗口一关就释放占用锁并立即结束进程(实测 <0.5 秒退出)。
            # 数据在每次操作时已原子落盘(含备份),快速退出不丢任何数据。
            def _watchdog() -> None:
                """监测主窗口消失 → 释放锁 → 立即退出进程(保证秒关)。"""
                import time as _t
                from ctypes import windll
                title = "国旗护卫队积分管理 · GHD Score"
                seen = False
                while True:
                    _t.sleep(0.2)
                    try:
                        hwnd = windll.user32.FindWindowW(None, title)
                    except Exception:
                        hwnd = 0
                    if hwnd:
                        seen = True
                    elif seen:
                        release_all_locks()
                        os._exit(0)

            import threading as _th
            _th.Thread(target=_watchdog, daemon=True).start()

            # 客户端断连(窗口被系统关闭等)时同样释放锁并快速退出
            def on_disconnect(e=None):
                release_all_locks()
                os._exit(0)

            page.on_disconnect = on_disconnect

            hub = Hub(page, open_project_cb=open_workspace, picker=picker)
            holder.content = hub.render()
            page.update()

        ft.app(run)
    except Exception:
        with open(log, "a", encoding="utf-8") as f:
            f.write("\n==== " + __import__("datetime").datetime.now().isoformat() +
                    " ====\n")
            f.write(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
