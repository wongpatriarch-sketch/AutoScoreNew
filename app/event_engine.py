"""模块四:活动积分结算引擎 —— 动态表单、文本解析、积分计算、Excel 落盘。

动态卡片:
- 训练卡片:可增删,N >= 0(支持全部删空)
- 彩排卡片:可增删,M >= 1(仅剩 1 张时禁止删除)
- 正式活动卡片:单例固定 1 张
"""

import flet as ft

from ghd import history_ops
from ghd.constants import CHIEF_MAX_COUNT
from ghd.name_parser import find_unknown, parse_names
from ghd.roster import parse_roster
from ghd.scoring import EventForm, RoundCard
from ghd.utils import format_score

from .theme import BG_CARD, BG_CARD2, GOLD, PRIMARY
from .widgets import (confirm_dialog, duration_options, info, names_field, snackbar,
                      warn)


class EventEngineView:
    def __init__(self, page: ft.Page, ws):
        self.page = page
        self.ws = ws          # Workspace(提供 guard_excel / handle_write_error / ctx)

        self.f_name = ft.TextField(label="活动名称（必填）", hint_text="如：国庆出旗",
                                   border_radius=10, expand=True)
        self.f_chief = names_field(f"主教官（1~{CHIEF_MAX_COUNT} 位，必填）",
                                   hint_text="多位人名用 ， 、 空格 分隔")
        self.f_formal_duration = ft.Dropdown(
            label="活动时长", options=duration_options(), value="1",
            dense=True, border_radius=10, width=200,
        )
        self.f_formal_attendees = names_field("参加（正式出旗人员）")
        self.f_field_duty = names_field("场务（可为空）")

        self.training_cards: list[dict] = []
        self.rehearsal_cards: list[dict] = []
        self.training_box = ft.Column(spacing=10)
        self.rehearsal_box = ft.Column(spacing=10)

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def render(self) -> ft.Control:
        # 默认 1 张彩排卡片
        if not self.rehearsal_cards:
            self._add_card("rehearsal")
        self._refresh_cards()

        return ft.Column(
            [
                self._header_card(),
                ft.Row(
                    [
                        ft.Column([self._training_section()], spacing=10, expand=True),
                        ft.Column([self._rehearsal_section()], spacing=10, expand=True),
                    ],
                    spacing=16,
                ),
                self._formal_card(),
                ft.Container(height=4),
                self._submit_bar(),
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _header_card(self) -> ft.Control:
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, color=PRIMARY),
                    ft.Text("活动积分结算引擎", size=17, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.Text("主教官每位 +2.0 · 场务固定 +0.5 · 训练/彩排/出旗按 1 小时 = 1.0 分",
                            size=11, color="#9AA3B5"),
                ], spacing=8),
                self.f_name,
                self.f_chief,
            ], spacing=12),
            padding=20, bgcolor=BG_CARD2, border_radius=16,
        )

    # ------------------------------------------------------------------
    # 动态卡片区域
    # ------------------------------------------------------------------
    def _training_section(self) -> ft.Control:
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.DIRECTIONS_RUN, color=PRIMARY, size=18),
                    ft.Text("训练卡片（可增删，可全部删空）", size=13,
                            weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.ADD_CIRCLE, tooltip="新增训练卡片",
                                  icon_color=PRIMARY, on_click=self._add_training),
                ], spacing=8),
                self.training_box,
            ], spacing=10),
            padding=16, bgcolor=BG_CARD2, border_radius=16, expand=True,
        )

    def _rehearsal_section(self) -> ft.Control:
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.THEATER_COMEDY, color=GOLD, size=18),
                    ft.Text("彩排卡片（至少保留 1 张）", size=13, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.ADD_CIRCLE, tooltip="新增彩排卡片",
                                  icon_color=GOLD, on_click=self._add_rehearsal),
                ], spacing=8),
                self.rehearsal_box,
            ], spacing=10),
            padding=16, bgcolor=BG_CARD2, border_radius=16, expand=True,
        )

    def _formal_card(self) -> ft.Control:
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.FLAG_ROUNDED, color="#EF5350", size=18),
                    ft.Text("正式活动（固定，不可增删）", size=13, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.Container(width=200, content=self.f_formal_duration),
                ], spacing=8),
                self.f_formal_attendees,
                self.f_field_duty,
            ], spacing=10),
            padding=16, bgcolor=BG_CARD2, border_radius=16,
        )

    # ------------------------------------------------------------------
    # 卡片增删
    # ------------------------------------------------------------------
    def _add_training(self, e=None):
        self._add_card("training")

    def _add_rehearsal(self, e=None):
        self._add_card("rehearsal")

    def _add_card(self, kind: str) -> None:
        box = self.training_cards if kind == "training" else self.rehearsal_cards
        idx = len(box) + 1
        card = {
            "kind": kind,
            "index": ft.Text(f"第 {idx} 次{'训练' if kind == 'training' else '彩排'}",
                             size=12, weight=ft.FontWeight.BOLD, color=PRIMARY),
            "duration": ft.Dropdown(label="时长", options=duration_options(), value="1",
                                    dense=True, border_radius=10, width=160),
            "instructors": names_field("教官"),
            "attendees": names_field("参训"),
        }
        box.append(card)
        self._refresh_cards()
        # 关键:控件变更必须显式同步到窗口,否则界面无反应
        self.page.update()

    def _remove_card(self, kind: str, card: dict) -> None:
        box = self.training_cards if kind == "training" else self.rehearsal_cards
        if kind == "rehearsal" and len(box) <= 1:
            warn(self.page, "无法删除",
                 "彩排卡片数量下限为 1，仅剩最后 1 张时禁止删除。")
            return
        if card in box:
            box.remove(card)
        self._refresh_cards()
        # 关键:控件变更必须显式同步到窗口,否则界面无反应
        self.page.update()

    def _refresh_cards(self) -> None:
        for kind, box, cards in (("training", self.training_box, self.training_cards),
                                 ("rehearsal", self.rehearsal_box, self.rehearsal_cards)):
            box.controls.clear()
            for i, card in enumerate(cards, start=1):
                card["index"].value = f"第 {i} 次{'训练' if kind == 'training' else '彩排'}"
                box.controls.append(self._card_widget(kind, card))

    def _card_widget(self, kind: str, card: dict) -> ft.Control:
        color = PRIMARY if kind == "training" else GOLD
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    card["index"],
                    ft.Container(expand=True),
                    ft.Container(width=160, content=card["duration"]),
                    ft.IconButton(ft.Icons.REMOVE_CIRCLE_OUTLINE, tooltip="删除本卡片",
                                  icon_color="#EF5350",
                                  on_click=lambda e, k=kind, c=card: self._remove_card(k, c)),
                ], spacing=8),
                card["instructors"],
                card["attendees"],
            ], spacing=8),
            padding=14, bgcolor=BG_CARD, border_radius=12,
        )

    # ------------------------------------------------------------------
    # 解析、校验、生成预览
    # ------------------------------------------------------------------
    def _collect_form(self) -> EventForm:
        form = EventForm(name=(self.f_name.value or "").strip(),
                         chief_instructors=parse_names(self.f_chief.value or ""))
        for c in self.training_cards:
            form.training_cards.append(RoundCard(
                kind="training",
                duration=float(c["duration"].value or 0),
                instructors=parse_names(c["instructors"].value or ""),
                attendees=parse_names(c["attendees"].value or ""),
            ))
        for c in self.rehearsal_cards:
            form.rehearsal_cards.append(RoundCard(
                kind="rehearsal",
                duration=float(c["duration"].value or 0),
                instructors=parse_names(c["instructors"].value or ""),
                attendees=parse_names(c["attendees"].value or ""),
            ))
        form.formal_duration = float(self.f_formal_duration.value or 0)
        form.formal_attendees = parse_names(self.f_formal_attendees.value or "")
        form.field_duty = parse_names(self.f_field_duty.value or "")
        return form

    def _all_names(self, form: EventForm) -> list[str]:
        names: list[str] = list(form.chief_instructors)
        for c in form.training_cards + form.rehearsal_cards:
            names += c.instructors + c.attendees
        names += form.formal_attendees + form.field_duty
        # 去重保序
        seen, out = set(), []
        for n in names:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _submit(self, e=None):
        ws = self.ws
        form = self._collect_form()
        errs = form.validate()
        if errs:
            warn(self.page, "表单校验未通过", "\n".join("· " + x for x in errs))
            return

        # 预读花名册(A 列,过滤界别分隔行)
        try:
            roster = ws.ctx.roster()
        except Exception as ex:
            info(self.page, "读取花名册失败", str(ex))
            return

        unknown = find_unknown(self._all_names(form), roster.names)
        if unknown:
            # 生成预览前黄色预警:忽略该人员 或 修正为人名库中的队员
            self._unknown_dialog(form, unknown, roster)
            return
        self._preview(form, roster)

    def _unknown_dialog(self, form: EventForm, unknown: list[str], roster) -> None:
        """黄色预警:检测到未在名单库中的人名,提供【忽略该人员】或【修正】。"""
        options = sorted(roster.names)
        fix_dropdowns: dict[str, ft.Dropdown] = {}

        def build_fix_row(name: str) -> ft.Control:
            dd = ft.Dropdown(
                label=f"「{name}」修正为", options=[ft.dropdown.Option(o) for o in options],
                dense=True, border_radius=10, expand=True,
            )
            fix_dropdowns[name] = dd
            return dd

        fix_list = ft.Column([build_fix_row(n) for n in unknown], spacing=8,
                             scroll=ft.ScrollMode.AUTO, height=min(66 * len(unknown), 240))

        def do_ignore(e):
            self.page.close(dlg)
            self._strip_names(form, set(unknown))
            self._after_resolve(form, roster)

        def do_fix(e):
            mapping = {}
            for n, dd in fix_dropdowns.items():
                if dd.value:
                    mapping[n] = dd.value
            self.page.close(dlg)
            self._apply_fix(form, mapping)
            self._after_resolve(form, roster)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=GOLD, size=26),
                ft.Text("检测到未在名单库中的人名", size=15, weight=ft.FontWeight.BOLD),
            ], spacing=10),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("检测到以下人名未在名单库中：" + "、".join(unknown),
                            size=13, color=GOLD),
                    ft.Text("请选择【忽略该人员】或【修正为人名库中的队员】：",
                            size=12, color="#C9D1E3"),
                    fix_list,
                ], spacing=10, tight=True),
                width=460,
            ),
            scrollable=True,   # 内容过多时整体可上下滚动
            actions=[
                ft.TextButton("全部忽略该人员", on_click=do_ignore),
                ft.FilledButton("按下方映射修正", on_click=do_fix,
                                style=ft.ButtonStyle(bgcolor=PRIMARY, color="#0E1116")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
        )
        self.page.open(dlg)

    def _strip_names(self, form: EventForm, drop: set[str]) -> None:
        form.chief_instructors = [n for n in form.chief_instructors if n not in drop]
        for c in form.training_cards + form.rehearsal_cards:
            c.instructors = [n for n in c.instructors if n not in drop]
            c.attendees = [n for n in c.attendees if n not in drop]
        form.formal_attendees = [n for n in form.formal_attendees if n not in drop]
        form.field_duty = [n for n in form.field_duty if n not in drop]

    def _apply_fix(self, form: EventForm, mapping: dict[str, str]) -> None:
        def fix(lst: list[str]) -> list[str]:
            out = []
            for n in lst:
                out.append(mapping.get(n, n))
            # 再次去重保序
            seen, dedup = set(), []
            for n in out:
                if n not in seen:
                    seen.add(n)
                    dedup.append(n)
            return dedup
        form.chief_instructors = fix(form.chief_instructors)
        for c in form.training_cards + form.rehearsal_cards:
            c.instructors = fix(c.instructors)
            c.attendees = fix(c.attendees)
        form.formal_attendees = fix(form.formal_attendees)
        form.field_duty = fix(form.field_duty)

    def _after_resolve(self, form: EventForm, roster) -> None:
        errs = form.validate()
        if errs:
            warn(self.page, "表单校验未通过", "\n".join("· " + x for x in errs))
            return
        self._preview(form, roster)

    # ------------------------------------------------------------------
    # 预览确认 -> 原子写回
    # ------------------------------------------------------------------
    def _preview(self, form: EventForm, roster) -> None:
        scores = form.compute()
        # 同名预警:花名册中同名姓名,用 ERROR 色高亮
        dup_rows = [n for n in scores if len(roster.by_name.get(n, [])) > 1]
        if dup_rows:
            warn(self.page, "同名队员预警",
                 "以下姓名在花名册中存在同名数据，已用红色高亮标识，请确认无误后再提交：\n"
                 + "、".join(dup_rows))

        rows = sorted(scores.items(), key=lambda kv: -kv[1])
        table_rows = []
        for name, pts in rows:
            dup = len(roster.by_name.get(name, [])) > 1
            table_rows.append(ft.DataRow(cells=[
                # 固定宽 + 省略号:杜绝长姓名把表格撑出弹窗
                ft.DataCell(ft.Container(
                    content=ft.Text(name + ("  ⚠同名" if dup else ""), size=12,
                                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                    color="#FF8A80" if dup else "#E8ECF5",
                                    weight=ft.FontWeight.BOLD if dup else None),
                    width=170,
                )),
                ft.DataCell(ft.Text("花名册" if not dup else "⚠同名",
                                    size=11, color="#9AA3B5")),
                ft.DataCell(ft.Text(("+" if pts >= 0 else "") + format_score(pts),
                                    size=12, weight=ft.FontWeight.BOLD,
                                    color="#A5D6A7")),
            ]))

        table_h = min(46 * len(table_rows) + 56, 360)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"预览确认 —— {form.name}", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"主教官：{'、'.join(form.chief_instructors) or '—'}    "
                            f"训练 {len(form.training_cards)} 次 · 彩排 {len(form.rehearsal_cards)} 次    "
                            f"正式时长 {form.formal_duration:g} 小时",
                            size=12, color="#9AA3B5"),
                # 固定高度区域:纵向滚动套横向拖动 + 硬裁剪,内容框死在弹窗内
                    ft.Container(
                        content=ft.Column(
                            [ft.Row(
                                [ft.DataTable(
                                    columns=[ft.DataColumn(ft.Text("姓名")),
                                             ft.DataColumn(ft.Text("匹配")),
                                             ft.DataColumn(ft.Text("本次积分"))],
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
                        height=table_h, width=430,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,   # 越界内容硬裁剪
                    ),
                    ft.Text("确认后将在主表最右侧追加新列「" + form.name +
                            "」，汇总列自动重算为前面各列之和。⚠同名姓名仅落到首个同名行，请确认无误。",
                            size=11, color="#9AA3B5"),
                ], spacing=10, tight=True),
            ),
            scrollable=True,   # 弹窗内容整体可上下滚动(兜底)
            actions=[
                ft.TextButton("返回修改", on_click=lambda e: self.page.close(dlg)),
                ft.FilledButton("确认落盘", icon=ft.Icons.SAVE,
                                on_click=lambda e: self._commit(form, scores, dlg),
                                style=ft.ButtonStyle(bgcolor=PRIMARY, color="#0E1116")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
        )
        self.page.open(dlg)

    def _commit(self, form: EventForm, scores: dict[str, float], dlg) -> None:
        ws = self.ws
        if not ws.guard_excel():
            return
        self.page.close(dlg)
        try:
            tx = history_ops.commit_event(ws.ctx, form.name, scores)
        except Exception as ex:
            ws.handle_write_error(ex)
            return
        snackbar(self.page,
                 f"活动「{form.name}」已落盘（批次 {tx['batch_id']}，{len(scores)} 人）。"
                 "可在【历史撤销】中修改或撤销本批次。")
        # 重置表单
        self.f_name.value = ""
        self.f_chief.value = ""
        self.f_formal_attendees.value = ""
        self.f_field_duty.value = ""
        self.training_cards.clear()
        self.rehearsal_cards.clear()
        self._add_card("rehearsal")
        self._refresh_cards()
        self.page.update()

    def _submit_bar(self) -> ft.Control:
        return ft.Row([
            ft.Container(expand=True),
            ft.OutlinedButton("清空表单", icon=ft.Icons.RESTART_ALT,
                              on_click=self._reset),
            ft.FilledButton(
                "生成预览", icon=ft.Icons.PREVIEW_ROUNDED, on_click=self._submit,
                style=ft.ButtonStyle(bgcolor=PRIMARY, color="#0E1116",
                                     padding=ft.padding.symmetric(26, 14)),
            ),
            ft.Container(expand=True),
        ], spacing=12)

    def _reset(self, e=None):
        self.f_name.value = ""
        self.f_chief.value = ""
        self.f_formal_attendees.value = ""
        self.f_field_duty.value = ""
        self.training_cards.clear()
        self.rehearsal_cards.clear()
        self._add_card("rehearsal")
        self._refresh_cards()
        self.page.update()
