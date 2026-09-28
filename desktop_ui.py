"""CxSign 桌面端入口。打开窗口不提交签到。

界面层只负责展示与调度；签到网络逻辑保持独立于 ``desktop_core.py``，
本文件不修改任何签到请求字段。
"""
import asyncio
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser

import app_config
import disclaimer
from desktop_core import read_json, write_json, validate_location, run_batch


# ===== 主题色（浅色现代风） =====
BG = '#f5f6f8'
CARD = '#ffffff'
SIDEBAR = '#ffffff'
ACCENT = '#2f6bff'
ACCENT_DARK = '#2356d1'
TEXT = '#1f2430'
MUTED = '#8a919f'
BORDER = '#e6e8ee'

FONT = 'Microsoft YaHei UI'


# ===== 更新日志（与 CHANGELOG.md 保持一致） =====
CHANGELOG = [
    {
        'version': 'v1.0.0',
        'date': '2026-09',
        'sections': [
            ('新增', [
                '学习通位置签到（图形界面）',
                'SCUFE Edition / Generic Edition 双版本',
                '山西财经大学地点预设（立信楼 / 南院 / 修德楼）',
                '自定义地点的新增、编辑与删除',
                '首次启动用户须知',
                '学习资料入口',
                '帮助与更新日志页面',
            ]),
            ('优化', [
                '全新浅色界面与侧边导航',
                '账号与地点配置本地化保存',
            ]),
            ('修复', []),
        ],
    },
]


def merge_locations(presets, customs):
    """合并预设地点与用户自定义地点，同名时自定义覆盖预设。"""
    merged = {}
    for loc in presets:
        if loc.get('name'):
            merged[loc['name']] = dict(loc)
    for loc in customs:
        if loc.get('name'):
            merged[loc['name']] = dict(loc)
    return list(merged.values())


