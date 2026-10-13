"""公共 UI 控件:人员长文本框、预警对话框、Snackbar、名单徽章。"""

import flet as ft

from .theme import BG_CARD2, GOLD, PRIMARY


def alert_dialog(page: ft.Page, title: str, message: str,
                 color: str | None = None, actions: list | None = None) -> ft.AlertDialog:
    """统一风格对话框。"""
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED if color == GOLD else
                    ft.Icons.INFO_ROUNDED, color=color or PRIMARY, size=26),
            ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
        ], spacing=10),
        content=ft.Container(
            content=ft.Text(message, size=13, color="#C9D1E3"),
            width=420,
        ),
        actions=actions or [],
        actions_alignment=ft.MainAxisAlignment.END,
        shape=ft.RoundedRectangleBorder(radius=14),
    )
    if not actions:
        # 默认关闭按钮:dlg 必须是本作用域的局部变量,闭包才能在点击时解析到它
        def _close(e=None):
            try:
                page.close(dlg)
            except Exception:
                dlg.open = False
                try:
                    page.update()
                except Exception:
                    pass
        dlg.actions = [ft.TextButton("知道了", on_click=_close)]
    return dlg


def info(page: ft.Page, title: str, message: str) -> None:
    dlg = alert_dialog(page, title, message)
    page.open(dlg)


def warn(page: ft.Page, title: str, message: str) -> None:
    dlg = alert_dialog(page, title, message, color=GOLD)
    page.open(dlg)


def snackbar(page: ft.Page, message: str, error: bool = False) -> None:
    page.open(ft.SnackBar(
        content=ft.Text(message, size=13),
        bgcolor="#B3261E" if error else "#2E7D32",
        duration=4000,
        behavior=ft.SnackBarBehavior.FLOATING,
        shape=ft.RoundedRectangleBorder(radius=10),
    ))


def confirm_dialog(page: ft.Page, title: str, message: str,
                   on_yes, yes_text: str = "确认", danger: bool = True) -> ft.AlertDialog:
    """确认对话框:on_yes 在用户确认后调用。"""

    def _close(e=None):
        page.close(dlg)

    def _yes(e):
        page.close(dlg)
        on_yes(e)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
        content=ft.Container(content=ft.Text(message, size=13, color="#C9D1E3"), width=420),
        actions=[
            ft.TextButton("取消", on_click=_close),
            ft.FilledButton(
                yes_text,
                on_click=_yes,
                style=ft.ButtonStyle(
                    bgcolor="#B3261E" if danger else PRIMARY,
                    color="#FFFFFF",
                ),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        shape=ft.RoundedRectangleBorder(radius=14),
    )
    page.open(dlg)
    return dlg


def names_field(label: str, hint: str = "支持 ， , 、 空格 换行 分隔", **kw) -> ft.TextField:
    """人员长文本人名串输入框。"""
    kw.setdefault("hint_text", hint)
    return ft.TextField(
        label=label,
        multiline=True,
        min_lines=1,
        max_lines=3,
        dense=True,
        border_radius=10,
        **kw,
    )


def duration_options() -> list[ft.dropdown.Option]:
    """时长选项:0.5 ~ 4.0 小时,步长 0.5。"""
    from ghd.constants import DURATION_MAX, DURATION_MIN, DURATION_STEP
    opts = []
    v = DURATION_MIN
    while v <= DURATION_MAX + 1e-9:
        label = f"{v:g} 小时"
        opts.append(ft.dropdown.Option(key=f"{v:g}", text=label))
        v = round(v + DURATION_STEP, 2)
    return opts


def pill(text: str, color: str = PRIMARY) -> ft.Container:
    """圆角徽章。"""
    return ft.Container(
        content=ft.Text(text, size=11, weight=ft.FontWeight.BOLD, color="#0E1116"),
        padding=ft.padding.symmetric(horizontal=10, vertical=4),
        bgcolor=color,
        border_radius=999,
    )
