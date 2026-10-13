"""驱动测试:复现 Hub「创建并进入项目」完整点击链路。

运行:python tests/test_hub_flow.py
"""

import os
import shutil
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

from ghd import project

TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_flow")
opened = []          # 记录 page.open 的对话框标题
opened_dlgs = []     # 记录弹出的对话框对象(用于触发其内部按钮)
updates = [0]
entered = []         # 记录 open_project_cb 是否被调用


def make_page() -> MagicMock:
    page = MagicMock(spec=ft.Page)
    page.overlay = []

    def _open(ctrl, *a, **kw):
        if isinstance(ctrl, ft.AlertDialog):
            # 标题可能是 Text 或 Row([Icon, Text])
            title = getattr(ctrl, "title", None)
            text = getattr(title, "value", None)
            if text is None and title is not None and getattr(title, "controls", None):
                for x in title.controls:
                    if isinstance(x, ft.Text):
                        text = x.value
                        break
            opened.append(f"dialog:{text}")
            opened_dlgs.append(ctrl)
        else:
            opened.append("<other>")
    page.open = _open
    page.close = lambda ctrl, *a, **kw: None

    def _update(*a, **kw):
        updates[0] += 1
    page.update = _update
    return page


def find_buttons(ctrl, out):
    """深度遍历控件树,收集全部按钮。"""
    if hasattr(ctrl, "on_click") and ctrl.on_click is not None:
        out.append(ctrl)
    for attr in ("content", "controls", "actions", "leading", "title"):
        sub = getattr(ctrl, attr, None)
        if sub is None:
            continue
        if isinstance(sub, list):
            for s in sub:
                find_buttons(s, out)
        else:
            find_buttons(sub, out)
    if hasattr(ctrl, "rows") and getattr(ctrl, "rows", None):
        for r in ctrl.rows:
            find_buttons(r, out)
    return out


def btn_label(b) -> str:
    c = getattr(b, "content", None)
    if isinstance(c, ft.Row) and c.controls:
        for x in c.controls:
            if isinstance(x, ft.Text):
                return x.value
    return getattr(b, "text", "") or "?"


