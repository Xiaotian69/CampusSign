"""CxSign 发行包构建脚本。

用法：python build_release.py

流程：
1. 用 PyInstaller 按 CxSign.spec 打包出单个 CxSign.exe（核心代码完全共用）。
2. 组装 SCUFE / Generic 两个发行目录（仅 config.json 的 edition 不同）。
3. 打包成 zip，并生成 RELEASE_CONTENTS_*.txt 内容清单供检查。
"""
import json
import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from importlib.metadata import distribution
from app_config import CONTACT_EMAIL, REPO_URL

ROOT = Path(__file__).resolve().parent
VERSION = '1.0.0'
DIST = ROOT / 'dist'
RELEASE = ROOT / 'release'

EDITIONS = {
    'SCUFE': {'edition': 'scufe', 'dev_mode': False},
    'Generic': {'edition': 'generic', 'dev_mode': False},
}


def build_exe():
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / 'build' / 'pyinstaller-cache'))
    subprocess.run(
        [sys.executable, '-m', 'PyInstaller', 'CxSign.spec', '--noconfirm', '--clean'],
        cwd=ROOT, check=True, env=env,
    )
    exe = DIST / 'CxSign.exe'
    if not exe.exists():
        raise RuntimeError('打包失败：未找到 dist/CxSign.exe')
    return exe


def assemble(exe):
    # Never remove an earlier package or a user's saved configuration.
    if not RELEASE.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('发行目录必须位于项目目录内')
    for name in EDITIONS:
        for suffix in ('', '.zip'):
            if (RELEASE / f'CxSign-v{VERSION}-{name}{suffix}').exists():
                raise FileExistsError('目标发行包已存在，请使用新的 --output 目录')
    for name, config in EDITIONS.items():
        folder = RELEASE / f'CxSign-v{VERSION}-{name}'
        folder.mkdir(parents=True)

        shutil.copy(exe, folder / 'CxSign.exe')
        (folder / 'config.json').write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        shutil.copy(ROOT / 'user.example.json', folder / 'user.example.json')
        (folder / 'README.md').write_text(
            f'# CxSign v{VERSION} — {name} Edition\n\n'
            '解压到可写目录，双击 CxSign.exe 启动，无需安装 Python。\n\n'
            '首次使用阅读用户须知，添加自己的账号和地点；输入完整课程名后可先“仅查询”，再执行“查询并签到”。\n\n'
            'SCUFE 内置山财地点和资料入口；Generic 初始地点为空。两个版本均支持自定义地点。\n\n'
            '账号以明文保存在本机，登录凭据仅用于学习通请求。请勿分享包含个人配置的程序目录。\n\n'
            '仅支持位置签到；接口或网络变化可能影响功能，结果请在学习通核对。\n\n'
            '[使用教程](docs/USER_GUIDE.md) · [隐私说明](docs/PRIVACY.md) · [免责声明](docs/DISCLAIMER.md)\n\n'
            f'反馈：{REPO_URL}/issues · {CONTACT_EMAIL}\n\n'
            '反馈时请勿发送账号、密码、Cookie、Token、学号或私人配置。\n', encoding='utf-8')
        for filename in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md'):
            shutil.copy(ROOT / filename, folder / filename)
        (folder / 'docs').mkdir()
        for filename in ('USER_GUIDE.md', 'PRIVACY.md', 'DISCLAIMER.md'):
            shutil.copy(ROOT / 'docs' / filename, folder / 'docs' / filename)
        licenses = folder / 'licenses'
        licenses.mkdir()
        runtime = ('aiohttp', 'aiohappyeyeballs', 'aiosignal', 'attrs', 'beautifulsoup4',
                   'frozenlist', 'idna', 'lxml', 'multidict', 'propcache', 'soupsieve',
                   'typing_extensions', 'yarl', 'packaging', 'setuptools', 'pyinstaller')
        for package in runtime:
            dist = distribution(package)
            for file in dist.files or ():
                if any(word in file.name.lower() for word in ('license', 'copying', 'notice')) and not file.name.endswith(('.py', '.pyc')):
                    source = Path(dist.locate_file(file))
                    if source.is_file():
                        destination = licenses / package / str(file).replace('..', '_')
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(source, destination)
        python_license = Path(sys.base_prefix) / 'LICENSE.txt'
        if not python_license.is_file():
            raise FileNotFoundError('缺少 Python 运行时许可证')
        shutil.copy(python_license, licenses / 'PYTHON-LICENSE.txt')

        zip_path = RELEASE / f'CxSign-v{VERSION}-{name}.zip'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(folder.rglob('*')):
                if f.is_file():
                    zf.write(f, f.relative_to(RELEASE))

        contents = [str(p.relative_to(folder)) for p in sorted(folder.rglob('*')) if p.is_file()]
        (RELEASE / f'RELEASE_CONTENTS_{name.upper()}.txt').write_text(
            '\n'.join(contents) + '\n', encoding='utf-8')

    print('构建完成：')
    for name in EDITIONS:
        print(f'  {RELEASE / f"CxSign-v{VERSION}-{name}.zip"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='release', help='项目内的新发行目录（保留已有包）')
    args = parser.parse_args()
    RELEASE = (ROOT / args.output).resolve()
    if not RELEASE.is_relative_to(ROOT):
        parser.error('output 必须位于项目目录内')
    exe = build_exe()
    assemble(exe)
