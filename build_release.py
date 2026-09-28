"""CxSign 发行包构建脚本。

用法：python build_release.py

流程：
1. 用 PyInstaller 按 CxSign.spec 打包出单个 CxSign.exe（核心代码完全共用）。
2. 组装 SCUFE / Generic 两个发行目录（仅 config.json 的 edition 不同）。
3. 打包成 zip，并生成 RELEASE_CONTENTS_*.txt 内容清单供检查。
"""
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = '1.0.0'
DIST = ROOT / 'dist'
RELEASE = ROOT / 'release'

EDITIONS = {
    'SCUFE': {'edition': 'scufe', 'dev_mode': False},
    'Generic': {'edition': 'generic', 'dev_mode': False},
}


def build_exe():
    subprocess.run(
        [sys.executable, '-m', 'PyInstaller', 'CxSign.spec', '--noconfirm', '--clean'],
        cwd=ROOT, check=True,
    )
    exe = DIST / 'CxSign.exe'
    if not exe.exists():
        raise RuntimeError('打包失败：未找到 dist/CxSign.exe')
    return exe


def assemble(exe):
    for name, config in EDITIONS.items():
        folder = RELEASE / f'CxSign-v{VERSION}-{name}'
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)

        shutil.copy(exe, folder / 'CxSign.exe')
        (folder / 'config.json').write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        shutil.copy(ROOT / 'user.example.json', folder / 'user.example.json')
        shutil.copy(ROOT / 'README.md', folder / 'README.md')

        zip_path = RELEASE / f'CxSign-v{VERSION}-{name}.zip'
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(folder.rglob('*')):
                if f.is_file():
                    zf.write(f, f.relative_to(RELEASE))

        contents = [str(p.relative_to(folder)) for p in sorted(folder.rglob('*')) if p.is_file()]
        (RELEASE / f'RELEASE_CONTENTS_{name}.txt').write_text(
            '\n'.join(contents) + '\n', encoding='utf-8')

    print('构建完成：')
    for name in EDITIONS:
        print(f'  {RELEASE / f"CxSign-v{VERSION}-{name}.zip"}')


if __name__ == '__main__':
    exe = build_exe()
    assemble(exe)
