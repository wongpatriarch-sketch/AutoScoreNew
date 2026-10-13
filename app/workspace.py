"""项目主工作台:四大核心功能导航布局。"""

import flet as ft

from ghd import excel_io, project

from .theme import BG_CARD, PRIMARY
from .widgets import info, snackbar


class Workspace:
    """工作台外壳:顶部导航 + 内容区。

    四大核心功能导航:
    1. 仪表盘与积分排行榜(Dashboard & Ranking)
    2. 活动积分结算引擎(Event Scoring Engine)
    3. 批量考勤与部门分导入引擎(Batch Data Import Engine)
    4. 历史流水与撤销中心(History & Undo Center)
    """

    def __init__(self, page: ft.Page, ctx, exit_cb, picker: ft.FilePicker | None = None):
        self.page = page
        self.ctx = ctx                    # history_ops.ProjectContext
        self.exit_cb = exit_cb            # 返回欢迎页回调
        self.picker = picker              # FilePicker 由入口统一管理
        self.tabs: dict[str, ft.Control] = {}
        self.current = ""
        self._nav_btns: dict[str, ft.Control] = {}

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def render(self) -> ft.Control:
        from .dashboard import DashboardView
        from .event_engine import EventEngineView
        from .history_view import HistoryView
        from .import_engine import ImportEngineView

        self.views = {
            "dashboard": DashboardView(self.page, self.ctx,
                                       reload_cb=lambda: self.show("dashboard")),
            "event": EventEngineView(self.page, self),
            "import": ImportEngineView(self.page, self),
            "history": HistoryView(self.page, self),
        }

        name = self.ctx.config["meta"].get("project_name", "未命名项目")
        self._title = ft.Column([
            ft.Text(name, size=15, weight=ft.FontWeight.BOLD),
            ft.Text(self.ctx.excel_path, size=10, color="#7A8299",
                    overflow=ft.TextOverflow.ELLIPSIS),
        ], spacing=1, expand=True)

        nav_defs = [
            ("dashboard", "积分排名", ft.Icons.LEADERBOARD_ROUNDED),
            ("event", "活动结算", ft.Icons.ADD_CIRCLE_OUTLINE),
            ("import", "批量导入", ft.Icons.UPLOAD_FILE_ROUNDED),
            ("history", "历史撤销", ft.Icons.HISTORY_ROUNDED),
        ]
        nav_row = []
        for key, label, icon in nav_defs:
            btn = ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=17),
                    ft.Text(label, size=13, weight=ft.FontWeight.W_600),
                ], spacing=6, tight=True),
                padding=ft.padding.symmetric(14, 8),
                border_radius=10,
                ink=True,
                on_click=lambda e, k=key: self.show(k),
            )
            self._nav_btns[key] = btn
            nav_row.append(btn)

        back_btn = ft.IconButton(ft.Icons.ARROW_BACK_ROUNDED, tooltip="返回欢迎页",
                                 on_click=self._exit, icon_color="#9AA3B5")

        header = ft.Container(
            content=ft.Row(
                [back_btn, ft.Icon(ft.Icons.FLAG_ROUNDED, color=PRIMARY, size=22),
                 self._title, ft.Container(width=20), ft.Row(nav_row, spacing=6)],
                spacing=10,
            ),
            padding=ft.padding.symmetric(14, 8),
            bgcolor=BG_CARD,
            border_radius=0,
        )

        self._content = ft.Container(expand=True, padding=20)
        # 各视图均自带滚动(表单/列表/表格视口);此槽不再纵向滚动,
        # 否则子内容高度无界,看板表格被撑到全高,横向滚动条会沉到内容最底部
        # (必须先滚到底才可见)。不滚动 → 看板表格区定高,横滚条常驻底部。
        self._view_slot = ft.Column(spacing=0, expand=True)
        self._lock_banner = ft.Container(expand=False)
        self._content.content = ft.Column([self._lock_banner, self._view_slot],
                                          spacing=0, expand=True)
        self._refresh_lock_banner()
        self.show("dashboard")
        self.shell = ft.Column([header, self._content], spacing=0, expand=True)
        return self.shell

    def _refresh_lock_banner(self) -> None:
        state = self.ctx.config.get("state", {})
        locks = []
        if state.get("is_logistics_imported"):
            locks.append("后勤部积分已导入(入口锁定)")
        if state.get("is_comprehensive_imported"):
            locks.append("综办部积分已导入(入口锁定)")
        if locks:
            self._lock_banner.content = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.LOCK, size=14, color="#FFD54F"),
                    ft.Text(" · ".join(locks) + "  |  如需修改请前往【历史撤销】",
                            size=11, color="#FFD54F"),
                ], spacing=6),
                padding=ft.padding.symmetric(12, 7),
                bgcolor="#3A3320",
                border_radius=8,
                margin=ft.margin.only(bottom=12),
            )
        else:
            self._lock_banner.content = ft.Container(height=0, margin=ft.margin.only(bottom=0))

    # ------------------------------------------------------------------
    # 导航
    # ------------------------------------------------------------------
    def show(self, key: str) -> None:
        self.current = key
        for k, btn in self._nav_btns.items():
            active = (k == key)
            btn.bgcolor = "#2A3550" if active else None
        view = self.views[key]
        self._view_slot.controls = [view.render()]
        self._refresh_lock_banner()
        self.page.update()

    def _exit(self, e=None) -> None:
        """返回欢迎页:释放占用锁。"""
        try:
            project.release_lock(self.ctx.excel_path)
        except Exception:
            pass
        self.exit_cb()

    # ------------------------------------------------------------------
    # 供各视图调用:写前冲突检测 + 统一写入失败提示
    # ------------------------------------------------------------------
    def guard_excel(self) -> bool:
        """写入前检测第三方 Office 独占;被占用时弹出阻断提示。"""
        msg = project.check_third_party_lock(self.ctx.excel_path)
        if msg:
            info(self.page, "目标表格已被占用", msg)
            return False
        return True

    def handle_write_error(self, ex: Exception) -> None:
        snackbar(self.page, str(ex) if isinstance(ex, excel_io.ExcelWriteError)
                 else f"写入失败:{ex}", error=True)
