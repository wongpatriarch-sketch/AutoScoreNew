"""模块五/六/七:批量考勤与部门分导入引擎(通用向导)。

- 日常训练考勤:严格「姓名」「总次数」列,B 列 + F 列增量累加
- 升降旗考勤:严格「姓名」「总次数」列,倍率单选(日常 0.5 / 节假日 1.0),C 列 + F 列
- 部门积分:智能夹心提取(姓名…总积分),后勤 D 列 / 综办 E 列 + F 列,单次互斥锁
"""

import os

import flet as ft

from ghd import history_ops, import_parsers
from ghd.constants import FLAG_DUTY_RATES
from ghd.utils import format_score

from .theme import BG_CARD, BG_CARD2, GOLD, PRIMARY
from .widgets import info, snackbar, warn

_SCENE_META = {
    "flag_duty": {"title": "升降旗考勤导入", "icon": ft.Icons.WB_TWILIGHT,
                  "tx": "flag_duty", "col_label": "C 列（升降旗）"},
    "daily_training": {"title": "日常训练考勤导入", "icon": ft.Icons.DIRECTIONS_RUN,
                       "tx": "daily_training", "col_label": "B 列（夜训周训）"},
    "logistics": {"title": "后勤部积分导入", "icon": ft.Icons.INVENTORY,
                  "tx": "department", "col_label": "D 列（后勤部）"},
    "comprehensive": {"title": "综办部积分导入", "icon": ft.Icons.ASSIGNMENT_TURNED_IN,
                      "tx": "department", "col_label": "E 列（综办部）"},
}


