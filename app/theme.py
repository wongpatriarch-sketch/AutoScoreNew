"""UI 主题与公共小部件:Material 3 深色主题、卡片、对话框、徽章。"""

import flet as ft

from ghd.utils import format_score

# ---------------------------------------------------------------------------
# 配色(Material 3 深色)
# ---------------------------------------------------------------------------
PRIMARY = "#7C9EFF"
BG_CARD = "#1E2230"
BG_CARD2 = "#232838"
BG_HOVER = "#2A3042"
NEGATIVE_BG = "#FFB4AB"          # 负分行:浅红(深色主题下取 Material error 容器色)
DUP_COLOR = ft.Colors.ERROR
GOLD = "#FFD54F"

THRESHOLD_NEG_BG = "#ffe6e6"     # 需求指定浅红底色(浅色语境),深色主题下用映射
TITLE_LG = 22
TITLE_MD = 17


def apply_theme(page: ft.Page) -> None:
    """全局深色主题与页面基础设置。"""
    page.title = "国旗护卫队积分管理 · GHD Score"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(
        color_scheme_seed=PRIMARY,
        font_family="Microsoft YaHei UI",
    )
    page.window.width = 1120
    page.window.height = 760
    page.window.min_width = 980
    page.window.min_height = 680
    page.window.center()
    page.padding = 0
    page.bgcolor = "#14161D"


def card(*controls, padding: int = 18, bgcolor: str = BG_CARD,
         expand: bool | None = None) -> ft.Container:
    """圆角卡片容器。"""
    return ft.Container(
        content=ft.Column(list(controls), spacing=12, tight=bool(not expand)),
        padding=padding,
        bgcolor=bgcolor,
        border_radius=16,
        expand=expand,
    )


def section_title(text: str, subtitle: str = "") -> ft.Column:
    """区块标题。"""
    items: list[ft.Control] = [ft.Text(text, size=TITLE_MD, weight=ft.FontWeight.BOLD)]
    if subtitle:
        items.append(ft.Text(subtitle, size=12, color="#9AA3B5"))
    return ft.Column(items, spacing=2)


def icon_button(icon: str, tooltip: str, on_click, color: str = PRIMARY) -> ft.IconButton:
    """标准图标按钮。"""
    return ft.IconButton(
        icon=icon,
        tooltip=tooltip,
        on_click=on_click,
        icon_color=color,
        icon_size=20,
    )
