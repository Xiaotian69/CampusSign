"""生成净化截图（仅使用占位/模拟数据，不含任何真实账号、密码、课程）。"""
import sys
import time
from pathlib import Path
from unittest.mock import patch

import app_config
from desktop_ui import App

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'screenshots'

# 占位课程，绝不使用真实课程
PLACEHOLDER_COURSES = {'高等数学（示例）': ['手机号'], '大学英语（示例）': ['手机号'], '数学建模（示例）': ['手机号']}
# 公开地点的示例网址（立信楼为 SCUFE 内置预设地点）
SAMPLE_MAP_URL = ('https://map.baidu.com/poi/%E5%B1%B1%E8%A5%BF%E8%B4%A2%E7%BB%8F%E5%A4%A7%E5%AD%A6'
                  '%E5%9D%9E%E5%9F%8E%E6%A0%A1%E5%8C%BA-%E7%AB%8B%E4%BF%A1%E6%A5%BC/@12533898.37,4523710.51,21z')


class ShotApp(App):
    def _build_style(self):
        # 固定按 100% 缩放渲染，截图尺寸与高分屏缩放无关。
        self.tk.call('tk', 'scaling', 96 / 72)
        super()._build_style()


def make_app(edition):
    profile = app_config.load_profile(edition)
    # Isolate all local configuration before construction, including locations
    # and previous results; replacing accounts afterwards is insufficient.
    with patch('desktop_ui.read_json', side_effect=lambda name, default: default):
        app = ShotApp(config={'edition': edition, 'dev_mode': True}, profile=profile)
    # 占位账号，绝不使用真实账号
    app.accounts = [{'username': '手机号', 'password': '••••••••', 'schoolid': ''}]
    app.refresh_accounts()
    app.show_page('home')
    app.deiconify()
    app.geometry('1100x760+0+0')
    app.update_idletasks()
    app.update()
    return app


def capture(window, name):
    from PIL import ImageGrab
    window.attributes('-topmost', True)
    window.lift()
    window.update()
    time.sleep(0.5)
    window.update()
    x = window.winfo_rootx()
    y = window.winfo_rooty()
    w = window.winfo_width()
    h = window.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(OUT / name)
    print('已保存', name, img.size)


def main():
    if sys.platform == 'win32':
        # 让 Tk 与截屏使用同一套物理像素坐标，避免高分屏下截图错位。
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    OUT.mkdir(exist_ok=True)

    # SCUFE 版
    scufe = make_app('scufe')
    scufe.show_page('home')
    capture(scufe, 'home_scufe.png')
    scufe.course_owners = dict(PLACEHOLDER_COURSES)
    scufe.course_picker.configure(values=list(PLACEHOLDER_COURSES))
    scufe.course.set('高等数学（示例）')
    scufe.update_course_hint()
    scufe.show_page('sign')
    capture(scufe, 'sign_scufe.png')
    scufe.show_page('places')
    capture(scufe, 'places_scufe.png')
    scufe.show_page('resources')
    capture(scufe, 'resources_scufe.png')
    scufe.attributes('-topmost', False)
    dialog = scufe.search_location()
    dialog.window.geometry('+40+40')
    dialog.coord_text.set(SAMPLE_MAP_URL)
    dialog.parse()
    capture(dialog.window, 'pick_scufe.png')
    scufe.destroy()

    # Generic 版
    generic = make_app('generic')
    generic.show_page('home')
    capture(generic, 'home_generic.png')
    generic.show_page('places')
    capture(generic, 'places_generic.png')
    generic.destroy()


if __name__ == '__main__':
    main()
