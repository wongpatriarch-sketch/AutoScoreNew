"""模块九:历史记录与撤销/修改中心(Revision & Undo Center)。

- 数据源:项目 .ghd.json 的 history 数组
- 线性版本栈:同一操作对象的所有记录构成栈,仅栈顶可修改/可撤销
- 操作 A:部分修改(Delta Update);操作 B:撤销(分支 1 / 分支 2)
"""

import flet as ft

from ghd import history_ops
from ghd.constants import STATUS_LABELS, ST_ACTIVE, ST_LOCKED, ST_UNDONE, TX_TYPE_LABELS
from ghd.utils import format_score

from .theme import BG_CARD, BG_CARD2, GOLD, PRIMARY
from .widgets import confirm_dialog, info, snackbar, warn

_STATUS_STYLE = {
    ST_ACTIVE: ("#66BB6A", "#153B1E"),
    ST_LOCKED: ("#9AA3B5", "#262B38"),
    ST_UNDONE: ("#EF9A9A", "#3B2222"),
}


class HistoryView:
    def __init__(self, page: ft.Page, ws):
        self.page = page
        self.ws = ws

    def render(self) -> ft.Control:
        cfg = self.ws.ctx.config
        history: list[dict] = cfg.get("history", [])

        head = ft.Row([
            ft.Icon(ft.Icons.HISTORY_ROUNDED, color=PRIMARY),
            ft.Column([
                ft.Text("历史流水与撤销中心", size=17, weight=ft.FontWeight.BOLD),
                ft.Text("线性版本栈 · 仅栈顶记录可修改/撤销 · 撤销将精准回滚 Excel 并流转状态",
                        size=11, color="#9AA3B5"),
            ], spacing=2, expand=True),
            ft.IconButton(ft.Icons.REFRESH, tooltip="刷新",
                          on_click=lambda e: self.ws.show("history")),
        ], spacing=10)

        if not history:
            return ft.Column([
                head,
                ft.Container(
                    content=ft.Text("暂无历史记录 —— 完成「活动结算」或「批量导入」后，"
                                    "所有生效批次将在此留痕。", color="#7A8299"),
                    padding=40, alignment=ft.alignment.center,
                    bgcolor=BG_CARD2, border_radius=16,
                ),
            ], spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)

        # 展示顺序:最新在前
        rows = []
        for tx in reversed(history):
            rows.append(self._tx_row(tx))

        table = ft.Container(
            content=ft.Row([ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("操作时间", size=12, weight=ft.FontWeight.BOLD,
                                          color="#9AA3B5")),
                    ft.DataColumn(ft.Text("操作类型", size=12, weight=ft.FontWeight.BOLD,
                                          color="#9AA3B5")),
                    ft.DataColumn(ft.Text("涉及人数", size=12, weight=ft.FontWeight.BOLD,
                                          color="#9AA3B5")),
                    ft.DataColumn(ft.Text("操作对象 / 关联活动", size=12,
                                          weight=ft.FontWeight.BOLD, color="#9AA3B5")),
                    ft.DataColumn(ft.Text("状态", size=12, weight=ft.FontWeight.BOLD,
                                          color="#9AA3B5")),
                    ft.DataColumn(ft.Text("操作", size=12, weight=ft.FontWeight.BOLD,
                                          color="#9AA3B5")),
                ],
                rows=rows,
                column_spacing=26,
                heading_row_height=40,
                data_row_min_height=44,
                data_row_max_height=52,
            )], scroll=ft.ScrollMode.AUTO),
            expand=True, bgcolor=BG_CARD2, border_radius=16, padding=10,
        )
        return ft.Column([head, table], spacing=12, expand=True,
                         scroll=ft.ScrollMode.AUTO)

    # ------------------------------------------------------------------
    # 行渲染
    # ------------------------------------------------------------------
    def _tx_row(self, tx: dict) -> ft.DataRow:
        status = tx.get("status", ST_LOCKED)
        color, bg = _STATUS_STYLE.get(status, ("#9AA3B5", "#262B38"))
        editable = status == ST_ACTIVE
        badge = ft.Container(
            content=ft.Text(STATUS_LABELS.get(status, status), size=11,
                            weight=ft.FontWeight.BOLD, color=color),
            padding=ft.padding.symmetric(10, 4), bgcolor=bg, border_radius=999,
        )
        delta_total = sum(tx.get("changes", {}).values())
        actions = ft.Row([
            ft.TextButton("详情", icon=ft.Icons.VISIBILITY,
                          on_click=lambda e, t=tx: self._detail(t)),
            ft.TextButton("修改", icon=ft.Icons.EDIT,
                          disabled=not editable,
                          tooltip="可修改" if editable else "已被更新的记录锁定,仅最新记录可修改",
                          on_click=lambda e, t=tx: self._edit(t)),
            ft.TextButton("撤销", icon=ft.Icons.UNDO,
                          disabled=not editable,
                          tooltip="可撤销" if editable else "已被更新的记录锁定,仅最新记录可撤销",
                          on_click=lambda e, t=tx: self._undo(t),
                          style=ft.ButtonStyle(color="#EF9A9A")),
        ], spacing=2, tight=True)

        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(tx.get("time", ""), size=12)),
            ft.DataCell(ft.Text(TX_TYPE_LABELS.get(tx.get("type"), tx.get("type", "")),
                                size=12)),
            ft.DataCell(ft.Text(str(tx.get("count", 0)), size=12)),
            ft.DataCell(ft.Column([
                ft.Text(tx.get("label", "—"), size=12, weight=ft.FontWeight.W_600),
                ft.Text(f"批次 {tx.get('batch_id', '')} · 净变化 "
                        f"{'+' if delta_total >= 0 else ''}{format_score(delta_total)}",
                        size=10, color="#7A8299"),
            ], spacing=1)),
            ft.DataCell(badge),
            ft.DataCell(actions),
        ])

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def _detail(self, tx: dict) -> None:
        changes: dict = tx.get("changes", {})
        rows = sorted(changes.items(), key=lambda kv: -abs(kv[1]))
        table_rows = [
            ft.DataRow(cells=[
                # 固定宽 + 省略号:杜绝长姓名把表格撑出弹窗
                ft.DataCell(ft.Container(
                    content=ft.Text(n, size=12, max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                    width=200,
                )),
                ft.DataCell(ft.Text(("+" if v >= 0 else "") + format_score(v),
                                    size=12,
                                    color="#A5D6A7" if v >= 0 else "#EF9A9A",
                                    weight=ft.FontWeight.BOLD)),
            ]) for n, v in rows
        ] or [ft.DataRow(cells=[ft.DataCell(ft.Text("（无分值变化）", size=12,
                                                color="#9AA3B5"))])]
        meta_lines = [f"批次：{tx.get('batch_id', '')}",
                      f"时间：{tx.get('time', '')}",
                      f"类型：{TX_TYPE_LABELS.get(tx.get('type'), '')}",
                      f"对象：{tx.get('label', '')}",
                      f"状态：{STATUS_LABELS.get(tx.get('status'), '')}"]
        for k in ("file", "rate", "unit_score", "editor"):
            if tx.get(k) is not None:
                meta_lines.append(f"{k}：{tx[k]}")
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("批次详情", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column([
                ft.Text("\n".join(meta_lines), size=11, color="#9AA3B5"),
                # 固定高度区域:纵向滚动套横向拖动 + 硬裁剪,内容框死在弹窗内
                ft.Container(
                    content=ft.Column(
                        [ft.Row(
                            [ft.DataTable(
                                columns=[ft.DataColumn(ft.Text("姓名")),
                                         ft.DataColumn(ft.Text("分值变化"))],
                                rows=table_rows, column_spacing=26,
                                heading_row_height=36,
                                data_row_min_height=38,
                                data_row_max_height=42,
                            )],
                            scroll=ft.ScrollMode.AUTO,
                        )],
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    width=360, height=min(46 * len(table_rows) + 56, 340),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ], spacing=10, tight=True)),
            actions=[ft.TextButton("关闭", on_click=lambda e: self.page.close(dlg))],
            shape=ft.RoundedRectangleBorder(radius=14),
            scrollable=True,   # 弹窗内容整体可上下滚动(兜底)
        )
        self.page.open(dlg)

    # ------------------------------------------------------------------
    # 操作 A:部分修改
    # ------------------------------------------------------------------
    def _edit(self, tx: dict) -> None:
        changes: dict = tx.get("changes", {})
        fields: dict[str, ft.TextField] = {}

        def field_for(name: str, old: float) -> ft.TextField:
            tf = ft.TextField(value=format_score(old), dense=True, border_radius=8,
                              keyboard_type=ft.KeyboardType.NUMBER, width=110)
            fields[name] = tf
            return tf

        rows = sorted(changes.items())
        table_rows = [
            ft.DataRow(cells=[
                # 固定宽 + 省略号:杜绝长姓名把表格撑出弹窗
                ft.DataCell(ft.Container(
                    content=ft.Text(n, size=12, max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                    width=170,
                )),
                ft.DataCell(ft.Text(format_score(v), size=12, color="#9AA3B5")),
                ft.DataCell(field_for(n, v)),
            ]) for n, v in rows
        ] or [ft.DataRow(cells=[ft.DataCell(ft.Text("（该批次无明细）", size=12,
                                                color="#9AA3B5"))])]

        def do_commit(e):
            new_scores: dict[str, float] = {}
            bad = []
            for name, tf in fields.items():
                try:
                    new_scores[name] = float(tf.value or 0)
                except ValueError:
                    bad.append(name)
            if bad:
                warn(self.page, "分值格式错误",
                     "以下人员的新分值不是数字：" + "、".join(bad))
                return
            self.page.close(dlg)
            self._commit_edit(tx, new_scores)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"部分修改 —— {tx.get('label', '')}", size=16,
                          weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column([
                ft.Text("自动加载该批次中所有成员当时的积分。提交时仅对有变动的人员"
                        "计算差值（新 - 旧）并增量写回活动列与 F 列汇总。",
                        size=11, color="#9AA3B5"),
                # 固定高度区域:纵向滚动套横向拖动 + 硬裁剪,内容框死在弹窗内
                ft.Container(
                    content=ft.Column(
                        [ft.Row(
                            [ft.DataTable(
                                columns=[ft.DataColumn(ft.Text("姓名")),
                                         ft.DataColumn(ft.Text("原分值")),
                                         ft.DataColumn(ft.Text("新分值"))],
                                rows=table_rows, column_spacing=24,
                                heading_row_height=36,
                                data_row_min_height=38,
                                data_row_max_height=46,
                            )],
                            scroll=ft.ScrollMode.AUTO,
                        )],
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    width=400, height=min(52 * len(table_rows) + 56, 360),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ], spacing=10, tight=True)),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.close(dlg)),
                ft.FilledButton("提交修改", on_click=do_commit,
                                style=ft.ButtonStyle(bgcolor=PRIMARY, color="#0E1116")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
            scrollable=True,   # 弹窗内容整体可上下滚动(兜底)
        )
        self.page.open(dlg)

    def _commit_edit(self, tx: dict, new_scores: dict[str, float]) -> None:
        ws = self.ws
        if not ws.guard_excel():
            return
        try:
            new_tx = history_ops.commit_edit(ws.ctx, tx, new_scores)
        except Exception as ex:
            ws.handle_write_error(ex)
            return
        snackbar(self.page,
                 f"修改已落盘（新批次 {new_tx['batch_id']}），原记录已锁定。"
                 f"本次净变化 {sum(new_tx['changes'].values()):+g} 分")
        ws.show("history")

    # ------------------------------------------------------------------
    # 操作 B:撤销
    # ------------------------------------------------------------------
    def _undo(self, tx: dict) -> None:
        ws = self.ws
        tx_type = tx.get("type")
        if tx_type == "event_create":
            msg = ("将从 F 列（汇总）精准扣除本批次全部分数，并物理删除该活动对应的整列"
                   "（右侧列自动左移）。")
        elif tx_type == "event_edit":
            msg = ("将按本记录的差值在活动列与 F 列执行反向扣减，"
                   "使数据恢复到上一个版本。")
        else:
            msg = ("将在对应积分列与 F 列反向扣除本批次分数；"
                   "部门积分批次撤销后将重新点亮对应导入入口。")
        msg += "\n\n该记录将被标记为「已撤销」，其上一级记录自动解除锁定。"

        def do_undo(e=None):
            if not ws.guard_excel():
                return
            try:
                history_ops.undo_tx(ws.ctx, tx)
            except Exception as ex:
                ws.handle_write_error(ex)
                return
            snackbar(self.page, f"批次 {tx.get('batch_id', '')} 已撤销，Excel 已精准回滚。")
            ws.show("history")

        confirm_dialog(self.page, f"撤销批次 {tx.get('batch_id', '')}", msg,
                       on_yes=do_undo, yes_text="确认撤销")
