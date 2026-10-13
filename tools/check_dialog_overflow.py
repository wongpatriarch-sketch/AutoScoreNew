"""弹窗越界真实渲染检测(回归 #1)—— 屏障像素判别法。

页面背景为纯洋红,弹窗屏障会将其压暗为暗洋红。若表格内容越出弹窗,
溢出的浅色文字/表格底色会覆盖底部条带的暗洋红屏障。
指标:底部条带中"洋红系像素"占比 —— 无越界 ≈ 1.0,越界时骤降。

运行:python tools/check_dialog_overflow.py [old]   # 启动探针窗口(old=缺陷结构)
     python tools/check_dialog_overflow.py analyze # 像素分析(退出码 0=无越界)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

_OLD = False


def make_dialog(old: bool = False) -> ft.AlertDialog:
    """与 app/event_engine._preview 相同嵌套结构的弹窗,200 行超长姓名。

    old=True 时构造修复前的缺陷结构(仅横向滚动,表格高度约束不完整)。
    """
    table_rows = []
    for i in range(200):
        name = f"欧阳雨桐浩然思远子涵{i:03d}"
        table_rows.append(ft.DataRow(cells=[
            ft.DataCell(ft.Container(
                content=ft.Text(name + ("  ⚠同名" if i % 7 == 0 else name), size=12,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                color="#FF8A80" if i % 7 == 0 else "#E8ECF5",
                                weight=ft.FontWeight.BOLD if i % 7 == 0 else None),
                width=170,
            )),
            ft.DataCell(ft.Text("花名册" if i % 7 else "⚠同名",
                                size=11, color="#9AA3B5")),
            ft.DataCell(ft.Text("+3.0", size=12, weight=ft.FontWeight.BOLD,
                                color="#A5D6A7")),
        ]))

    def table_widget() -> ft.Control:
        dt = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("姓名")),
                     ft.DataColumn(ft.Text("匹配")),
                     ft.DataColumn(ft.Text("本次积分"))],
            rows=table_rows,
            column_spacing=24,
            heading_row_height=36,
            data_row_min_height=38,
            data_row_max_height=42,
        )
        if old:
            return ft.Row([dt], scroll=ft.ScrollMode.AUTO)
        # 与 app 修复后一致:纵向滚动套横向拖动 + 硬裁剪
        return ft.Column([ft.Row([dt], scroll=ft.ScrollMode.AUTO)],
                         scroll=ft.ScrollMode.AUTO)

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("预览确认 —— 越界压力测试", size=16, weight=ft.FontWeight.BOLD),
        content=ft.Container(
            content=ft.Column([
                ft.Text("主教官：张三    训练 0 次 · 彩排 1 次    正式时长 1 小时",
                        size=12, color="#9AA3B5"),
                ft.Container(content=table_widget(), height=360, width=430,
                             clip_behavior=ft.ClipBehavior.HARD_EDGE),
                ft.Text("共 200 行 —— 弹窗下方洋红屏障不应被覆盖。",
                        size=11, color="#9AA3B5"),
            ], spacing=10, tight=True),
        ),
        scrollable=True,
        actions=[ft.TextButton("知道了", on_click=lambda e: None)],
        shape=ft.RoundedRectangleBorder(radius=14),
    )


def main(page: ft.Page) -> None:
    page.title = "OVF-PROBE"
    page.bgcolor = "#FF00FF"   # 纯洋红:溢出文字/表格底色一眼可辨
    page.window.width = 900
    page.window.height = 700
    page.add(ft.Text("probe", color="#FF00FF"))
    page.open(make_dialog(_OLD))
    page.update()


def analyze() -> int:
    import ctypes
    from ctypes import wintypes

    import numpy as np
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "OVF-PROBE")
    if not hwnd:
        print("probe window not found")
        return 1
    # 客户区矩形(排除阴影/边框)
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    rc = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    left, top = pt.x, pt.y
    right, bottom = left + rc.right, top + rc.bottom
    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    a = np.asarray(img.convert("RGB")).astype(int)
    h, w, _ = a.shape
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    # 弹窗 = 低饱和暗色(深蓝黑,r≈g≈b);背景 = 压暗洋红(r、b 高,g 低)
    dlg = (r < 90) & (g < 95) & (b < 120) & (np.abs(r - b) < 35)
    light = (r > 190) & (g > 190) & (b > 190)
    dim_magenta = (r > 60) & (b > 60) & (g < 55) & (np.abs(r - b) < 70)
    rows = np.where(dlg.sum(axis=1) > w * 0.20)[0]
    if not len(rows):
        print("dialog region not found")
        return 1
    d_top, d_bot = int(rows[0]), int(rows[-1])
    # 弹窗正下方 40px 条带(溢出内容绘制区)
    y0, y1 = d_bot + 2, min(h, d_bot + 42)
    band_l = int(light[y0:y1].sum())
    band_m = int(dim_magenta[y0:y1].sum())
    band_t = (y1 - y0) * w
    print(f"dialog rows {d_top}-{d_bot}, below-band [{y0}:{y1}]: "
          f"light={band_l / band_t:.4f} dim_magenta={band_m / band_t:.4f} ({band_l}/{band_t})")
    # 条带必须是背景(压暗洋红为主)才有效;有效时无浅色 = 无越界
    if band_m / band_t < 0.5:
        print("band is not background - measurement invalid")
        return 1
    return 0 if band_l == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        sys.exit(analyze())
    _OLD = len(sys.argv) > 1 and sys.argv[1] == "old"
    ft.app(main)