class ImportEngineView:
    def __init__(self, page: ft.Page, ws):
        self.page = page
        self.ws = ws
        self.scene = None
        self.parsed: list[tuple[str, float]] = []
        self.import_file = ""
        self.rate = None          # 升降旗倍率
        self.unit_score = 1.0     # 日常训练单次分值
        # FilePicker 由入口统一管理(Workspace 持有)
        self._picker = ws.picker
        self._dept_btns: dict[str, ft.Control] = {}

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def render(self) -> ft.Control:
        return ft.Column(
            [
                self._header(),
                self._flag_duty_card(),
                self._daily_card(),
                self._dept_card(),
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _header(self) -> ft.Control:
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, color=PRIMARY),
                ft.Column([
                    ft.Text("批量考勤与部门分导入引擎", size=17, weight=ft.FontWeight.BOLD),
                    ft.Text("统合外部表格导入与解析 · 增量累加写回 · 原子事务可撤销",
                            size=11, color="#9AA3B5"),
                ], spacing=2, expand=True),
            ], spacing=10),
            padding=18, bgcolor=BG_CARD2, border_radius=16,
        )

    # ------------------------------------------------------------------
    # 卡片
    # ------------------------------------------------------------------
    def _flag_duty_card(self) -> ft.Control:
        return self._scene_card(
            "flag_duty",
            desc="导入升降旗考勤表（外部专职考勤员提供）。列名必须严格匹配「姓名」「总次数」；"
                 "解析成功后选择积分倍率：日常升降旗单次 0.5 分 / 节假日升降旗单次 1.0 分。",
            btn="导入升降旗考勤表…",
        )

    def _daily_card(self) -> ft.Control:
        self._unit_field = ft.TextField(
            label="单次训练分值", value="1", width=140, dense=True,
            border_radius=10, keyboard_type=ft.KeyboardType.NUMBER,
            tooltip="1 次训练 = 1 分（可修改）",
        )
        return self._scene_card(
            "daily_training",
            desc="导入日常训练考勤模板（列名必须严格匹配「姓名」「总次数」）。",
            btn="导入日常训练考勤表…",
            extra=ft.Row([
                self._unit_field,
                ft.Text("分 / 次（可修改，默认 1 次 = 1 分）", size=11, color="#9AA3B5"),
            ], spacing=10),
        )

    def _dept_card(self) -> ft.Control:
        state = self.ws.ctx.config.get("state", {})
        self._dept_btns = {}
        btn_logi = self._dept_btn("logistics", state.get("is_logistics_imported"))
        btn_comp = self._dept_btn("comprehensive", state.get("is_comprehensive_imported"))
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.CORPORATE_FARE, color=GOLD, size=18),
                    ft.Text("部门专职积分导入（单次互斥锁）", size=13,
                            weight=ft.FontWeight.BOLD),
                ], spacing=8),
                ft.Text(
                    "智能夹心提取：首列严格匹配「姓名」、尾列严格匹配「总积分」，中间 0~N 列明细自动忽略。"
                    "单个项目生命周期内每个部门仅可导入一次；成功落盘后入口锁定。",
                    size=11, color="#9AA3B5",
                ),
                ft.Row([btn_logi, btn_comp], spacing=10),
            ], spacing=10),
            padding=16, bgcolor=BG_CARD2, border_radius=16,
        )

    def _dept_btn(self, scene: str, locked: bool) -> ft.Control:
        meta = _SCENE_META[scene]
        btn = ft.FilledTonalButton(
            ("已导入 · 入口锁定" if locked else f"{meta['title']}…"),
            icon=ft.Icons.LOCK if locked else ft.Icons.UPLOAD_FILE,
            disabled=locked,
            on_click=lambda e, s=scene: self._start(s),
            tooltip=("该部门积分已导入。如需修改，请前往【历史记录】撤销上一次操作后重新导入"
                     if locked else None),
        )
        if locked:
            btn.style = ft.ButtonStyle(color="#7A8299")
        return btn

    def _scene_card(self, scene: str, desc: str, btn: str,
                    extra: ft.Control | None = None) -> ft.Control:
        meta = _SCENE_META[scene]
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(meta["icon"], color=PRIMARY, size=18),
                    ft.Text(meta["title"], size=13, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.Text(f"写入 {meta['col_label']} + F 列（汇总）· 增量累加",
                            size=11, color="#9AA3B5"),
                ], spacing=8),
                ft.Text(desc, size=11, color="#9AA3B5"),
                extra or ft.Container(height=0),
                ft.Row([
                    ft.FilledTonalButton(btn, icon=ft.Icons.FILE_OPEN,
                                         on_click=lambda e, s=scene: self._start(s)),
                ], spacing=8),
            ], spacing=10),
            padding=16, bgcolor=BG_CARD2, border_radius=16,
        )

    # ------------------------------------------------------------------
    # 文件选择与解析
    # ------------------------------------------------------------------
    def _start(self, scene: str) -> None:
        state = self.ws.ctx.config.get("state", {})
        if scene in ("logistics", "comprehensive"):
            key = "is_logistics_imported" if scene == "logistics" else "is_comprehensive_imported"
            if state.get(key):
                warn(self.page, "该部门积分已导入",
                     "该部门积分已导入。如需修改，请前往【历史记录】撤销上一次操作后重新导入。")
                return
        self.scene = scene
        self._picker.on_result = self._on_pick
        self._picker.pick_files(
            dialog_title=_SCENE_META[scene]["title"],
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )

    def _on_pick(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files or not self.scene:
            return
        path = e.files[0].path
        self.import_file = os.path.basename(path)
        try:
            if self.scene in ("flag_duty", "daily_training"):
                self.parsed = import_parsers.parse_count_sheet(path)
            else:
                self.parsed = import_parsers.parse_department_sheet(path)
        except Exception as ex:
            info(self.page, "文件解析失败",
                 f"{self.import_file}\n\n{ex}\n\n"
                 "请检查列名是否严格匹配（姓名 / 总次数 或 姓名 / 总积分）。")
            return
        self._rate_dialog()

    # ------------------------------------------------------------------
    # 倍率/分值选择(模态)
    # ------------------------------------------------------------------
    def _rate_dialog(self) -> None:
        if self.scene == "flag_duty":
            self._flag_rate_dialog()
        elif self.scene == "daily_training":
            try:
                self.unit_score = float(self._unit_field.value or 1)
            except ValueError:
                warn(self.page, "单次分值无效", "请输入数字格式的单次训练分值。")
                return
            self._preview()
        else:
            self._preview()

    def _flag_rate_dialog(self) -> None:
        radio = ft.RadioGroup(value="daily", content=ft.Column([
            ft.Radio(value="daily", label="日常升降旗（单次记 0.5 分）"),
            ft.Radio(value="holiday", label="节假日升降旗（单次记 1.0 分）"),
        ], spacing=6))

        def confirm(e):
            self.rate = FLAG_DUTY_RATES.get(radio.value, 0.5)
            self.page.close(dlg)
            self._preview()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("选择本次导入的积分倍率（必选）", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column([
                ft.Text(f"已解析 {len(self.parsed)} 行数据 · 文件：{self.import_file}",
                        size=11, color="#9AA3B5"),
                radio,
            ], spacing=12, tight=True), width=380),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.close(dlg)),
                ft.FilledButton("确定并生成预览", on_click=confirm,
                                style=ft.ButtonStyle(bgcolor=PRIMARY, color="#0E1116")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
        )
        self.page.open(dlg)

    # ------------------------------------------------------------------
    # 预览与异常名单处理
    # ------------------------------------------------------------------
    def _score_of(self, count: float) -> float:
        if self.scene == "flag_duty":
            return round(count * (self.rate or 0.5), 2)
        if self.scene == "daily_training":
            return round(count * self.unit_score, 2)
        return round(count, 2)   # 部门:总积分直接累加

    def _type_label(self) -> str:
        return {
            "flag_duty": "节假日升降旗" if (self.rate or 0.5) == 1.0 else "日常升降旗",
            "daily_training": "日常训练",
            "logistics": "后勤部积分",
            "comprehensive": "综办部积分",
        }[self.scene]

    def _preview(self) -> None:
        ws = self.ws
        try:
            roster = ws.ctx.roster()
        except Exception as ex:
            info(self.page, "读取主库花名册失败", str(ex))
            return

        rows = [(name, count, self._score_of(count)) for name, count in self.parsed]
        unknown = [n for n, _, _ in rows if n not in roster.names]

        if unknown:
            self._unknown_dialog(rows, unknown, roster)
            return
        self._confirm_preview(rows, roster)

    def _unknown_dialog(self, rows, unknown: list[str], roster) -> None:
        """异常预警:姓名不在主库,高亮标黄;忽略该人员 或 手动映射到主库姓名。"""
        options = sorted(roster.names)
        dds: dict[str, ft.Dropdown] = {}

        def row_w(name: str) -> ft.Control:
            dd = ft.Dropdown(label=f"「{name}」映射到", dense=True,
                             options=[ft.dropdown.Option(o) for o in options],
                             border_radius=10, expand=True)
            dds[name] = dd
            return dd

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=GOLD, size=26),
                ft.Text("检测到主库中不存在的人名", size=15, weight=ft.FontWeight.BOLD),
            ], spacing=10),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("以下人名未在主 Excel 花名册中：\n" + "、".join(unknown),
                            size=13, color=GOLD),
                    ft.Text("可选择【忽略该人员】（跳过录入），或手动映射到主库中的正确姓名：",
                            size=12, color="#C9D1E3"),
                    ft.Column([row_w(n) for n in unknown], spacing=8,
                              scroll=ft.ScrollMode.AUTO,
                              height=min(66 * len(unknown), 240)),
                ], spacing=10, tight=True),
                width=460,
            ),
            actions=[
                ft.TextButton("忽略该人员（跳过）",
                              on_click=lambda e: (self.page.close(dlg),
                                                  self._drop_unknown(rows, set(unknown),
                                                                     roster))),
                ft.FilledButton("按映射修正",
                                on_click=lambda e: (self.page.close(dlg),
                                                    self._map_unknown(rows, dds, roster))),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
            scrollable=True,   # 内容过多时整体可上下滚动
        )
        self.page.open(dlg)

    def _drop_unknown(self, rows, drop: set[str], roster) -> None:
        rows = [r for r in rows if r[0] not in drop]
        if not rows:
            warn(self.page, "没有可导入的数据", "忽略后无有效数据行。")
            return
        self._confirm_preview(rows, roster)

    def _map_unknown(self, rows, dds: dict[str, ft.Dropdown], roster) -> None:
        mapping = {n: dd.value for n, dd in dds.items() if dd.value}
        merged: dict[str, float] = {}
        for name, count, score in rows:
            target = mapping.get(name, name)
            merged[target] = round(merged.get(target, 0.0) + score, 2)
        new_rows = [(name, None, score) for name, score in merged.items()]
        self._confirm_preview(new_rows, roster, mapped=True)

    def _confirm_preview(self, rows, roster, mapped: bool = False) -> None:
        """预确认表格:姓名、总次数、类型、本次加分。"""
        table_rows = []
        for name, count, score in rows:
            dup = len(roster.by_name.get(name, [])) > 1
            unknown = name not in roster.names
            warn_row = dup or unknown
            table_rows.append(ft.DataRow(cells=[
                # 固定宽 + 省略号:杜绝长姓名把表格撑出弹窗
                ft.DataCell(ft.Container(
                    content=ft.Text(name + ("  ⚠同名" if dup else ""), size=12,
                                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                    color="#B71C1C" if warn_row else "#E8ECF5",
                                    weight=ft.FontWeight.BOLD if warn_row else None),
                    width=150,
                )),
                ft.DataCell(ft.Text("—" if count is None else format_score(count),
                                    size=12)),
                ft.DataCell(ft.Text(self._type_label() if not mapped else "按映射合并",
                                    size=11, color="#9AA3B5")),
                ft.DataCell(ft.Text("+" + format_score(score), size=12,
                                    weight=ft.FontWeight.BOLD, color="#A5D6A7")),
            ], color="#5A4A1E" if unknown else None))

        total = round(sum(r[2] for r in rows), 2)
        table_h = min(46 * len(table_rows) + 56, 360)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"预确认 —— {_SCENE_META[self.scene]['title']}",
                          size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"文件：{self.import_file} · 共 {len(rows)} 行 · 本批次合计 +{format_score(total)} 分"
                            f"（{'升降旗倍率 ' + format_score(self.rate) if self.scene == 'flag_duty' else '单次 ' + format_score(self.unit_score) + ' 分' if self.scene == 'daily_training' else '总积分直接累加'}）",
                            size=11, color="#9AA3B5"),
                    # 固定高度区域:纵向滚动套横向拖动 + 硬裁剪,内容框死在弹窗内
                    ft.Container(
                        content=ft.Column(
                            [ft.Row(
                                [ft.DataTable(
                                    columns=[ft.DataColumn(ft.Text("姓名")),
                                             ft.DataColumn(ft.Text("总次数")),
                                             ft.DataColumn(ft.Text("类型")),
                                             ft.DataColumn(ft.Text("本次加分"))],
                                    rows=table_rows,
                                    column_spacing=24,
                                    heading_row_height=36,
                                    data_row_min_height=38,
                                    data_row_max_height=42,
                                )],
                                scroll=ft.ScrollMode.AUTO,
                            )],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        height=table_h, width=450,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,   # 越界内容硬裁剪
                    ),
                    ft.Text("确认后增量写入主表（原值为空按 0 运算，严禁写 NaN），"
                            "汇总列自动重算为前面各列之和。",
                            size=11, color="#9AA3B5"),
                ], spacing=10, tight=True),
            ),
            scrollable=True,   # 弹窗内容整体可上下滚动(兜底)
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.close(dlg)),
                ft.FilledButton("确认导入", icon=ft.Icons.SAVE,
                                on_click=lambda e: self._commit(rows, dlg),
                                style=ft.ButtonStyle(bgcolor=PRIMARY, color="#0E1116")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
        )
        self.page.open(dlg)

    # ------------------------------------------------------------------
    # 提交
    # ------------------------------------------------------------------
    def _commit(self, rows, dlg) -> None:
        ws = self.ws
        if not ws.guard_excel():
            return
        self.page.close(dlg)
        deltas: dict[str, float] = {}
        for name, _count, score in rows:
            deltas[name] = round(deltas.get(name, 0.0) + score, 2)
        meta = _SCENE_META[self.scene]
        try:
            tx = history_ops.commit_batch(
                ws.ctx, meta["tx"], meta["title"], deltas,
                target_col=import_parsers.target_col_for_scenes(self.scene),
                file=self.import_file,
                rate=self.rate if self.scene == "flag_duty" else None,
                unit_score=self.unit_score if self.scene == "daily_training" else None,
                department=self.scene if self.scene in ("logistics", "comprehensive") else None,
                stack_key=(f"dept:{self.scene}"
                           if self.scene in ("logistics", "comprehensive")
                           else None),
            )
        except Exception as ex:
            ws.handle_write_error(ex)
            return
        label = ("若不慎导入重复文件，请前往【历史撤销】模块一键撤销本批次操作。")
        snackbar(self.page,
                 f"已导入 {len(deltas)} 人（批次 {tx['batch_id']}）。{label}")
        # 部门导入后刷新锁状态(顶部状态条 + 入口按钮变灰)
        if self.scene in ("logistics", "comprehensive"):
            self.ws.show("import")
        else:
            self.scene = None
            self.parsed = []
            self.page.update()