def main() -> None:
    if os.path.isdir(TMP):
        shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    from ghd import excel_io
    xlsx = os.path.join(TMP, "测试_总积分.xlsx")
    excel_io.create_main_template(xlsx, ["张三", "李四"])

    page = make_page()
    from app.hub import Hub
    hub = Hub(page, open_project_cb=lambda p, c: entered.append(p))
    root = hub.render()

    # ---- 步骤 1:填项目名称,模拟「初始化新模板并绑定」保存对话框结果 ----
    hub.new_name.value = "测试项目"
    hub._pending_mode = "new_template"
    evt = MagicMock(path=xlsx, files=None)
    hub._on_pick(evt)
    print("绑定后 new_excel =", repr(hub.new_excel))
    assert hub.new_excel == xlsx, "绑定未生效"

    # ---- 步骤 2:找到「创建并进入项目」按钮并触发 ----
    btns = find_buttons(root, [])
    target = [b for b in btns if btn_label(b) == "创建并进入项目"]
    print(f"控件树中按钮: {[btn_label(b) for b in btns]}")
    assert target, "未找到创建按钮"
    try:
        target[0].on_click(None)
        print("on_click 执行完成(未抛异常)")
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[FAIL] on_click 抛出异常: {type(ex).__name__}: {ex}")
        sys.exit(1)

    print("弹出的对话框:", opened)
    print("page.update 次数:", updates[0])
    print("open_project_cb 触发:", entered)
    if entered:
        print("[PASS] 完整链路走通:创建 -> 加锁 -> 进入工作台")
    else:
        print("[FAIL] open_project_cb 未被调用")
        sys.exit(1)

    # ---- 步骤 3:Workspace 渲染(真实走一遍) ----
    cfg = project.load_config(entered[0])
    from ghd.history_ops import ProjectContext
    from app.workspace import Workspace
    ws = Workspace(page, ProjectContext(entered[0], cfg),
                   exit_cb=lambda: None, picker=MagicMock())
    try:
        r = ws.render()
        print("[PASS] Workspace 渲染成功")
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # ---- 步骤 4:异常路径 —— 处理器抛异常时必须弹出可见错误对话框 ----
    opened.clear()
    entered.clear()

    def boom(*a, **kw):
        raise TypeError("模拟:unexpected keyword argument 'save'")
    hub._picker.save_file = boom
    btns = find_buttons(root, [])
    target = [b for b in btns if btn_label(b) == "初始化新模板并绑定"]
    target[0].on_click(None)
    if any(str(o).startswith("dialog:操作失败") for o in opened):
        print(f"[PASS] 异常可见上报: {opened}")
    else:
        print(f"[FAIL] 异常被静默吞掉,弹窗: {opened}")
        sys.exit(1)

    # ---- 步骤 5:「知道了」按钮必须能关闭对话框(回归:NameError) ----
    from app.widgets import info
    closed = []
    page.close = lambda ctrl, *a, **kw: closed.append(type(ctrl).__name__)
    info(page, "测试标题", "测试消息")
    dlg_opened = [c for c in opened if str(c).startswith("dialog:测试标题")]
    assert dlg_opened, f"对话框未弹出: {opened}"
    # 找到对话框中的「知道了」按钮并点击
    ok_btns = []
    for it in page.overlay + opened and []:
        pass
    # info() 返回 None,重新构造并从返回值拿 dlg
    from app.widgets import alert_dialog
    dlg2 = alert_dialog(page, "测试标题2", "消息2")
    find_buttons(dlg2, ok_btns)
    zhidao = [b for b in ok_btns if getattr(b, "text", "") == "知道了"]
    assert zhidao, "未找到「知道了」按钮"
    zhidao[0].on_click(None)
    if "AlertDialog" in closed:
        print(f"[PASS] 「知道了」点击成功关闭对话框: closed={closed}")
    else:
        print(f"[FAIL] 「知道了」点击未生效: closed={closed}")
        sys.exit(1)

    # ---- 步骤 6:目录可写探针与 save_config 健壮性 ----
    from ghd import project as proj
    ok, msg = proj.dir_writable(TMP)
    assert ok, f"正常目录被误判不可写: {msg}"
    print("[PASS] 目录可写探针(可写目录)")
    ok2, msg2 = proj.dir_writable(os.path.join(TMP, "不存在的目录"))
    assert not ok2 and "不存在" in msg2, "不存在目录未被识别"
    print("[PASS] 目录可写探针(不存在目录)")
    # save_config:正常写 + 读取回验
    p1 = os.path.join(TMP, "工程A.ghd.json")
    proj.save_config(p1, proj.default_config("工程A", xlsx))
    assert proj.load_config(p1)["meta"]["project_name"] == "工程A"
    print("[PASS] save_config 原子写与回读")
    # save_config:唯一临时文件名(不再用固定 .tmp)
    import glob as _glob
    assert not _glob.glob(os.path.join(TMP, "工程A.ghd.json.tmp")), "仍残留固定 .tmp"
    print("[PASS] 临时文件名唯一化(防残留锁阻塞)")

    # ---- 步骤 7:同名工程三选(打开 / 删除重建 / 取消) ----
    opened.clear()
    entered.clear()
    # 模拟从工作台返回欢迎页(释放步骤 2 持有的锁)
    project.release_lock(xlsx)
    hub2 = Hub(page, open_project_cb=lambda p, c: entered.append(p))
    root2 = hub2.render()
    hub2.new_name.value = "测试项目"
    hub2._pending_mode = "new_template"
    hub2._on_pick(MagicMock(path=xlsx, files=None))
    # 再次创建同名 -> 应弹出三选对话框
    create_btn = [b for b in find_buttons(root2, []) if btn_label(b) == "创建并进入项目"]
    create_btn[0].on_click(None)
    assert any("同名工程文件已存在" in str(o) for o in opened), f"未弹出同名对话框: {opened}"
    dlg = opened_dlgs[-1]
    dbtns = {btn_label(b): b for b in find_buttons(dlg, [])}
    assert "打开已有工程" in dbtns and "删除重建(历史清空)" in dbtns and "取消" in dbtns, \
        f"三选按钮缺失: {list(dbtns)}"
    print("[PASS] 同名工程弹出三选对话框(打开/删除重建/取消)")

    # 取消:不进入工程
    n_before = len(entered)
    dbtns["取消"].on_click(None)
    assert len(entered) == n_before, "取消后仍进入了工程"
    print("[PASS] 取消不进入工程")

    # 打开已有工程:进入工程
    dbtns["打开已有工程"].on_click(None)
    assert len(entered) == n_before + 1, "打开已有工程未进入"
    assert os.path.isfile(entered[-1]), "工程文件路径无效"
    print("[PASS] 打开已有工程进入工作台")

    # 删除重建:旧 json 被删,新工程创建,残留锁被清理
    cfg_path2 = entered[-1]
    lock = project.excel_lock_path(xlsx)
    assert os.path.exists(lock), "前置:当前工程应持有锁"
    create_btn[0].on_click(None)
    dlg = opened_dlgs[-1]
    dbtns = {btn_label(b): b for b in find_buttons(dlg, [])}
    n_before = len(entered)
    dbtns["删除重建(历史清空)"].on_click(None)
    assert len(entered) == n_before + 1, "删除重建未进入新工程"
    assert os.path.isfile(cfg_path2), "重建后的工程文件不存在"
    new_cfg = project.load_config(cfg_path2)
    assert new_cfg["history"] == [], "重建后历史未清空"
    assert os.path.exists(lock), "重建后应重新持有锁"
    print("[PASS] 删除重建:历史清空、工程重建、锁正常流转")

    # 释放锁
    project.release_lock(xlsx)
    assert not os.path.exists(lock), "锁未释放"

    # ---- 步骤 8:智能锁 —— 死进程残留自动清理 / 活进程阻断 / 强制解锁 ----
    # 8a:死进程 PID(上上次窗口被强制关闭的残留) -> 自动清理并加锁成功
    lock = project.excel_lock_path(xlsx)
    with open(lock, "w", encoding="utf-8") as f:
        f.write('{"pid": 999999999, "time": "2020-01-01 00:00:00", "host": "X"}')
    ok, msg = project.acquire_lock(xlsx)
    assert ok, f"死进程残留锁未自动清理: {msg}"
    info2 = project.read_lock_info(lock)
    assert info2 and info2["pid"] == os.getpid(), "新锁未写入当前 PID"
    print(f"[PASS] 死进程残留锁自动清理并重建(PID {info2['pid']})")

    # 8b:旧版本格式锁(纯时间戳,无法解析) -> 视为残留,自动清理
    project.release_lock(xlsx)
    with open(lock, "w", encoding="utf-8") as f:
        f.write("2020-01-01 00:00:00")
    ok, msg = project.acquire_lock(xlsx)
    assert ok, f"旧版锁未自动清理: {msg}"
    print("[PASS] 旧版本格式锁自动清理")
    project.release_lock(xlsx)

    # 8c:活进程锁 -> 真实阻断(信息含 PID 与强制解锁提示)
    with open(lock, "w", encoding="utf-8") as f:
        f.write('{"pid": 12345, "time": "2026-10-02 12:00:00", "host": "X"}')
    from ghd import project as proj_mod
    orig_alive = proj_mod.is_pid_alive
    proj_mod.is_pid_alive = lambda pid: True     # 模拟持锁进程存活
    try:
        ok, msg = project.acquire_lock(xlsx)
        assert not ok and "本软件" in msg and "12345" in msg, f"活进程锁未阻断: {msg}"
        print("[PASS] 活进程锁真实阻断(含 PID 信息)")
    finally:
        proj_mod.is_pid_alive = orig_alive

    # 8d:阻断对话框提供【强制解锁并继续】,点击后清理并进入
    opened.clear()
    entered.clear()
    with open(lock, "w", encoding="utf-8") as f:
        f.write('{"pid": 12345, "time": "2026-10-02 12:00:00", "host": "X"}')
    hub3 = Hub(page, open_project_cb=lambda p, c: entered.append(p))
    hub3._blocked_dialog(entered_cfg := os.path.join(TMP, "测试项目.ghd.json"), xlsx, msg)
    d = opened_dlgs[-1]
    dbtns = {btn_label(b): b for b in find_buttons(d, [])}
    assert "强制解锁并继续" in dbtns and "重试检测" in dbtns, f"按钮缺失: {list(dbtns)}"
    proj_mod.is_pid_alive = lambda pid: False    # 模拟持锁进程已退出
    try:
        dbtns["强制解锁并继续"].on_click(None)
        assert len(entered) == 1, "强制解锁后未进入工程"
        print("[PASS] 强制解锁按钮:清理锁并进入工程")
    finally:
        proj_mod.is_pid_alive = orig_alive
    project.release_lock(xlsx)

    print("\n==== Hub 创建/同名/智能锁 全链路测试全部通过 ====")


if __name__ == "__main__":
    main()
