"""Project Hub:欢迎与启动窗口 —— 新建项目 / 打开项目 / 历史项目列表。"""

import datetime
import os
import sys
import traceback

import flet as ft

from ghd import excel_io, project, recent
from ghd.utils import file_signature

from .theme import BG_CARD, BG_CARD2, GOLD, PRIMARY
from .widgets import info, snackbar, warn


def _error_log_path() -> str:
    """错误日志:优先 exe/脚本同目录,失败回落用户目录。"""
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


def log_error(where: str, ex: Exception) -> None:
    """把处理器异常写入日志文件(便于无窗口模式下排查)。"""
    try:
        with open(_error_log_path(), "a", encoding="utf-8") as f:
            f.write(f"\n==== {datetime.datetime.now().isoformat()} [{where}] ====\n")
            f.write(traceback.format_exc())
    except OSError:
        pass


def show_error(page: ft.Page, where: str, ex: Exception) -> None:
    """可见错误上报:对话框 + 日志。杜绝"无反应"。"""
    log_error(where, ex)
    info(page, f"操作失败({where})",
         f"{type(ex).__name__}: {ex}\n\n详情已写入 ghd_score_error.log,请将日志内容反馈给开发者。")


class Hub:
    """欢迎页。"""

    def __init__(self, page: ft.Page, open_project_cb, picker: ft.FilePicker | None = None):
        self.page = page
        self.open_project_cb = open_project_cb   # 进入工作台的回调
        self.new_name = ft.TextField(
            label="项目名称", hint_text="如：2026秋季集训积分",
            border_radius=10, expand=True,
        )
        self.new_excel = ""     # 关联的主数据表格路径
        self.new_dir = ""       # 工程配置保存目录
        self._pending_mode = None
        # FilePicker 由入口统一创建并挂载,避免重复注册
        self._picker = picker or ft.FilePicker(on_result=self._on_pick)
        if picker is None:
            page.overlay.append(self._picker)
        else:
            self._picker.on_result = self._on_pick

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def render(self) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                [
                    self._brand_panel(),
                    ft.Container(width=24),
                    ft.Column(
                        [self._new_project_panel(), ft.Container(height=16), self._open_panel()],
                        expand=3,
                        spacing=0,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            padding=36,
            expand=True,
            bgcolor="#14161D",
            alignment=ft.alignment.center,
        )

    def _brand_panel(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.FLAG_ROUNDED, size=64, color=PRIMARY),
                    ft.Container(height=8),
                    ft.Text("GHD Score", size=30, weight=ft.FontWeight.BOLD),
                    ft.Text("国旗护卫队积分管理与统计工具", size=14, color="#9AA3B5"),
                    ft.Container(height=24),
                    ft.Text(
                        "开箱即用 · 项目工程制\n本地 Excel 双向绑定\n事务级历史与撤销",
                        size=13, color="#C9D1E3",
                        style=ft.TextStyle(height=1.9),
                    ),
                ],
                spacing=6,
            ),
            padding=30,
            bgcolor=BG_CARD,
            border_radius=20,
            width=280,
        )

    # ------------------------------------------------------------------
    # 新建项目
    # ------------------------------------------------------------------
    def _safe(self, where: str, fn):
        """处理器安全包装:任何异常可见上报,杜绝"无反应"。"""
        def run(e=None):
            try:
                fn(e)
            except Exception as ex:
                show_error(self.page, where, ex)
        return run

    def _new_project_panel(self) -> ft.Control:
        def pick_excel(e):
            self._pending_mode = "new_excel"
            self._picker.pick_files(
                dialog_title="关联总积分表格",
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xlsx"],
            )

        def init_template(e):
            if not self.new_name.value or not self.new_name.value.strip():
                warn(self.page, "请先输入项目名称", "初始化模板前请填写项目名称。")
                return
            self._pending_mode = "new_template"
            # flet 0.28.3:保存对话框为独立方法 save_file(不归 pick_files 管)
            self._picker.save_file(
                dialog_title="保存主数据表格",
                file_name=f"{self.new_name.value.strip()}_总积分.xlsx",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xlsx"],
            )

        def pick_dir(e):
            self._pending_mode = "new_dir"
            self._picker.get_directory_path(dialog_title="选择工程配置保存目录")

        def do_create(e):
            name = (self.new_name.value or "").strip()
            if not name:
                warn(self.page, "项目名称为必填", "请输入项目名称，如：2026秋季集训积分。")
                return
            if not self.new_excel:
                warn(self.page, "请关联主数据表格",
                     "请选择「关联本地已有表格」或「初始化新模板并绑定」。")
                return
            directory = self.new_dir or os.path.dirname(self.new_excel)
            # 提前探测目录可写性,失败立即给出可操作提示(而非等到落盘才报错)
            ok, msg = project.dir_writable(directory)
            if not ok:
                warn(self.page, "保存目录不可写", msg)
                return
            cfg_path = project.config_path_for(directory, name)
            if os.path.exists(cfg_path):
                # 同名工程文件已存在:提供 打开 / 删除重建 / 取消
                self._recreate_dialog(cfg_path, name, self.new_excel)
                return
            cfg = project.default_config(name, self.new_excel)
            project.save_config(cfg_path, cfg)
            self._enter(cfg_path)

        self._excel_text = ft.Text(
            "未选择（尚未绑定主数据表格）", size=12, color="#9AA3B5",
            overflow=ft.TextOverflow.ELLIPSIS, expand=True,
        )
        self._dir_text = ft.Text(
            "默认与主表格同目录", size=12, color="#9AA3B5",
            overflow=ft.TextOverflow.ELLIPSIS, expand=True,
        )
        self._do_create_impl = do_create

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row([
                        ft.Icon(ft.Icons.CREATE_NEW_FOLDER_ROUNDED, color=PRIMARY),
                        ft.Text("新建项目", size=17, weight=ft.FontWeight.BOLD),
                    ], spacing=8),
                    self.new_name,
                    ft.Row([
                        ft.FilledTonalButton("关联本地已有表格", icon=ft.Icons.LINK,
                                             on_click=self._safe("关联表格", pick_excel)),
                        ft.FilledTonalButton("初始化新模板并绑定", icon=ft.Icons.NOTE_ADD,
                                             on_click=self._safe("初始化模板", init_template)),
                    ], spacing=8),
                    self._excel_text,
                    ft.Row([
                        ft.OutlinedButton("工程配置保存目录…", on_click=self._safe("选择目录", pick_dir)),
                        self._dir_text,
                    ], spacing=10),
                    ft.FilledButton(
                        "创建并进入项目",
                        icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                        on_click=self._safe("创建项目", do_create),
                        style=ft.ButtonStyle(bgcolor=PRIMARY, color="#0E1116",
                                             padding=ft.padding.symmetric(18, 12)),
                    ),
                ],
                spacing=12,
            ),
            padding=22,
            bgcolor=BG_CARD2,
            border_radius=18,
        )

    # ------------------------------------------------------------------
    # 同名工程文件处理:打开已有 / 删除重建 / 取消
    # ------------------------------------------------------------------
    def _recreate_dialog(self, cfg_path: str, name: str, excel_path: str) -> None:
        """同名 .ghd.json 已存在时的三选对话框。

        说明:「从列表移除」等操作不会删除磁盘上的工程文件,
        因此同名重建会走到这里;Excel 数据文件不受任何影响。
        """
        old_ok = False
        note = ""
        try:
            old = project.load_config(cfg_path)
            old_excel = old.get("meta", {}).get("excel_path", "")
            old_ok = os.path.isfile(old_excel)
            if not old_ok:
                note = (f"\n\n注意:旧工程绑定的表格已不存在（{old_excel}），"
                        "只能删除重建。")
        except Exception:
            note = "\n\n注意:旧工程文件可能已损坏，建议删除重建。"

        def do_open(e=None):
            self.page.close(dlg)
            self._enter(cfg_path)

        def do_recreate(e=None):
            self.page.close(dlg)
            try:
                os.remove(cfg_path)
            except OSError as ex:
                show_error(self.page, "删除旧工程", ex)
                return
            # 顺带清理可能残留的占用锁(旧工程未正常退出时)
            project.release_lock(excel_path)
            cfg = project.default_config(name, excel_path)
            try:
                project.save_config(cfg_path, cfg)
            except Exception as ex:
                show_error(self.page, "创建项目", ex)
                return
            self._enter(cfg_path)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.FOLDER_SPECIAL_ROUNDED, color=GOLD, size=26),
                ft.Text("同名工程文件已存在", size=16, weight=ft.FontWeight.BOLD),
            ], spacing=10),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"发现同名工程文件：\n{cfg_path}", size=13, color="#C9D1E3"),
                    ft.Text("它包含旧工程的历史积分记录（流水日志）。"
                            "删除重建不会影响磁盘上的 Excel 数据文件。" + note,
                            size=12, color="#9AA3B5"),
                    ft.Text("可选择:打开已有工程继续使用 / 删除旧工程记录后重建（历史将清空）。",
                            size=12, color="#C9D1E3"),
                ], spacing=10, tight=True),
                width=470,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.close(dlg)),
                ft.FilledTonalButton("打开已有工程", icon=ft.Icons.FOLDER_OPEN,
                                     on_click=do_open, disabled=not old_ok),
                ft.FilledButton("删除重建(历史清空)", icon=ft.Icons.DELETE_SWEEP,
                                on_click=do_recreate,
                                style=ft.ButtonStyle(bgcolor="#B3261E", color="#FFFFFF")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
            scrollable=True,   # 内容过多时整体可上下滚动
        )
        self.page.open(dlg)

    # ------------------------------------------------------------------
    # 打开项目
    # ------------------------------------------------------------------
    def _open_panel(self) -> ft.Control:
        def browse(e):
            self._pending_mode = "open_browse"
            self._picker.pick_files(
                dialog_title="选择工程配置文件",
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
            )

        def clear_invalid(e):
            n = recent.clear_invalid()
            snackbar(self.page, f"已清除 {n} 个失效项目记录" if n else "没有失效项目记录")
            self.refresh()

        head = ft.Row([
            ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, color=PRIMARY),
            ft.Text("打开项目", size=17, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.TextButton("浏览工程文件…", icon=ft.Icons.FILE_OPEN,
                          on_click=self._safe("浏览工程", browse)),
            ft.TextButton("清除失效项", icon=ft.Icons.CLEANING_SERVICES,
                          on_click=self._safe("清除失效", clear_invalid)),
        ], spacing=8)

        self._recent_list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        panel = ft.Container(
            content=ft.Column([head, self._recent_list], spacing=10),
            padding=22,
            bgcolor=BG_CARD2,
            border_radius=18,
            expand=True,
        )
        self._fill_recent()
        return panel

    def _fill_recent(self) -> None:
        items = recent.list_recent()
        self._recent_list.controls.clear()
        if not items:
            self._recent_list.controls.append(
                ft.Container(
                    content=ft.Text("暂无历史项目 —— 从上方新建你的第一个工程",
                                    size=12, color="#7A8299"),
                    padding=14, alignment=ft.alignment.center,
                    bgcolor=BG_CARD, border_radius=12,
                )
            )
        for it in items:
            self._recent_list.controls.append(self._recent_row(it))

    def _recent_row(self, it: dict) -> ft.Control:
        exists = it.get("exists", False)
        color = "#C9D1E3" if exists else "#FF8A80"
        def load(e, _it=it):
            self._enter(_it["config_path"])
        def remove(e, _it=it):
            recent.remove_recent(_it["config_path"])
            snackbar(self.page, "已从历史列表移除（不删除磁盘上的工程文件与 Excel，"
                                "如需彻底删除请手动清理或重建时选择「删除重建」）")
            self.refresh()
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INSERT_DRIVE_FILE_ROUNDED,
                            color="#43A047" if exists else "#B0BEC5", size=20),
                    ft.Column([
                        ft.Text(it.get("name", "未命名"), size=14, weight=ft.FontWeight.BOLD,
                                color=color),
                        ft.Text(it.get("excel_path", ""), size=11, color="#8A93A8",
                                overflow=ft.TextOverflow.ELLIPSIS),
                    ], spacing=2, expand=True),
                    ft.Text(f"最后修改 {it.get('last_modified', '')}", size=11, color="#7A8299"),
                    ft.IconButton(ft.Icons.EDIT_OFF, tooltip="仅从列表移除(不删除工程文件)",
                                  on_click=remove,
                                  icon_color="#9AA3B5", icon_size=18),
                    ft.FilledTonalButton(
                        "载入" if exists else "失效", on_click=load if exists else None,
                        disabled=not exists, icon=ft.Icons.ROCKET_LAUNCH if exists else None,
                    ),
                ],
                spacing=10,
            ),
            padding=ft.padding.symmetric(14, 10),
            bgcolor=BG_CARD,
            border_radius=12,
        )

    # ------------------------------------------------------------------
    # 文件选择回调与进入
    # ------------------------------------------------------------------
    def _on_pick(self, e: ft.FilePickerResultEvent) -> None:
        try:
            self._on_pick_impl(e)
        except Exception as ex:
            show_error(self.page, "文件选择", ex)

    def _on_pick_impl(self, e: ft.FilePickerResultEvent) -> None:
        mode = self._pending_mode
        self._pending_mode = None
        if mode == "new_excel" and e.files:
            self.new_excel = e.files[0].path
            self._excel_text.value = self.new_excel
            self._excel_text.color = "#C9D1E3"
            # 即时探测目标目录可写性,提前暴露权限问题
            ok, msg = project.dir_writable(os.path.dirname(self.new_excel))
            if not ok:
                warn(self.page, "注意：该目录可能不可写", msg)
            self.page.update()
        elif mode == "new_template" and e.path:
            dest = e.path
            # 即时探测保存目录可写性,避免模板创建才失败
            ok, msg = project.dir_writable(os.path.dirname(dest))
            if not ok:
                warn(self.page, "保存目录不可写", msg)
                return
            try:
                excel_io.create_main_template(dest)
            except Exception as ex:
                info(self.page, "模板创建失败", str(ex))
                return
            self.new_excel = dest
            self._excel_text.value = f"已初始化模板：{dest}"
            self._excel_text.color = "#A5D6A7"
            self.page.update()
        elif mode == "new_dir" and e.path:
            ok, msg = project.dir_writable(e.path)
            if not ok:
                warn(self.page, "该目录不可写，未采用", msg)
                return
            self.new_dir = e.path
            self._dir_text.value = e.path
            self._dir_text.color = "#C9D1E3"
            self.page.update()
        elif mode == "open_browse" and e.files:
            self._enter(e.files[0].path)

    def _enter(self, config_path: str) -> None:
        """载入工程:占用检测 -> 加锁 -> 注册历史 -> 进入工作台。"""
        try:
            self._enter_impl(config_path)
        except Exception as ex:
            show_error(self.page, "进入工程", ex)

    def _enter_impl(self, config_path: str) -> None:
        cfg = project.load_config(config_path)
        excel_path = cfg["meta"].get("excel_path", "")
        if not os.path.isfile(excel_path):
            info(self.page, "绑定的 Excel 不存在",
                 f"工程绑定的主数据表格不存在：\n{excel_path}\n请检查文件是否被移动或删除。")
            return
        sig = file_signature(excel_path)
        cfg["meta"]["excel_signature"] = sig

        ok, msg = project.acquire_lock(excel_path)
        if not ok:
            self._blocked_dialog(config_path, excel_path, msg)
            return
        project.save_config(config_path, cfg)
        recent.add_recent(config_path, cfg["meta"].get("project_name", ""), excel_path)
        self.open_project_cb(config_path, cfg)

    def _blocked_dialog(self, config_path: str, excel_path: str, msg: str) -> None:
        """占用阻断:重试 / 强制解锁并继续(仅本软件锁) / 取消。

        残留锁常见于:上次窗口未走「返回欢迎页」就关闭(✕/强制结束/崩溃)。
        智能锁已能自动清理死进程残留;此对话框是兜底逃生口。
        """
        own_lock = "本软件" in msg or "残留锁" in msg

        def do_retry(e=None):
            self.page.close(dlg)
            self._enter(config_path)

        def do_force(e=None):
            self.page.close(dlg)
            project.release_lock(excel_path)
            self._enter(config_path)

        actions = [ft.TextButton("取消", on_click=lambda e: self.page.close(dlg))]
        if own_lock:
            actions.append(ft.FilledTonalButton("强制解锁并继续",
                                                icon=ft.Icons.LOCK_OPEN,
                                                on_click=do_force))
        actions.append(ft.FilledButton("重试检测", icon=ft.Icons.REFRESH,
                                       on_click=do_retry,
                                       style=ft.ButtonStyle(bgcolor=PRIMARY,
                                                            color="#0E1116")))

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.LOCK, color=GOLD, size=26),
                ft.Text("目标表格已被占用", size=16, weight=ft.FontWeight.BOLD),
            ], spacing=10),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(msg, size=13, color="#C9D1E3"),
                    ft.Text("严禁并发写入导致数据损坏。常见原因：\n"
                            "① 上次窗口未走「返回欢迎页」就关闭（✕/强制结束），残留了锁标志"
                            " —— 智能锁通常已自动清理，也可点【强制解锁并继续】；\n"
                            "② 确实还有另一个本软件窗口开着该工程 —— 请先关闭它；\n"
                            "③ 第三方 Office（WPS/Excel）正在编辑该表格 —— 请先关闭表格。",
                            size=12, color="#9AA3B5"),
                ], spacing=10, tight=True),
                width=470,
            ),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
            scrollable=True,
        )
        self.page.open(dlg)

    def refresh(self) -> None:
        self._fill_recent()
        self.page.update()
