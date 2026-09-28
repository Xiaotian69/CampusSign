"""源码级功能冒烟测试：验证 SCUFE/Generic 的关键功能点（非 mock）。

覆盖：Edition 地点加载、首次须知判断、保存/读取配置往返、学习资料入口。
"""
import sys
from pathlib import Path

import app_config
import disclaimer
from desktop_core import DEFAULT_LOCATIONS, read_json, write_json
from desktop_ui import App


def check(label, condition):
    print(('  [PASS] ' if condition else '  [FAIL] ') + label)
    return condition


def test_scufe():
    print('[SCUFE Edition]')
    app = App(config={'edition': 'scufe', 'dev_mode': True}, profile=app_config.load_profile('scufe'))
    ok = True
    ok &= check('启动成功', True)
    ok &= check('山财预设地点为 3 个', len(app.locations) == 3)
    ok &= check('默认固定地点为立信楼', app.locations[0]['name'].endswith('立信楼'))
    ok &= check('Edition 显示为 SCUFE Edition', app.profile['display_name'] == 'SCUFE Edition')
    ok &= check('须知在 dev_mode 下跳过', not app.disclaimer_needed())
    ok &= check('学习资料页含山财资料卡', _resource_has(app, '山西财经大学历年期末资料'))
    app.destroy()
    return ok


def test_generic():
    print('[Generic Edition]')
    app = App(config={'edition': 'generic', 'dev_mode': True}, profile=app_config.load_profile('generic'))
    ok = True
    ok &= check('启动成功', True)
    ok &= check('默认地点为空', len(app.locations) == 0)
    ok &= check('不加载山财预设', all('山西财经大学' not in p['name'] for p in app.locations))
    ok &= check('Edition 显示为 Generic Edition', app.profile['display_name'] == 'Generic Edition')
    ok &= check('学习资料页不含山财专属卡片', not _resource_has(app, '山西财经大学历年期末资料'))
    app.destroy()
    return ok


def _resource_has(app, text):
    app.show_page('resources')
    app.update_idletasks()
    texts = []
    stack = [app.pages['resources']]
    while stack:
        w = stack.pop()
        try:
            t = w.cget('text')
            if t:
                texts.append(str(t))
        except Exception:
            pass
        stack.extend(w.winfo_children())
    return text in texts


def test_persistence_roundtrip():
    print('[配置保存/读取]')
    probe = '_smoke_probe.json'
    payload = {'course': '测试课程', 'location_mode': 'fixed', 'disclaimer_accepted': True}
    ok = True
    try:
        write_json(probe, payload)
        ok &= check('保存配置成功', True)
        ok &= check('重新读取一致', read_json(probe, {}) == payload)
    finally:
        Path(app_config.data_root() / probe).unlink(missing_ok=True)
        Path(app_config.data_root() / (probe + '.tmp')).unlink(missing_ok=True)
    return ok


def main():
    print('=' * 40)
    results = {
        'SCUFE': test_scufe(),
        'Generic': test_generic(),
        'persistence': test_persistence_roundtrip(),
    }
    print('=' * 40)
    print('源码冒烟结果：', results)
    sys.exit(0 if all(results.values()) else 1)


if __name__ == '__main__':
    main()
