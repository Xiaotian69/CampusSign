"""exe 启动冒烟测试：启动两个发行版 exe，确认进程存活（不截图，避免隐私泄露）。"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / 'release'


def smoke(exe_path, edition):
    print(f'[启动] {edition} 版')
    proc = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
    time.sleep(6)
    alive = proc.poll() is None
    if not alive:
        print(f'[失败] {edition} 版 exe 启动后退出，退出码 {proc.returncode}')
        return False
    print(f'[存活] {edition} 版 exe 正常运行')
    proc.terminate()
    time.sleep(1)
    if proc.poll() is None:
        subprocess.run(['taskkill', '/F', '/IM', 'CxSign.exe'], capture_output=True)
    return True


def main():
    results = {
        'SCUFE': smoke(RELEASE / 'CxSign-v1.0.0-SCUFE' / 'CxSign.exe', 'SCUFE'),
        'Generic': smoke(RELEASE / 'CxSign-v1.0.0-Generic' / 'CxSign.exe', 'Generic'),
    }
    print('=' * 40)
    print('冒烟测试结果：', results)
    sys.exit(0 if all(results.values()) else 1)


if __name__ == '__main__':
    main()
