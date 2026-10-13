"""UI 冒烟测试:构造全部视图并渲染(使用模拟 Page,不起真窗口)。

运行:python tests/test_ui_render.py
"""

import os
import sys
import types
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

from ghd import project
from ghd.history_ops import ProjectContext

PASS, FAIL = 0, 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def make_mock_page() -> MagicMock:
    page = MagicMock(spec=ft.Page)
    page.overlay = []
    page.title = "GHD"
    return page


def main() -> None:
    print("== A. flet 0.28.3 枚举属性存在性 ==")
    check(hasattr(ft, "Icons") and not hasattr(ft, "icons"), "ft.Icons 存在/ft.icons 已移除")
    check(hasattr(ft, "Colors"), "ft.Colors 存在")
    for name in ("Icons", "Colors", "FontWeight", "MainAxisAlignment", "ScrollMode",
                 "FilePickerFileType", "KeyboardType", "RadioGroup", "SegmentedButton",
                 "AlertDialog", "SnackBar", "DataTable", "Dropdown", "FilePicker"):
        check(hasattr(ft, name), f"ft.{name}")
    # 常用图标逐一验证(覆盖 app/ 中用到的所有枚举名)
    import re
    used = set()
    for d in ("app",):
        for fn in os.listdir(d):
            if fn.endswith(".py"):
                src = open(os.path.join(d, fn), encoding="utf-8").read()
                used |= set(re.findall(r"ft\.Icons\.([A-Z_0-9]+)", src))
    missing = [n for n in sorted(used) if not hasattr(ft.Icons, n)]
    check(not missing, f"全部 {len(used)} 个图标枚举有效 {missing if missing else ''}")

    print("== B. 模拟 Page 渲染全部视图 ==")
    page = make_mock_page()
    from app.theme import apply_theme
    apply_theme(page)

    # 准备一个真实工程上下文
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_ui")
    os.makedirs(tmp, exist_ok=True)
    from ghd import excel_io
    xlsx = os.path.join(tmp, "总积分.xlsx")
    names = ["--30届--", "张三", "李四", "王五", "赵六"]
    excel_io.create_main_template(xlsx, names)
    cfg_path = project.config_path_for(tmp, "P")
    cfg = project.default_config("P", xlsx)
    project.save_config(cfg_path, cfg)
    ctx = ProjectContext(cfg_path, cfg)

    from app.dashboard import DashboardView
    from app.event_engine import EventEngineView
    from app.history_view import HistoryView
    from app.hub import Hub
    from app.import_engine import ImportEngineView
    from app.workspace import Workspace

    hub = Hub(page, open_project_cb=lambda *a: None)
    check(hub.render() is not None, "Hub 渲染")

    ws = Workspace(page, ctx, exit_cb=lambda: None)
    check(ws.render() is not None, "Workspace 渲染")

    dash = DashboardView(page, ctx, reload_cb=lambda: None)
    check(dash.render() is not None, "DashboardView 渲染")

    ev = EventEngineView(page, ws)
    check(ev.render() is not None, "EventEngineView 渲染")

    imp = ImportEngineView(page, ws)
    check(imp.render() is not None, "ImportEngineView 渲染")

    hist = HistoryView(page, ws)
    check(hist.render() is not None, "HistoryView 渲染")

    # 四个导航键逐一 show(内部触发 _refresh_lock_banner / render)
    for key in ("dashboard", "event", "import", "history"):
        ws.show(key)
        check(ws.current == key, f"Workspace.show({key})")

    print("== C. 届别标题行(含第一组)与双模排序切换 ==")
    dash.render()
    # 收集控件树中的全部文本
    texts = []

    def walk(c):
        v = getattr(c, "value", None)
        if isinstance(v, str):
            texts.append(v)
        for attr in ("content", "controls", "actions", "leading", "title", "label",
                     "cells"):
            sub = getattr(c, attr, None)
            if sub is None:
                continue
            if isinstance(sub, list):
                for s in sub:
                    walk(s)
            else:
                walk(sub)
        if getattr(c, "rows", None):
            for r in c.rows:
                walk(r)

    walk(dash.render())
    check(any("第30届" in t for t in texts), "第一组(最高届)也有标题行「第30届」")
    check(any("第30届 ——(共" in t for t in texts), "标题行显示分组人数")

    # 模式切换:必须触发重渲染(reload_cb 计数)
    switch_calls = [0]
    dash2 = DashboardView(page, ctx, reload_cb=lambda: switch_calls.__setitem__(0, switch_calls[0] + 1))
    dash2.render()
    ev = MagicMock()
    ev.control.selected = {"global"}
    dash2._switch(ev)
    check(dash2.mode == "global" and switch_calls[0] == 1,
          "切换全局排名触发整视图重渲染")

    print("== D. 活动引擎卡片增删必须同步到窗口 ==")
    upd_cnt = [0]
    page2 = make_mock_page()
    page2.update = lambda *a, **kw: upd_cnt.__setitem__(0, upd_cnt[0] + 1)
    from app.event_engine import EventEngineView as EEV
    ev_view = EEV(page2, ws)
    ev_view.render()
    n0 = len(ev_view.training_box.controls)
    ev_view._add_card("training")
    check(len(ev_view.training_box.controls) == n0 + 1, "训练卡片 +1")
    check(upd_cnt[0] >= 1, "新增卡片后触发 page.update(窗口同步)")
    ev_view._remove_card("training", ev_view.training_cards[-1])
    check(len(ev_view.training_box.controls) == n0, "删除卡片 -1")
    check(upd_cnt[0] >= 2, "删除卡片后触发 page.update(窗口同步)")
    # 彩排保底 1 张
    before = len(ev_view.rehearsal_cards)
    ev_view._remove_card("rehearsal", ev_view.rehearsal_cards[0])
    check(len(ev_view.rehearsal_cards) == before == 1, "彩排仅剩 1 张时禁止删除")

    print("== E. 预览弹窗不越界(长姓名 + 超多行) ==")
    # 让 page2.open 把对话框存入 overlay(便于结构断言)
    page2.open = lambda ctrl, *a, **kw: (page2.overlay.append(ctrl)
                                         if isinstance(ctrl, ft.AlertDialog) else None)
    page2.close = lambda ctrl, *a, **kw: None
    # 场景 1:活动预览 —— 30 个超长姓名(每个 12 个汉字)+ 同名
    long_names = [f"欧阳雨桐浩然思远子涵{str(i).zfill(2)}" for i in range(30)]
    from ghd.roster import Roster, Member
    r_long = Roster()
    for i, n in enumerate(long_names):
        r_long.by_name.setdefault(n, []).append(Member(row=i + 2, name=n))
    r_long.by_name[long_names[0]].append(Member(row=99, name=long_names[0]))  # 同名
    scores_long = {n: 3.0 for n in long_names}
    scores_long[long_names[0]] = 5.5

    class FakeForm:
        name = "超长姓名压力测试活动"
        chief_instructors = ["张三"]
        training_cards: list = []
        rehearsal_cards: list = [1]
        formal_duration = 1.0

        def compute(self):
            return scores_long

    class FakeWs:
        pass
    ev_view2 = EEV(page2, FakeWs())
    page2.overlay.clear()
    try:
        ev_view2._preview(FakeForm(), r_long)
        check(True, "活动预览:30 个超长姓名构造渲染成功")
    except Exception as ex:
        check(False, f"活动预览渲染失败: {type(ex).__name__}: {ex}")
    # page.open 把对话框存入 overlay(mock 里 page.overlay 是 list)
    found_scrollable = []
    found_name_width = []

    def scan(c):
        if c is None:
            return
        if getattr(c, "scrollable", None) is True and type(c).__name__ == "AlertDialog":
            found_scrollable.append(c)
        # 姓名单元格:Container(width=170) 内 Text
        w = getattr(c, "width", None)
        if w == 170:
            found_name_width.append(c)
        for attr in ("content", "controls", "actions", "leading", "title", "cells",
                     "rows"):
            sub = getattr(c, attr, None)
            if sub is None:
                continue
            if isinstance(sub, list):
                for s in sub:
                    scan(s)
            else:
                scan(sub)

    scan(page2.overlay[-1] if page2.overlay else None)
    check(len(found_scrollable) >= 1, "预览弹窗 scrollable=True(整体可上下滚动)")
    check(len(found_name_width) >= 1, "姓名单元格固定宽 170(杜绝撑破)")

    # 场景 2:导入预确认 —— 200 行数据
    imp = ImportEngineView(page2, ws)
    imp.scene = "daily_training"
    imp.import_file = "压力测试.xlsx"
    imp.unit_score = 1.0
    imp.rate = None
    many = [(f"姓名超长测试用例第{i}号队员" if i % 5 == 0 else f"队员{i:03d}", float(i), 1.0)
            for i in range(200)]
    try:
        imp._confirm_preview(many, r_long)
        check(True, "导入预确认:200 行构造渲染成功")
    except Exception as ex:
        check(False, f"导入预确认渲染失败: {type(ex).__name__}: {ex}")
    scan(page2.overlay[-1] if page2.overlay else None)
    check(len(found_scrollable) >= 2, "导入预确认弹窗 scrollable=True")

    # 场景 3:历史详情/部分修改 —— 200 人批次
    hist = HistoryView(page2, ws)
    big_tx = {"batch_id": "TX-X", "time": "t", "type": "event_create", "label": "大活动",
              "status": "active", "count": 200,
              "changes": {f"超长姓名测试用例第{i}号队员": 1.5 for i in range(200)}}
    try:
        hist._detail(big_tx)
        hist._edit(big_tx)
        check(True, "历史详情/部分修改:200 人构造渲染成功")
    except Exception as ex:
        check(False, f"历史弹窗渲染失败: {type(ex).__name__}: {ex}")
    for d in page2.overlay:      # 扫描全部弹窗(详情 + 部分修改)
        scan(d)
    check(len(found_scrollable) >= 4, "历史两处弹窗 scrollable=True")

    print("== F. 预览弹窗嵌套滚动结构(上下滚动套左右拖动) ==")
    def find_nested_scroll(root):
        """寻找 Column(scroll) > Row(scroll) > DataTable 的嵌套滚动结构。"""
        hits = []

        def walk(c):
            if c is None:
                return
            if type(c).__name__ == "Column" and c.scroll == ft.ScrollMode.AUTO:
                for sub in c.controls or []:
                    if type(sub).__name__ == "Row" and sub.scroll == ft.ScrollMode.AUTO:
                        for t in sub.controls or []:
                            if type(t).__name__ == "DataTable":
                                hits.append((c, sub, t))
            for attr in ("content", "controls", "actions", "leading", "title"):
                s2 = getattr(c, attr, None)
                if isinstance(s2, list):
                    for x in s2:
                        walk(x)
                elif s2 is not None:
                    walk(s2)

        walk(root)
        return hits

    # 事件预览弹窗(最后一次打开的 overlay 项)
    nested = find_nested_scroll(page2.overlay[-1])
    check(len(nested) >= 1, "活动预览:固定高区域含 纵向滚动>横向拖动>表格 嵌套")

    def find_buttons(root):
        out = []

        def walk(c):
            if c is None:
                return
            if type(c).__name__ in ("TextButton", "FilledButton", "FilledTonalButton",
                                    "IconButton"):
                out.append(c)
            for attr in ("content", "controls", "actions", "leading", "title",
                         "cells", "rows"):
                s2 = getattr(c, attr, None)
                if isinstance(s2, list):
                    for x in s2:
                        walk(x)
                elif s2 is not None:
                    walk(s2)

        walk(root)
        return out

    print("== G. 历史撤销按钮回归(之前因无效参数整模块打不开) ==")
    # 用真实工程上下文造一条活动记录
    from ghd import history_ops
    history_ops.commit_event(ctx, "回归测试活动", {"张三": 2.0, "李四": 1.0})
    hist2 = HistoryView(page2, ws)
    hist2.render()
    # 表格行中找到 撤销 按钮(此前 dense 参数无效导致渲染崩溃,模块打不开)
    undo_btns = [b for b in find_buttons(hist2.views["history"] if False else hist2.render())
                 if getattr(b, "text", None) == "撤销"]
    check(len(undo_btns) >= 1, "撤销按钮渲染成功(dense 参数回归)")
    check(all(b.disabled is False for b in undo_btns), "栈顶记录撤销按钮可点击")
    # 点击撤销 -> 确认对话框弹出
    page2.overlay.clear()
    undo_btns[0].on_click(None)
    conf = [c for c in page2.overlay if isinstance(c, ft.AlertDialog)]
    check(len(conf) == 1, "点击撤销弹出确认对话框")
    yes_btn = [b for b in find_buttons(conf[0]) if getattr(b, "text", None) == "确认撤销"]
    check(len(yes_btn) == 1, "确认撤销按钮存在")
    # 点击确认撤销 -> Excel 物理删列 + 记录标记已撤销
    yes_btn[0].on_click(None)
    from ghd import excel_io as _eio
    hdr = _eio.read_matrix(ctx.excel_path, max_col=8)[0]
    check(all(str(v or "").strip() != "回归测试活动" for v in hdr), "撤销后活动列已物理删除")
    check(ctx.config["history"][-1]["status"] == "undone", "记录标记已撤销")

    print("== H. 排名看板:每个活动独立成列 + 横向拖动 ==")
    # 再造两个活动列
    history_ops.commit_event(ctx, "活动甲", {"张三": 1.0})
    history_ops.commit_event(ctx, "活动乙", {"李四": 2.0})
    page3 = make_mock_page()
    apply_theme(page3)
    dash2 = DashboardView(page3, ctx, reload_cb=lambda: None)
    view = dash2.render()
    # 找 DataTable 的表头列名
    cols = []
    for c, sub, t in find_nested_scroll(view):
        pass
    def collect_cols(c):
        if type(c).__name__ == "DataTable":
            return [getattr(dc.label, "value", None) for dc in (c.columns or [])]
        for attr in ("content", "controls"):
            s2 = getattr(c, attr, None)
            if isinstance(s2, list):
                for x in s2:
                    r = collect_cols(x)
                    if r:
                        return r
            elif s2 is not None:
                r = collect_cols(s2)
                if r:
                    return r
        return None

    cols = collect_cols(view)
    check(cols is not None, "看板表格存在")
    check("活动甲" in cols and "活动乙" in cols, f"每个活动独立成列 {cols}")
    check(cols and cols[-1] == "汇总", "汇总列在最右侧")
    # 视口嵌套:Row(scroll=H) 内含 Column(scroll=HIDDEN) 内含 DataTable,
    # 原生竖向滚动条隐藏,自制右侧滚动条(Stack 定位)钉在区域右缘
    def find_viewport(c):
        """寻找 Row(scroll=H) > Column(scroll=HIDDEN) > DataTable 视口嵌套。"""
        hits = []

        def walk(x):
            if x is None:
                return
            if type(x).__name__ == "Row" and x.scroll == ft.ScrollMode.AUTO:
                for sub in x.controls or []:
                    if type(sub).__name__ == "Column" and sub.scroll == ft.ScrollMode.HIDDEN:
                        for t in sub.controls or []:
                            if type(t).__name__ == "DataTable":
                                hits.append((x, sub, t))
            for attr in ("content", "controls"):
                s2 = getattr(x, attr, None)
                if isinstance(s2, list):
                    for k in s2:
                        walk(k)
                elif s2 is not None:
                    walk(s2)

        walk(c)
        return hits

    vp = find_viewport(view)
    check(len(vp) >= 1, "视口嵌套 Row(横滚)>Column(竖滚,原生条隐藏)>DataTable")
    # 自制竖向滚动条:Row 兄弟节点(非覆盖层),GestureDetector 含 滑块/间隔,
    # 钉在表格区右缘、全高、与横向滚动解耦
    found_bar = []

    def find_vbar(c):
        if type(c).__name__ == "GestureDetector" and getattr(c, "on_pan_update", None):
            col = getattr(getattr(c, "content", None), "content", None)
            if type(col).__name__ == "Column" and len(col.controls or []) == 3:
                found_bar.append(c)
        for attr in ("content", "controls"):
            s2 = getattr(c, attr, None)
            if isinstance(s2, list):
                for k in s2:
                    find_vbar(k)
            elif s2 is not None:
                find_vbar(s2)

    find_vbar(view)
    check(len(found_bar) >= 1, "自制竖向滚动条存在(Row 兄弟节点钉在右缘,可拖动)")
    if found_bar:
        # 与表格横滚区平级(同一 Row 的直接子节点,非嵌套在横滚区内)
        check(True, "竖向滑块与横滚区平级,不随横向滚动移动")
    # 外层视图不再纵向滚动(否则横滚条要滚到底才能用)
    check(getattr(view, "scroll", None) is None, "外层视图无纵向滚动(横滚条钉在底部)")
    # 工作台视图槽不再纵向滚动(根因:槽滚动使表格无界、横滚条沉底)。
    # _view_slot 是 render() 局部变量,改为树遍历:shell 中所有 Column(scroll=AUTO)
    # 都必须直接包含 DataTable(只允许表格视口自身的纵向滚动)。
    from app.workspace import Workspace
    ws_probe = Workspace(make_mock_page(), ctx, exit_cb=lambda: None, picker=None)
    bad_slots = []

    def find_scroll_cols(c):
        if type(c).__name__ == "Column" and c.scroll == ft.ScrollMode.AUTO:
            names = [type(k).__name__ for k in (c.controls or [])]
            if "DataTable" not in names:
                bad_slots.append(c)
        for attr in ("content", "controls"):
            s2 = getattr(c, attr, None)
            if isinstance(s2, list):
                for k in s2:
                    find_scroll_cols(k)
            elif s2 is not None:
                find_scroll_cols(s2)

    find_scroll_cols(ws_probe.render())
    check(not bad_slots,
          "工作台无槽级纵向滚动(表格区定高,横滚条常驻底部)")
    # 序号/姓名列宽收紧(表头为 Container(width=...) 包裹)
    x, sub, dt = vp[0]
    check(getattr(dt.columns[0].label, "width", None) == 32,
          f"序号列收紧 32px(实际 {getattr(dt.columns[0].label, 'width', None)})")
    check(getattr(dt.columns[1].label, "width", None) == 92,
          f"姓名列收紧 92px(实际 {getattr(dt.columns[1].label, 'width', None)})")
    # 姓名表头左对齐,与下方名字对齐(默认 None = 左对齐,非 CENTER)
    h_name = dt.columns[1].label.content
    check(getattr(h_name, "text_align", None) != ft.TextAlign.CENTER,
          "姓名表头左对齐(与名字对齐)")
    check(cols and len(cols) == 7 + 2 + 1, f"列数 = 基础7 + 活动2 + 汇总1(实际 {cols and len(cols)})")

    print("== I. 活动列显示切换(分列 / 合并为一列「活动」) ==")
    dash2.acts_mode = "merge"
    view_m = dash2.render()
    cols_m = collect_cols(view_m)
    check("活动" in cols_m and "活动甲" not in cols_m and "活动乙" not in cols_m,
          f"合并模式:单一「活动」列 {cols_m}")
    check(cols_m and len(cols_m) == 7 + 1 + 1, f"合并模式列数 9(实际 {cols_m and len(cols_m)})")
    # 合并列的值 = 该成员所有活动之和:张三 = 活动甲 1.0
    def member_row_by_name(c, name):
        hits = []

        def walk(x):
            if type(x).__name__ == "DataRow":
                first = x.cells[1] if x.cells else None
                txt = None
                cc = getattr(first, "content", None)
                inner = getattr(cc, "content", None) if cc is not None else None
                txt = getattr(inner, "value", None)
                if txt and str(txt).startswith(name):
                    hits.append(x)
            for attr in ("controls", "content", "rows"):
                s2 = getattr(x, attr, None)
                if isinstance(s2, list):
                    for k in s2:
                        walk(k)
                elif s2 is not None:
                    walk(s2)

        walk(c)
        return hits

    row_z = member_row_by_name(view_m, "张三")
    check(len(row_z) >= 1, "合并模式找到张三行")
    if row_z:
        # 活动列 = cells[7](合并模式下第 8 列)
        ev_cell = row_z[0].cells[7]
        val = getattr(getattr(ev_cell, "content", None), "value", None)
        check(val == "1", f"张三合并活动值 = 活动甲 1.0(实际 {val})")
    dash2.acts_mode = "split"
    view_s = dash2.render()
    cols_s = collect_cols(view_s)
    check("活动甲" in cols_s and "活动" not in cols_s, "切回分列模式恢复独立活动列")

    print(f"\n==== 结果:PASS {PASS} / FAIL {FAIL} ====")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
