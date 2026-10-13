"""模块八:积分排名与看板中心。

核心原则:只读内存渲染 —— 一切排序、过滤、高亮只在内存与 UI 层进行,
绝对禁止将排序结果写回原 Excel;原表永久保持按届别排列的物理行序。
"""

import flet as ft

from ghd import excel_io
from ghd.constants import COL_TOTAL
from ghd.roster import parse_roster
from ghd.utils import format_score

from .theme import BG_CARD, BG_CARD2, GOLD, NEGATIVE_BG, PRIMARY
from .widgets import snackbar


class DashboardView:
    def __init__(self, page: ft.Page, ctx, reload_cb=None):
        self.page = page
        self.ctx = ctx
        self.mode = "generation"   # generation | global
        self.acts_mode = "split"   # split:每个活动独立一列 | merge:合并为「活动」一列
        self.reload_cb = reload_cb

    def reload(self) -> None:
        """刷新读取主表(重新渲染本视图)。"""
        if self.reload_cb:
            self.reload_cb()
        else:
            self.page.update()

    def render(self) -> ft.Control:
        # 读取主表(预读 -> 内存解析);清空缓存保证实时分值
        _DASH_CACHE.clear()
        try:
            matrix = excel_io.read_matrix(self.ctx.excel_path, max_col=256)
        except Exception as ex:
            return ft.Container(content=ft.Text(f"读取主表失败:{ex}", color="#FF8A80"),
                                padding=30)
        roster = parse_roster(matrix[0], matrix[1:])
        self._dup = set(roster.duplicate_names)
        # 活动列:G 列(7)起所有非空表头列,每个活动独立成列
        from ghd.constants import COL_EVENT_START
        self._activity_cols = [
            (c, str(matrix[0][c - 1]).strip())
            for c in range(COL_EVENT_START, len(matrix[0]) + 1)
            if matrix[0][c - 1] is not None and str(matrix[0][c - 1]).strip()
        ]

        header_row = ft.Row([
            ft.Icon(ft.Icons.LEADERBOARD_ROUNDED, color=PRIMARY),
            ft.Text("积分排行榜", size=18, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.SegmentedButton(
                segments=[
                    ft.Segment(value="generation",
                               label=ft.Text("按届数分组排名"),
                               icon=ft.Icon(ft.Icons.GROUPS)),
                    ft.Segment(value="global",
                               label=ft.Text("按总积分全局排名"),
                               icon=ft.Icon(ft.Icons.PUBLIC)),
                ],
                selected={self.mode},
                on_change=self._switch,
            ),
            ft.SegmentedButton(
                segments=[
                    ft.Segment(value="split",
                               label=ft.Text("活动分列"),
                               tooltip="每个大型活动独立一列展示"),
                    ft.Segment(value="merge",
                               label=ft.Text("活动合并"),
                               tooltip="所有大型活动合并为一列「活动」显示合计"),
                ],
                selected={self.acts_mode},
                on_change=self._acts_switch,
            ),
            ft.IconButton(ft.Icons.REFRESH, tooltip="刷新读取主表",
                          on_click=lambda e: self.reload()),
        ], spacing=12)

        table = self._build_table(roster)
        stats = self._build_stats(roster)
        # 渲染后触发一次滚动事件,滑块几何立即生效
        self._kick_thumb_geometry()

        return ft.Column([
            header_row,
            ft.Container(height=4),
            stats,
            ft.Container(height=8),
            ft.Container(
                content=table,
                expand=True,
                bgcolor=BG_CARD2,
                border_radius=16,
                padding=10,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,   # 圆角处内容裁剪
            ),
        ], spacing=8, expand=True)   # 外层不再纵向滚动:视口固定,滚动条常驻

    def _kick_thumb_geometry(self, attempt: int = 0):
        """渲染后微移 1px:触发 on_scroll 拿到真实几何,滑块立即按正确比例显示。
        控件挂载存在竞态,重试直到几何到达(实验证实 scroll_to 会触发 on_scroll)。"""
        import threading as _th
        if self._v_max > 1 or attempt >= 5:
            return
        try:
            self._vcol.scroll_to(offset=1, duration=50)
        except Exception:
            pass
        _th.Timer(0.5, lambda: self._kick_thumb_geometry(attempt + 1)).start()

    # ------------------------------------------------------------------
    # 统计条
    # ------------------------------------------------------------------
    def _build_stats(self, roster) -> ft.Control:
        members = roster.members
        total_people = len(members)
        total_sum = sum(m.total for m in members)
        neg = [m for m in members if m.total < 0]
        gens = sorted({m.generation for m in members if m.generation is not None},
                      reverse=True)
        dup_cnt = len(roster.duplicate_names)
        cards = [
            ("队员总数", str(total_people), PRIMARY),
            ("积分总量", format_score(total_sum), "#66BB6A"),
            ("届别数", str(len(gens)), GOLD),
            ("负分预警", str(len(neg)), "#FF8A80" if neg else "#66BB6A"),
            ("同名人员", str(dup_cnt), "#FF8A80" if dup_cnt else "#66BB6A"),
        ]
        row = []
        for label, value, color in cards:
            row.append(ft.Container(
                content=ft.Column([
                    ft.Text(value, size=20, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(label, size=11, color="#9AA3B5"),
                ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=12, bgcolor=BG_CARD, border_radius=12, expand=True,
            ))
        return ft.Row(row, spacing=10)

    # ------------------------------------------------------------------
    # 双模排序
    # ------------------------------------------------------------------
    def _switch(self, e):
        sel = list(e.control.selected)
        self.mode = sel[0] if sel else "generation"
        # 模式变更后必须整视图重渲染,否则表格仍按旧模式排序
        self.reload()

    def _acts_switch(self, e):
        sel = list(e.control.selected)
        self.acts_mode = sel[0] if sel else "split"
        self.reload()

    def _build_table(self, roster) -> ft.Control:
        if not roster.members:
            return ft.Container(
                content=ft.Text("主表中暂无队员数据(A 列为空)。", color="#9AA3B5"),
                padding=30, alignment=ft.alignment.center,
            )

        # 内存排序(只读,绝不写回)
        members = list(roster.members)
        if self.mode == "generation":
            # 第一优先 generation 降序,第二优先同届内汇总总分降序
            members.sort(key=lambda m: (-(m.generation if m.generation is not None
                                         else 10**9), -m.total))
        else:
            members.sort(key=lambda m: -m.total)

        rows: list[ft.DataRow] = []
        prev_gen: int | None = None
        first = True
        rank = 0
        # 按届别分组统计人数(用于标题行显示)
        gen_counts: dict = {}
        for m in members:
            gen_counts[m.generation] = gen_counts.get(m.generation, 0) + 1
        for m in members:
            if self.mode == "generation":
                g = m.generation
                if first or g != prev_gen:
                    # 届别标题行:每组(含第一组)都显示
                    glabel = "未标届" if g is None else f"第{g}届"
                    sep_cell = ft.DataCell(ft.Container(
                        content=ft.Text(
                            f"—— {glabel} ——(共 {gen_counts.get(g, 0)} 人)",
                            size=11, weight=ft.FontWeight.BOLD, color=GOLD),
                        alignment=ft.alignment.center, expand=True,
                    ))
                    filler = [ft.DataCell(ft.Container(width=1))
                              for _ in range(len(self._columns_for_table()) - 1)]
                    rows.append(ft.DataRow(cells=[sep_cell] + filler,
                                           color="#2A2416"))
                prev_gen = g
            first = False
            rank += 1
            rows.append(self._member_row(m, rank))

        def head(text: str, width: int | None = None,
                 align: ft.TextAlign | None = None) -> ft.DataColumn:
            t = ft.Text(text, size=12, weight=ft.FontWeight.BOLD, color="#9AA3B5",
                        text_align=align)
            return ft.DataColumn(ft.Container(content=t, width=width) if width else t)

        # 序号/姓名列再收紧(32px/92px);姓名表头左对齐,与下方名字对齐
        w_rank, w_name = 32, 92
        columns = [head("#", w_rank, ft.TextAlign.CENTER), head("姓名", w_name),
                   head("届别"), head("夜训周训"), head("升降旗"),
                   head("后勤部"), head("综办部")]
        if self.acts_mode == "merge":
            columns.append(head("活动"))
        else:
            columns += [head(name) for _, name in
                        getattr(self, "_activity_cols", [])]
        columns.append(head("汇总"))

        # 视口结构:横向滚动条钉在表格区底部;纵向滚动在内部 Column 上
        # (滚轮滚动,原生竖向滚动条隐藏)。竖向滑块是**纯布局兄弟节点**
        # (非覆盖层/非表内),钉在表格区右缘、全高、与横向滚动完全解耦——
        # 无论横滚到哪一列,它始终在原位可拖。
        self._v_px = 0.0      # 当前纵向滚动偏移(px)
        self._v_max = 0.0     # 最大滚动量 = 内容高 - 视口高
        self._v_vd = 0.0      # 视口高(px,来自滚动事件)
        self._vcol = ft.Column(
            [ft.DataTable(
                columns=columns,
                rows=rows,
                column_spacing=12,
                heading_row_height=38,
                data_row_min_height=36,
                data_row_max_height=42,
            )],
            scroll=ft.ScrollMode.HIDDEN,      # 内容可滚、原生滚动条隐藏
            on_scroll=self._v_on_scroll,
        )
        hscroll_area = ft.Container(
            content=ft.Row([self._vcol], scroll=ft.ScrollMode.AUTO),
            expand=True,
        )

        # 自制竖向滚动条:间隔/滑块/间隔 三段 expand 比例,
        # 几何来自 on_scroll 真实数据(已实验证实 scroll_to 会触发 on_scroll)
        self._s_top = ft.Container(expand=0)
        self._s_thumb = ft.Container(
            expand=1, bgcolor="#5B6B8C", width=8, border_radius=4,
        )
        self._s_bot = ft.Container(expand=0)
        self._vbar = ft.GestureDetector(
            content=ft.Container(
                content=ft.Column(
                    [self._s_top, self._s_thumb, self._s_bot],
                    spacing=0, expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.padding.only(top=14, bottom=20),
                expand=True,
            ),
            drag_interval=10,
            on_pan_update=self._v_drag,
        )
        return ft.Row([hscroll_area, self._vbar], spacing=6, expand=True)

    # ------------------------------------------------------------------
    # 自制竖向滚动条:事件与拖动
    # ------------------------------------------------------------------
    def _v_on_scroll(self, e):
        try:
            if e.max_scroll_extent is None or e.viewport_dimension is None:
                return
            self._v_max = max(float(e.max_scroll_extent), 0.0)
            self._v_px = min(max(float(e.pixels or 0), 0.0), self._v_max)
            self._v_vd = max(float(e.viewport_dimension), 1.0)
            self._sync_thumb()
        except Exception:
            pass

    def _sync_thumb(self):
        """按真实滚动几何更新滑块位置与可见性。"""
        try:
            show = self._v_max > 1
            self._vbar.visible = show
            if show:
                # 三段 expand 比例:上间隔 px / 滑块 视口高 / 下间隔 剩余
                self._s_top.expand = self._v_px
                self._s_bot.expand = max(self._v_max - self._v_px, 0.0001)
                self._s_thumb.expand = self._v_vd
            self.page.update()
        except Exception:
            pass

    def _v_drag(self, e):
        try:
            if self._v_max <= 1 or self._v_vd <= 1:
                return
            dy = float(e.delta_y or 0)
            if not dy:
                return
            # 轨道高 = 视口高 - 上下留白(14+20);滑块移动与滚动量按比例换算
            track_h = max(self._v_vd - 34.0, 60.0)
            delta_px = dy * (self._v_vd + self._v_max) / track_h
            self._v_px = min(max(self._v_px + delta_px, 0.0), self._v_max)
            self._vcol.scroll_to(offset=self._v_px, duration=0)
            self._sync_thumb()
        except Exception:
            pass

    def _columns_for_table(self) -> list[str]:
        """表头:#/姓名/届别/夜训周训/升降旗/后勤部/综办部 + 活动列(分列或合并) + 汇总。"""
        base = ["#", "姓名", "届别", "夜训周训", "升降旗", "后勤部", "综办部"]
        if self.acts_mode == "merge":
            return base + ["活动", "汇总"]
        return (base + [name for _, name in getattr(self, "_activity_cols", [])]
                + ["汇总"])

    def _member_row(self, m, rank: int) -> ft.DataRow:
        negative = m.total < 0
        duplicate = m.name in getattr(self, "_dup", set())

        def sc(col: int) -> str:
            v = _col_value(self.ctx, m, col)
            return format_score(v) if v is not None else "0"

        name_cell = ft.Text(
            m.name + ("  ⚠同名" if duplicate else ""),
            size=13,
            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
            weight=ft.FontWeight.BOLD if negative else ft.FontWeight.W_500,
            color=("#B71C1C" if negative else DUP_COLOR if duplicate else "#E8ECF5"),
        )
        cells = [
            # 序号列收紧(32px 居中,与表头一致)
            ft.DataCell(ft.Container(
                content=ft.Text(str(rank), size=12, color="#9AA3B5",
                                text_align=ft.TextAlign.CENTER),
                width=32,
            )),
            # 姓名列收紧(92px,超长省略号;左对齐与表头一致)
            ft.DataCell(ft.Container(content=name_cell, width=92)),
            ft.DataCell(ft.Text("未标届" if m.generation is None else f"第{m.generation}届",
                                size=12, color="#9AA3B5")),
            ft.DataCell(ft.Text(sc(2), size=12)),
            ft.DataCell(ft.Text(sc(3), size=12)),
            ft.DataCell(ft.Text(sc(4), size=12)),
            ft.DataCell(ft.Text(sc(5), size=12)),
        ]
        if self.acts_mode == "merge":
            # 合并模式:所有活动列合计为一列「活动」
            ev = 0.0
            for col, _n in getattr(self, "_activity_cols", []):
                v = _col_value(self.ctx, m, col)
                if v:
                    ev += v
            cells.append(ft.DataCell(ft.Text(format_score(ev), size=12)))
        else:
            # 分列模式:每个活动独立一列(与主表 G+ 列一一对应)
            for col, _ in getattr(self, "_activity_cols", []):
                cells.append(ft.DataCell(ft.Text(sc(col), size=12)))
        cells.append(ft.DataCell(ft.Text(format_score(m.total), size=13,
                                         weight=ft.FontWeight.BOLD,
                                         color="#B71C1C" if negative else "#E8ECF5")))
        return ft.DataRow(
            cells=cells,
            color=NEGATIVE_BG if negative else None,
        )


# ---------------------------------------------------------------------------
# 辅助:从主表读取各列值(按需缓存)
# ---------------------------------------------------------------------------

_DASH_CACHE: dict = {}


def _col_value(ctx, m, col: int):
    rows = _cached_rows(ctx)
    if rows is None:
        return None
    if m.row - 1 < len(rows) and col - 1 < len(rows[m.row - 1]):
        v = rows[m.row - 1][col - 1]
        try:
            f = float(v)
            return f if f == f else 0.0
        except (TypeError, ValueError):
            return 0.0
    return None


def _cached_rows(ctx) -> list | None:
    key = ctx.excel_path
    if _DASH_CACHE.get("path") != key:
        try:
            matrix = excel_io.read_matrix(key, max_col=256)
        except Exception:
            return None
        _DASH_CACHE["path"] = key
        _DASH_CACHE["rows"] = matrix
    return _DASH_CACHE.get("rows")