class App(tk.Tk):
    def __init__(self, config=None, profile=None):
        super().__init__()
        self.title(f'{app_config.APP_NAME} · 学习通位置签到 · v{app_config.APP_VERSION}')
        self.geometry('1100x760')
        self.minsize(920, 640)
        self.configure(bg=BG)

        self.config = config if config is not None else app_config.load_config()
        self.edition = self.config.get('edition', 'scufe')
        self.dev_mode = bool(self.config.get('dev_mode', False))
        self.profile = profile if profile is not None else app_config.load_profile(self.edition)

        self.accounts = read_json('user.json', [])
        self.custom_locations = read_json('locations.local.json', [])
        self.locations = merge_locations(self.profile.get('preset_locations', []), self.custom_locations)
        self.preferences = read_json('ui.local.json', {})

        self.messages = queue.Queue()
        self.busy = False
        self._current_rows = []
        self.last_result = self.preferences.get('last_result', '')
        self.last_time = self.preferences.get('last_time', '')
        self.run_status = tk.StringVar(value='未运行')

        self._build_style()
        self._build_shell()
        self._build_pages()
        self.show_page('home')
        self.after(100, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after_idle(self._ensure_disclaimer)

    # ================= 样式与外壳 =================
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('.', font=(FONT, 10), background=BG)
        style.configure('TFrame', background=BG)
        style.configure('Card.TFrame', background=CARD)
        style.configure('TLabel', background=BG, foreground=TEXT)
        style.configure('Card.TLabel', background=CARD, foreground=TEXT)
        style.configure('Muted.TLabel', background=BG, foreground=MUTED)
        style.configure('CardMuted.TLabel', background=CARD, foreground=MUTED)
        style.configure('TButton', padding=(14, 8), font=(FONT, 10))
        style.configure('Accent.TButton', background=ACCENT, foreground='#ffffff', font=(FONT, 10, 'bold'))
        style.map('Accent.TButton', background=[('active', ACCENT_DARK), ('disabled', '#b9c7e8')])
        style.configure('Nav.TButton', background=SIDEBAR, foreground=TEXT, padding=(14, 10), anchor='w')
        style.map('Nav.TButton', background=[('active', '#eef2ff')])
        style.configure('NavActive.TButton', background='#e8efff', foreground=ACCENT, padding=(14, 10), anchor='w', font=(FONT, 10, 'bold'))
        style.configure('Treeview', rowheight=30, font=(FONT, 10), background=CARD, fieldbackground=CARD)
        style.configure('Treeview.Heading', font=(FONT, 10, 'bold'))
        style.configure('TEntry', padding=6)

    def _build_shell(self):
        outer = ttk.Frame(self)
        outer.pack(fill='both', expand=True)

        self.sidebar = tk.Frame(outer, bg=SIDEBAR, width=180)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text=app_config.APP_NAME, bg=SIDEBAR, fg=ACCENT,
                 font=(FONT, 20, 'bold'), anchor='w').pack(fill='x', padx=20, pady=(22, 2))
        tk.Label(self.sidebar, text=f"{self.profile.get('display_name', self.edition)} · v{app_config.APP_VERSION}",
                 bg=SIDEBAR, fg=MUTED, font=(FONT, 9), anchor='w').pack(fill='x', padx=20)

        nav = tk.Frame(self.sidebar, bg=SIDEBAR)
        nav.pack(fill='x', pady=18)
        self.nav_buttons = {}
        for key, text in [('home', '首页'), ('sign', '签到'), ('places', '地点'),
                          ('resources', '学习资料'), ('help', '帮助'),
                          ('changelog', '更新日志'), ('about', '关于')]:
            btn = ttk.Button(nav, text=text, style='Nav.TButton', command=lambda k=key: self.show_page(k))
            btn.pack(fill='x', padx=12, pady=2)
            self.nav_buttons[key] = btn

        self.status = tk.StringVar(value='就绪 · 只处理进行中的位置签到')
        status_bar = tk.Frame(outer, bg=BG, height=34)
        status_bar.pack(side='bottom', fill='x')
        tk.Label(status_bar, textvariable=self.status, bg=BG, fg=MUTED,
                 font=(FONT, 9), anchor='w').pack(side='left', padx=20, pady=8)

        self.content = ttk.Frame(outer, style='Card.TFrame')
        self.content.pack(side='left', fill='both', expand=True)

    def _card(self, parent, **pack_opts):
        frame = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1, bd=0)
        frame.pack(fill='x', **pack_opts)
        return frame

    # ================= 页面 =================
    def _build_pages(self):
        self.pages = {}
        container = self.content
        self.pages['home'] = self._build_home(container)
        self.pages['sign'] = self._build_sign(container)
        self.pages['places'] = self._build_places(container)
        self.pages['resources'] = self._build_resources(container)
        self.pages['help'] = self._build_help(container)
        self.pages['changelog'] = self._build_changelog(container)
        self.pages['about'] = self._build_about(container)

    def show_page(self, key):
        for k, page in self.pages.items():
            if k == key:
                page.pack(fill='both', expand=True, padx=28, pady=24)
            else:
                page.pack_forget()
        for k, btn in self.nav_buttons.items():
            btn.configure(style='NavActive.TButton' if k == key else 'Nav.TButton')
        self._refresh_home()

    def _page_title(self, page, text, sub=None):
        tk.Label(page, text=text, bg=CARD, fg=TEXT, font=(FONT, 20, 'bold')).pack(anchor='w')
        if sub:
            tk.Label(page, text=sub, bg=CARD, fg=MUTED, font=(FONT, 10), wraplength=760).pack(anchor='w', pady=(4, 14))

    # ---- 首页 ----
    def _build_home(self, parent):
        page = tk.Frame(parent, bg=CARD)

        hero = self._card(page, padx=0, pady=0)
        tk.Label(hero, text=app_config.APP_NAME, bg=CARD, fg=TEXT, font=(FONT, 28, 'bold')).pack(anchor='w', padx=24, pady=(24, 2))
        tk.Label(hero, text=f"学习通位置签到 · {self.profile.get('display_name', '')} · v{app_config.APP_VERSION}",
                 bg=CARD, fg=MUTED, font=(FONT, 11)).pack(anchor='w', padx=24)
        tk.Label(hero, text='面向山西财经大学，同时支持自定义地点的学习通位置签到桌面工具。',
                 bg=CARD, fg=TEXT, font=(FONT, 10), wraplength=700).pack(anchor='w', padx=24, pady=(10, 24))

        grid = self._card(page, pady=(16, 0))
        grid_inner = tk.Frame(grid, bg=CARD)
        grid_inner.pack(fill='x', padx=20, pady=18)
        self.home_account = tk.StringVar()
        self.home_location = tk.StringVar()
        self.home_last = tk.StringVar()
        items = [
            ('当前账号', self.home_account),
            ('当前地点', self.home_location),
            ('运行状态', self.run_status),
            ('最近一次签到', self.home_last),
        ]
        for i, (label, var) in enumerate(items):
            cell = tk.Frame(grid_inner, bg=CARD)
            cell.grid(row=0, column=i, sticky='w', padx=(0, 12))
            tk.Label(cell, text=label, bg=CARD, fg=MUTED, font=(FONT, 9)).pack(anchor='w')
            tk.Label(cell, textvariable=var, bg=CARD, fg=TEXT, font=(FONT, 12, 'bold'), wraplength=170, justify='left').pack(anchor='w', pady=(4, 0))

        actions = self._card(page, pady=(16, 0))
        actions_inner = tk.Frame(actions, bg=CARD)
        actions_inner.pack(fill='x', padx=20, pady=18)
        ttk.Button(actions_inner, text='开始签到', style='Accent.TButton', command=lambda: self.show_page('sign')).pack(side='left')
        if not self.accounts:
            ttk.Button(actions_inner, text='前往设置', command=lambda: self.show_page('sign')).pack(side='left', padx=12)
        ttk.Button(actions_inner, text='管理地点', command=lambda: self.show_page('places')).pack(side='left', padx=12)
        return page

    def _refresh_home(self):
        self.home_account.set(f'已配置 {len(self.accounts)} 个' if self.accounts else '未配置')
        try:
            loc = self.selected_fixed_location()
            self.home_location.set(loc['name'])
        except ValueError:
            self.home_location.set('未选择')
        self.home_last.set(f'{self.last_time} {self.last_result}'.strip() if (self.last_time or self.last_result) else '暂无')

    # ---- 签到页 ----
    def _build_sign(self, parent):
        page = tk.Frame(parent, bg=CARD)
        self._page_title(page, '签到', '输入课程名，选择账号和位置模式，提交后逐项核对结果。')

        row = tk.Frame(page, bg=CARD)
        row.pack(fill='x')
        tk.Label(row, text='课程名称', bg=CARD, fg=TEXT).pack(side='left')
        self.course = tk.StringVar(value=self.preferences.get('course', ''))
        ttk.Entry(row, textvariable=self.course, width=36).pack(side='left', padx=12)
        self.scan = ttk.Button(row, text='仅查询', command=lambda: self.start(False))
        self.scan.pack(side='left', padx=4)
        self.submit = ttk.Button(row, text='查询并签到', style='Accent.TButton', command=lambda: self.start(True))
        self.submit.pack(side='left', padx=4)

        mode_row = tk.Frame(page, bg=CARD)
        mode_row.pack(fill='x', pady=(16, 4))
        self.mode = tk.StringVar(value=self.preferences.get('location_mode', 'fixed'))
        if self.mode.get() not in ('fixed', 'auto'):
            self.mode.set('fixed')
        self.fixed_radio = ttk.Radiobutton(mode_row, text='固定位置', variable=self.mode, value='fixed', command=self.update_location_controls)
        self.fixed_radio.pack(side='left')
        self.auto_radio = ttk.Radiobutton(mode_row, text='按指定地点匹配', variable=self.mode, value='auto', command=self.update_location_controls)
        self.auto_radio.pack(side='left', padx=16)

        self.fixed_name = tk.StringVar(value=self.preferences.get('fixed_location', ''))
        if not self.fixed_name.get() and self.locations:
            self.fixed_name.set(self.locations[0]['name'])
        self.fixed_picker = ttk.Combobox(page, textvariable=self.fixed_name, state='readonly')
        self.fixed_picker.pack(fill='x')
        self.fixed_picker.bind('<<ComboboxSelected>>', self.update_location_controls)
        self.location_hint = tk.StringVar()
        tk.Label(page, textvariable=self.location_hint, bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=760).pack(anchor='w', pady=(4, 0))

        tk.Label(page, text='选择账号（Ctrl / Shift 多选）', bg=CARD, fg=TEXT).pack(anchor='w', pady=(18, 6))
        account_row = tk.Frame(page, bg=CARD)
        account_row.pack(fill='x')
        self.account_list = tk.Listbox(account_row, selectmode='extended', exportselection=False, height=4,
                                       font=(FONT, 10), relief='flat', highlightbackground=BORDER, highlightthickness=1)
        self.account_list.pack(side='left', fill='x', expand=True)
        tools = tk.Frame(account_row, bg=CARD)
        tools.pack(side='left', padx=12)
        self.add_button = ttk.Button(tools, text='添加 / 更新账号', command=self.add_account)
        self.add_button.pack(fill='x')
        self.remove_button = ttk.Button(tools, text='删除选中账号', command=self.remove_accounts)
        self.remove_button.pack(fill='x', pady=4)
        self.refresh_accounts()

        tk.Label(page, text='执行结果', bg=CARD, fg=TEXT).pack(anchor='w', pady=(18, 6))
        self.results = ttk.Treeview(page, columns=('account', 'course', 'activity', 'address', 'status'), show='headings', height=8)
        for col, title, width in [('account', '账号', 120), ('course', '课程', 110), ('activity', '活动', 110), ('address', '签到位置', 190), ('status', '结果', 320)]:
            self.results.heading(col, text=title)
            self.results.column(col, width=width, minwidth=60)
        self.results.pack(fill='both', expand=True)
        scroll = ttk.Scrollbar(page, orient='horizontal', command=self.results.xview)
        scroll.pack(fill='x')
        self.results.configure(xscrollcommand=scroll.set)
        self.results.bind('<Double-1>', self.show_result)
        self.update_location_controls()
        return page

    # ---- 地点页 ----
    def _build_places(self, parent):
        page = tk.Frame(parent, bg=CARD)
        self._page_title(page, '地点', '固定模式使用所选地点；自动模式按签到页面中的指定地点匹配。坐标使用百度 BD-09（经度在前、纬度在后）。')

        self.place_list = tk.Listbox(page, font=(FONT, 10), height=14, relief='flat', highlightbackground=BORDER, highlightthickness=1)
        self.place_list.pack(fill='both', expand=True)
        self.refresh_places()

        place_buttons = tk.Frame(page, bg=CARD)
        place_buttons.pack(fill='x', pady=10)
        self.place_add = ttk.Button(place_buttons, text='添加 / 更新地点', command=self.add_location)
        self.place_add.pack(side='left')
        self.place_remove = ttk.Button(place_buttons, text='删除选中地点', command=self.remove_location)
        self.place_remove.pack(side='left', padx=8)
        ttk.Button(place_buttons, text='导出地点', command=self.export_locations).pack(side='left', padx=8)
        ttk.Button(place_buttons, text='导入地点', command=self.import_locations).pack(side='left', padx=8)
        tk.Label(page, text='预设地点来自当前版本档案，可删除；删除后仍可重新添加自定义地点。',
                 bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=760).pack(anchor='w')
        return page

    # ---- 学习资料页 ----
    def _build_resources(self, parent):
        page = tk.Frame(parent, bg=CARD)
        self._page_title(page, '学习资料', '整理中的校园学习资源入口。')
        self.resource_container = tk.Frame(page, bg=CARD)
        self.resource_container.pack(fill='both', expand=True)
        self._populate_resources()
        return page

    def _populate_resources(self):
        for w in self.resource_container.winfo_children():
            w.destroy()
        if self.edition == 'scufe':
            card = self._card(self.resource_container, pady=0)
            inner = tk.Frame(card, bg=CARD)
            inner.pack(fill='x', padx=22, pady=20)
            tk.Label(inner, text='山西财经大学历年期末资料', bg=CARD, fg=TEXT, font=(FONT, 14, 'bold')).pack(anchor='w')
            tk.Label(inner, text='整理中的山财历年期末真题与复习资料，欢迎补充。', bg=CARD, fg=MUTED, font=(FONT, 10)).pack(anchor='w', pady=(6, 14))
            row = tk.Frame(inner, bg=CARD)
            row.pack(anchor='w')
            ttk.Button(row, text='打开资料库', style='Accent.TButton', command=lambda: webbrowser.open(app_config.EXAM_REPO_URL)).pack(side='left')
            ttk.Button(row, text='查看资料索引', command=lambda: webbrowser.open(app_config.EXAM_REPO_URL + '/blob/main/INDEX.md')).pack(side='left', padx=10)
            ttk.Button(row, text='参与补充', command=lambda: webbrowser.open(app_config.EXAM_REPO_URL + '/issues')).pack(side='left', padx=10)
        else:
            tk.Label(self.resource_container, text='社区资源', bg=CARD, fg=TEXT, font=(FONT, 14, 'bold')).pack(anchor='w')
            tk.Label(self.resource_container, text='以下为社区贡献的校园资源，与 CxSign 通用版无绑定关系。',
                     bg=CARD, fg=MUTED, font=(FONT, 10)).pack(anchor='w', pady=(6, 12))
            card = self._card(self.resource_container, pady=0)
            inner = tk.Frame(card, bg=CARD)
            inner.pack(fill='x', padx=22, pady=20)
            tk.Label(inner, text='山西财经大学资源库', bg=CARD, fg=TEXT, font=(FONT, 12, 'bold')).pack(anchor='w')
            tk.Label(inner, text='山西财经大学历年期末资料（社区贡献）', bg=CARD, fg=MUTED, font=(FONT, 10)).pack(anchor='w', pady=(4, 12))
            ttk.Button(inner, text='打开', command=lambda: webbrowser.open(app_config.EXAM_REPO_URL)).pack(anchor='w')

    # ---- 帮助页 ----
    def _build_help(self, parent):
        page = tk.Frame(parent, bg=CARD)
        self._page_title(page, '帮助', '根据当前程序真实功能整理的简明使用说明。')
        steps = [
            ('第一次使用', '首次启动会展示《用户须知》，点击「我已阅读并理解」进入主程序。'),
            ('填写账号', '在「签到」页点击「添加 / 更新账号」，输入学习通账号与密码（手机号登录时学校 ID 留空）。账号仅保存在本机。'),
            ('添加地点', '在「地点」页点击「添加 / 更新地点」，填写完整地点名称与百度经纬度。'),
            ('选择签到地点', '在「签到」页选择「固定位置」并挑选地点，或选择「按指定地点匹配」。'),
            ('开始签到', '在「签到」页输入完整课程名、选择账号，点击「查询并签到」；「仅查询」不会提交签到。'),
            ('判断签到成功', '结果列显示「签到成功」即表示已提交并复查通过；请以学习通内实际状态为准。'),
            ('常见错误', '网络失败会提示检查网络；登录失败请核对账号密码；地点不匹配请核对地点名称与坐标。'),
            ('反馈问题', '请在 GitHub Issues 提交问题，提交前遮挡账号等隐私信息。'),
            ('更新', '前往 GitHub Releases 下载新版本，或从源码运行 git pull 更新。'),
        ]
        for title, body in steps:
            tk.Label(page, text=title, bg=CARD, fg=TEXT, font=(FONT, 11, 'bold')).pack(anchor='w', pady=(12, 2))
            tk.Label(page, text=body, bg=CARD, fg=MUTED, font=(FONT, 10), wraplength=760, justify='left').pack(anchor='w')
        tk.Label(page, text='完整教程见仓库 docs/USER_GUIDE.md。', bg=CARD, fg=MUTED, font=(FONT, 9)).pack(anchor='w', pady=(16, 0))
        return page

    # ---- 更新日志页 ----
    def _build_changelog(self, parent):
        page = tk.Frame(parent, bg=CARD)
        self._page_title(page, '更新日志', '当前版本更新内容。')
        for entry in CHANGELOG:
            tk.Label(page, text=f"{entry['version']}  ({entry['date']})", bg=CARD, fg=TEXT, font=(FONT, 14, 'bold')).pack(anchor='w', pady=(8, 4))
            for section, items in entry['sections']:
                if not items:
                    continue
                tk.Label(page, text=section, bg=CARD, fg=ACCENT, font=(FONT, 10, 'bold')).pack(anchor='w', pady=(6, 2))
                for it in items:
                    tk.Label(page, text='· ' + it, bg=CARD, fg=TEXT, font=(FONT, 10), wraplength=760, justify='left').pack(anchor='w', pady=1)
        return page

    # ---- 关于页 ----
    def _build_about(self, parent):
        page = tk.Frame(parent, bg=CARD)
        self._page_title(page, '关于', '')
        tk.Label(page, text=app_config.APP_NAME, bg=CARD, fg=TEXT, font=(FONT, 24, 'bold')).pack(anchor='w', pady=(8, 0))
        tk.Label(page, text=f"版本 v{app_config.APP_VERSION} · {self.profile.get('display_name', '')}",
                 bg=CARD, fg=MUTED, font=(FONT, 11)).pack(anchor='w', pady=(2, 10))
        tk.Label(page, text='一个第三方开源学习与技术交流项目，提供学习通位置签到桌面工具。',
                 bg=CARD, fg=TEXT, font=(FONT, 10), wraplength=760, justify='left').pack(anchor='w', pady=(0, 14))
        links = [
            ('GitHub 仓库', app_config.REPO_URL),
            ('问题反馈 / Issues', app_config.ISSUES_URL),
        ]
        for label, url in links:
            ttk.Button(page, text=label, command=lambda u=url: webbrowser.open(u)).pack(anchor='w', pady=2)
        ttk.Button(page, text='查看用户须知', command=lambda: self._show_disclaimer(False)).pack(anchor='w', pady=2)
        ttk.Button(page, text='查看更新日志', command=lambda: self.show_page('changelog')).pack(anchor='w', pady=2)
        tk.Label(page, text='如果这个项目对你有帮助，欢迎在 GitHub 点一个 Star ⭐，也欢迎提交 Issue 或参与改进。',
                 bg=CARD, fg=MUTED, font=(FONT, 10), wraplength=760, justify='left').pack(anchor='w', pady=(18, 0))
        tk.Label(page, text='本软件所依赖的第三方组件按其各自许可证授权，详见 THIRD_PARTY_NOTICES.md。',
                 bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=760, justify='left').pack(anchor='w', pady=(8, 0))
        return page

    # ================= 首次须知 =================
    def disclaimer_needed(self):
        return (not self.dev_mode) and (not self.preferences.get('disclaimer_accepted'))

    def _ensure_disclaimer(self):
        if self.disclaimer_needed():
            self._show_disclaimer(True)

    def _show_disclaimer(self, blocking):
        win = tk.Toplevel(self)
        win.title(disclaimer.DISCLAIMER_TITLE)
        win.transient(self)
        win.grab_set()
        win.configure(bg=CARD)
        win.geometry('640x560')

        tk.Label(win, text=disclaimer.DISCLAIMER_TITLE, bg=CARD, fg=TEXT, font=(FONT, 16, 'bold')).pack(anchor='w', padx=24, pady=(20, 4))
        tk.Label(win, text=disclaimer.DISCLAIMER_INTRO, bg=CARD, fg=MUTED, font=(FONT, 10), wraplength=580, justify='left').pack(anchor='w', padx=24, pady=(0, 8))

        body = tk.Frame(win, bg=CARD)
        body.pack(fill='both', expand=True, padx=24, pady=4)
        text = tk.Text(body, bg=CARD, fg=TEXT, font=(FONT, 10), wrap='word', relief='flat', borderwidth=0)
        text.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(body, command=text.yview)
        scrollbar.pack(side='right', fill='y')
        text.configure(yscrollcommand=scrollbar.set)
        for i, (heading, content) in enumerate(disclaimer.DISCLAIMER_SECTIONS, 1):
            text.insert('end', f'{i}. {heading}\n', 'heading')
            text.insert('end', f'{content}\n\n', 'body')
        text.tag_configure('heading', font=(FONT, 10, 'bold'), foreground=TEXT, spacing1=6)
        text.tag_configure('body', font=(FONT, 10), foreground=TEXT, spacing3=4, lmargin1=16, lmargin2=16)
        text.configure(state='disabled')

        footer = tk.Frame(win, bg=CARD)
        footer.pack(fill='x', padx=24, pady=16)
        if blocking:
            ttk.Button(footer, text='退出程序', command=lambda: self._quit_app(win)).pack(side='left')
            ttk.Button(footer, text='我已阅读并理解', style='Accent.TButton', command=lambda: self._accept_disclaimer(win)).pack(side='right')
        else:
            ttk.Button(footer, text='关闭', command=win.destroy).pack(side='right')

        win.wait_window()

    def _accept_disclaimer(self, win):
        self.preferences['disclaimer_accepted'] = True
        try:
            write_json('ui.local.json', self.preferences)
        except OSError:
            pass
        win.destroy()

    def _quit_app(self, win=None):
        if win is not None:
            win.destroy()
        self.destroy()

    # ================= 账号管理 =================
    def refresh_accounts(self):
        self.account_list.delete(0, 'end')
        for account in self.accounts:
            self.account_list.insert('end', account['username'])
        self.account_list.selection_set(0, 'end')

    def add_account(self):
        def save(values):
            username, password, schoolid = values
            username, schoolid = username.strip(), schoolid.strip()
            if not username or not password:
                raise ValueError('账号和密码不能为空')
            new = [a for a in self.accounts if a['username'] != username]
            new.append({'username': username, 'password': password, 'schoolid': schoolid})
            write_json('user.json', new)
            self.accounts = new
            self.refresh_accounts()
        self._form('添加 / 更新账号', [('账号', False), ('密码', True), ('学校 ID（手机号登录留空）', False)], save)

    def remove_accounts(self):
        chosen = set(self.account_list.curselection())
        new = [a for i, a in enumerate(self.accounts) if i not in chosen]
        try:
            write_json('user.json', new)
        except OSError:
            messagebox.showerror('未删除', '账号文件写入失败')
            return
        self.accounts = new
        self.refresh_accounts()

    # ================= 地点管理 =================
    def _preset_names(self):
        return {p.get('name') for p in self.profile.get('preset_locations', [])}

    def refresh_places(self):
        self.place_list.delete(0, 'end')
        presets = self._preset_names()
        for p in self.locations:
            tag = '预设' if p['name'] in presets else '自定义'
            self.place_list.insert('end', f"[{tag}] {p['name']}    {p['longitude']:.7f}, {p['latitude']:.7f}")
        self.fixed_picker.configure(values=[p['name'] for p in self.locations])
        self.update_location_controls()

    def selected_fixed_location(self):
        matches = [p for p in self.locations if p['name'] == self.fixed_name.get()]
        if len(matches) != 1:
            raise ValueError('请重新选择固定地点；当前地点已删除或存在同名记录。')
        p = matches[0]
        return validate_location(p['name'], p['longitude'], p['latitude'])

    def update_location_controls(self, event=None):
        fixed = self.mode.get() == 'fixed'
        self.fixed_picker.configure(state='readonly' if fixed and not self.busy else 'disabled')
        if fixed:
            try:
                p = self.selected_fixed_location()
                self.location_hint.set(f"每次提交此位置：百度经度 {p['longitude']:.7f}，纬度 {p['latitude']:.7f}；不依赖活动地点名称。")
            except ValueError as exc:
                self.location_hint.set(str(exc))
        else:
            self.location_hint.set('按活动的指定地点匹配地点库；未指定地点或匹配不唯一时停止。')

    def save_preferences(self):
        self.preferences.update(course=self.course.get().strip(), location_mode=self.mode.get(), fixed_location=self.fixed_name.get())
        write_json('ui.local.json', self.preferences)

    def add_location(self):
        def save(values):
            p = validate_location(*values)
            old = next((v for v in self.locations if v['name'] == p['name']), {})
            if 'aliases' in old:
                p['aliases'] = list(old['aliases'])
            new = [v for v in self.custom_locations if v['name'] != p['name']] + [p]
            write_json('locations.local.json', new)
            self.custom_locations = new
            self.locations = merge_locations(self.profile.get('preset_locations', []), self.custom_locations)
            self.refresh_places()
        self._form('添加 / 更新地点', [('完整地点名称（与签到页面一致）', False), ('百度经度', False), ('百度纬度', False)], save)

    def remove_location(self):
        chosen = set(self.place_list.curselection())
        to_remove = {self.locations[i]['name'] for i in chosen}
        new = [p for p in self.custom_locations if p['name'] not in to_remove]
        try:
            write_json('locations.local.json', new)
        except OSError:
            messagebox.showerror('未删除', '地点文件写入失败')
            return
        self.custom_locations = new
        self.locations = merge_locations(self.profile.get('preset_locations', []), self.custom_locations)
        self.refresh_places()

    def export_locations(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')],
                                            initialfile='locations.json')
        if not path:
            return
        try:
            import json
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.locations, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showerror('导出失败', str(exc))

    def import_locations(self):
        path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            import json
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError('地点文件格式应为列表')
            validated = [validate_location(p.get('name'), p.get('longitude'), p.get('latitude')) for p in data]
            new = list(self.custom_locations)
            names = {v['name'] for v in new}
            for p in validated:
                if p['name'] in names:
                    new = [v for v in new if v['name'] != p['name']]
                new.append(p)
                names.add(p['name'])
            write_json('locations.local.json', new)
            self.custom_locations = new
            self.locations = merge_locations(self.profile.get('preset_locations', []), self.custom_locations)
            self.refresh_places()
            messagebox.showinfo('导入完成', f'已导入 {len(validated)} 个地点。')
        except (ValueError, OSError, TypeError) as exc:
            messagebox.showerror('导入失败', str(exc))

    # ================= 表单 =================
    def _form(self, title, fields, save):
        window = tk.Toplevel(self)
        window.title(title)
        window.transient(self)
        window.grab_set()
        window.configure(bg=CARD)
        box = tk.Frame(window, bg=CARD)
        box.pack(fill='both', expand=True, padx=20, pady=20)
        variables = []
        for label, secret in fields:
            tk.Label(box, text=label, bg=CARD, fg=TEXT).pack(anchor='w', pady=(8, 4))
            var = tk.StringVar()
            ttk.Entry(box, textvariable=var, width=52, show='•' if secret else '').pack(fill='x')
            variables.append(var)

        def commit():
            try:
                save([v.get() for v in variables])
                window.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror('未保存', str(exc), parent=window)
        ttk.Button(box, text='保存到本机', style='Accent.TButton', command=commit).pack(anchor='e', pady=(18, 0))

    # ================= 签到调度 =================
    def set_busy(self, busy):
        self.busy = busy
        for button in [self.scan, self.submit, self.add_button, self.remove_button, self.place_add, self.place_remove]:
            button.configure(state='disabled' if busy else 'normal')
        for radio in [self.fixed_radio, self.auto_radio]:
            radio.configure(state='disabled' if busy else 'normal')
        self.update_location_controls()

    def start(self, execute):
        if self.busy:
            return
        accounts = [dict(self.accounts[i]) for i in self.account_list.curselection()]
        course = self.course.get().strip()
        if not accounts or not course:
            messagebox.showinfo('需要补充', '请输入完整课程名并选择至少一个账号。')
            return
        try:
            fixed_location = self.selected_fixed_location() if self.mode.get() == 'fixed' else None
            self.save_preferences()
        except ValueError as exc:
            messagebox.showerror('未开始', str(exc))
            return
        except OSError:
            messagebox.showerror('未开始', '配置文件写入失败')
            return
        self.results.delete(*self.results.get_children())
        self._current_rows = []
        locations = [dict(p) for p in self.locations]
        self.set_busy(True)
        self.run_status.set('正在签到')
        self.status.set(f'正在处理 {len(accounts)} 个账号，请稍候…')
        self._refresh_home()

        def worker():
            try:
                asyncio.run(run_batch(accounts, course, locations, execute, self.messages.put, fixed_location=fixed_location))
            except Exception as exc:
                self.messages.put(('', course, '', '', '任务异常：' + type(exc).__name__))
            finally:
                self.messages.put(None)
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                item = self.messages.get_nowait()
                if item is None:
                    self.set_busy(False)
                    self._finalize_run()
                    self.status.set('本次处理结束 · 请查看各账号结果；双击可查看完整详情')
                else:
                    self._current_rows.append(item)
                    self.results.insert('', 'end', values=item)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def _finalize_run(self):
        summary = self._summarize(self._current_rows)
        self.run_status.set(summary)
        self.last_result = summary
        self.last_time = time.strftime('%m-%d %H:%M', time.localtime())
        self.preferences['last_result'] = self.last_result
        self.preferences['last_time'] = self.last_time
        try:
            write_json('ui.local.json', self.preferences)
        except OSError:
            pass
        self._refresh_home()

    @staticmethod
    def _summarize(rows):
        if not rows:
            return '未运行'
        successes = [r for r in rows if '签到成功' in r[-1]]
        if successes:
            return f'签到成功（{len(successes)} 项）'
        if any(('失败' in r[-1] or '未成功' in r[-1] or '异常' in r[-1] or '登录失败' in r[-1]) for r in rows):
            return '签到失败'
        return '已完成（无待签到任务）'

    def show_result(self, event=None):
        selection = self.results.selection()
        if selection:
            values = self.results.item(selection[0], 'values')
            messagebox.showinfo('执行详情', '\n\n'.join(f'{k}：{v}' for k, v in zip(['账号', '课程', '活动', '地点', '结果'], values)))

    def close(self):
        if self.busy:
            messagebox.showinfo('任务执行中', '请等待当前请求结束后关闭窗口。')
            return
        try:
            self.save_preferences()
        except OSError:
            messagebox.showerror('未保存设置', '配置文件写入失败，请检查文件权限后重试。')
            return
        self.destroy()


if __name__ == '__main__':
    try:
        App().mainloop()
    except Exception as exc:
        messagebox.showerror('启动失败', '请检查本机 JSON 配置文件和运行环境。错误类型：' + type(exc).__name__)
