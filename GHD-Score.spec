# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置:GHD Score — 国旗护卫队积分管理与统计工具
# 用法:pyinstaller GHD-Score.spec
# 产物:dist/GHD-Score.exe
#
# 关键点:flet 0.28.3 桌面客户端位于 flet_desktop/app/(约 94MB Flutter 运行时),
# 运行时通过 flet_desktop.__file__ 同级的 app 目录查找 flet.exe,
# 因此必须把该目录作为数据文件打入包内,否则打包后启动报错。

import os

import flet_desktop

FLET_DESKTOP_APP = os.path.join(os.path.dirname(flet_desktop.__file__), "app")

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join("resources"), "resources"),
        (FLET_DESKTOP_APP, os.path.join("flet_desktop", "app")),
    ],
    hiddenimports=["flet_core", "flet_runtime", "flet_desktop"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="GHD-Score",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=".",
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
