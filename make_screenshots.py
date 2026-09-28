"""生成净化截图（仅使用占位/模拟数据，不含任何真实账号、密码、课程）。"""
from pathlib import Path
from unittest.mock import patch

import app_config
from desktop_ui import App

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'screenshots'


def make_app(edition):
    profile = app_config.load_profile(edition)
    # Isolate all local configuration before construction, including locations
    # and previous results; replacing accounts afterwards is insufficient.
    with patch('desktop_ui.read_json', side_effect=lambda name, default: default):
        app = App(config={'edition': edition, 'dev_mode': True}, profile=profile)
    # 占位账号，绝不使用真实账号
    app.accounts = [{'username': '手机号', 'password': '••••••••', 'schoolid': ''}]
    app.refresh_accounts()
    app.show_page('home')
    app.deiconify()
    app.geometry('1100x760')
    app.update_idletasks()
    app.update()
    return app


def capture(app, name):
    from PIL import ImageGrab
    x = app.winfo_rootx()
    y = app.winfo_rooty()
    w = app.winfo_width()
    h = app.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(OUT / name)
    print('已保存', name)


def main():
    OUT.mkdir(exist_ok=True)

    # SCUFE 版
    scufe = make_app('scufe')
    scufe.show_page('home')
    scufe.update()
    capture(scufe, 'home_scufe.png')
    scufe.show_page('places')
    scufe.update()
    capture(scufe, 'places_scufe.png')
    scufe.show_page('resources')
    scufe.update()
    capture(scufe, 'resources_scufe.png')
    scufe.destroy()

    # Generic 版
    generic = make_app('generic')
    generic.show_page('home')
    generic.update()
    capture(generic, 'home_generic.png')
    generic.show_page('places')
    generic.update()
    capture(generic, 'places_generic.png')
    generic.destroy()


if __name__ == '__main__':
    main()
