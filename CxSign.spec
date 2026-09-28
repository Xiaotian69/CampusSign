# -*- mode: python ; coding: utf-8 -*-
# CxSign 打包规格：单文件、无控制台窗口、内置 profiles 资源。
# 运行：pyinstaller CxSign.spec  （产物为 dist/CxSign.exe）


a = Analysis(
    ['desktop_ui.py'],
    pathex=[],
    binaries=[],
    datas=[('profiles', 'profiles')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CxSign',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
