# -*- mode: python ; coding: utf-8 -*-
# CxSign 打包规格：单文件、无控制台窗口、内置 profiles 资源。
# 运行：pyinstaller CxSign.spec  （产物为 dist/CxSign.exe）

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import importlib.util

# Base sign-in can still build without course extras. With extras installed,
# include lazy imports and Selenium Manager for the course worker.
course_modules = ['third_party.course_engine']
optional_modules = ['selenium', 'openai', 'colorama', 'fontTools']
hidden = []
extra_data = [('third_party/course_engine/LICENSE', 'third_party/course_engine'),
              ('third_party/course_engine/README.md', 'third_party/course_engine'),
              ('third_party/course_engine/task/tool/font_dict.txt', 'third_party/course_engine/task/tool')]
for module in course_modules + optional_modules:
    if importlib.util.find_spec(module) is not None:
        hidden += collect_submodules(module)
if importlib.util.find_spec('selenium') is not None:
    extra_data += collect_data_files('selenium')

a = Analysis(
    ['desktop_ui.py'],
    pathex=[],
    binaries=[],
    datas=[('profiles', 'profiles')] + extra_data,
    hiddenimports=hidden,
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
