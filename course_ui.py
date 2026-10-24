"""课程任务页面；可选浏览器依赖仅在工作进程内加载。"""
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from course_runner import CourseRunner, DEFAULTS, validate_settings
from paths import data_root


class CoursePage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg='white')
        self.app = app
        self.runner = CourseRunner(data_root() / 'course-data')
        self.preferences = dict(app.preferences.get('course_learning', {}))
        self.vars = {}
        tk.Label(self, text='课程学习', bg='white', font=('Microsoft YaHei UI', 20, 'bold')).pack(anchor='w')
        tk.Label(self, text='浏览器任务 · 位置签到仍在“签到”页面操作', bg='white').pack(anchor='w', pady=(4, 10))
        form = ttk.Frame(self)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        self.account = tk.StringVar()
        ttk.Label(form, text='现有账号').grid(row=0, column=0, sticky='w', padx=5, pady=4)
        self.account_box = ttk.Combobox(form, textvariable=self.account, state='readonly')
        self.account_box.grid(row=0, column=1, sticky='ew', padx=5)
        self.account_box.bind('<Button-1>', lambda _: self.refresh_accounts())
        self._field(form, 0, 2, '登录方式', 'login_mode', ['qr', 'account'])
        self._field(form, 1, 0, '浏览器', 'browser', ['edge', 'chrome'])
        self._field(form, 1, 2, '任务类型', 'task_type', ['课程', '作业'])
        self._field(form, 2, 0, '章节答题', 'choice', ['不刷题', 'DeepSeek AI', '随机答题'])
        self._field(form, 2, 2, '答题后', 'after_finish_question', ['仅自动保存', '强制自动提交'])
        self._field(form, 3, 0, '讨论', 'discussion_choice', ['跳过讨论', 'DeepSeek AI'])
        self._field(form, 3, 2, '作业选择', 'homework', ['自动选择', '手动选择'])
        self._field(form, 4, 0, '播放倍速', 'speed')
        self._field(form, 4, 2, 'AI 模型', 'ai_model')
        self._field(form, 5, 0, 'API Key', 'api_key', secret=True)
        self._field(form, 5, 2, '驱动路径（可空）', 'driver_path')
        self._field(form, 6, 0, '定时开始', 'start_at')
        self._field(form, 6, 2, '定时结束', 'end_at')
        ttk.Label(form, text='时间格式：YYYY-MM-DD HH:MM；留空立即开始 / 不限时。qr 为扫码，account 为账号密码。').grid(
            row=7, column=0, columnspan=4, sticky='w', padx=5, pady=3)
        self._field(form, 8, 0, '同时运行课程数', 'parallel', ['1', '2', '3'])
        self.keep_awake = tk.BooleanVar(value=bool(self.preferences.get('lock_screen', False)))
        ttk.Checkbutton(form, text='运行时保持电脑唤醒', variable=self.keep_awake).grid(row=8, column=2, columnspan=2, sticky='w')
        ttk.Label(self, text='课程名称（每行一门，按顺序处理）').pack(anchor='w', pady=(8, 3))
        self.courses = tk.Text(self, height=2, font=('Microsoft YaHei UI', 10))
        self.courses.pack(fill='x')
        self.courses.insert('1.0', '\n'.join(self.preferences.get('courses', [])))
        buttons = ttk.Frame(self)
        buttons.pack(fill='x', pady=8)
        self.start_button = ttk.Button(buttons, text='开始课程任务', command=self.start)
        self.start_button.pack(side='left')
        ttk.Button(buttons, text='停止', command=self.stop).pack(side='left', padx=6)
        ttk.Button(buttons, text='保存设置', command=self.save).pack(side='left')
        ttk.Button(buttons, text='选择驱动', command=self.choose_driver).pack(side='left', padx=6)
        self.status = tk.StringVar(value='未运行 · API Key 仅本次使用，不保存到设置')
        ttk.Label(self, textvariable=self.status).pack(anchor='w')
        self.output = tk.Text(self, height=5, state='disabled', wrap='word')
        self.output.pack(fill='both', expand=True, pady=(5, 0))
        self.refresh_accounts()
        self._poll_id = self.app.after(150, self.poll)

    def _field(self, parent, row, column, label, key, values=None, secret=False):
        value = '' if secret else self.preferences.get(key, DEFAULTS[key])
        self.vars[key] = tk.StringVar(value=str(value))
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky='w', padx=5, pady=2)
        if values:
            widget = ttk.Combobox(parent, textvariable=self.vars[key], values=values, state='readonly', width=16)
        else:
            widget = ttk.Entry(parent, textvariable=self.vars[key], show='*' if secret else '', width=18)
        widget.grid(row=row, column=column+1, sticky='ew', padx=5)

    def refresh_accounts(self):
        names = [a.get('username', '') for a in self.app.accounts]
        self.account_box.configure(values=names)
        if self.account.get() not in names:
            self.account.set(names[0] if names else '')

    def settings(self):
        cfg = {k: v.get() for k, v in self.vars.items()}
        cfg['courses'] = self.courses.get('1.0', 'end').strip()
        cfg['lock_screen'] = self.keep_awake.get()
        return cfg

    def save(self):
        # Saving incomplete AI settings is useful; validation happens on start.
        cfg = self.settings()
        cfg.pop('api_key', None)
        cfg['courses'] = [x.strip() for x in cfg['courses'].splitlines() if x.strip()]
        self.app.preferences['course_learning'] = cfg
        try:
            self.app.save_preferences()
        except OSError:
            messagebox.showerror('保存失败', '无法写入本地设置，请检查文件权限。', parent=self)
            return
        self.status.set('课程设置已保存（不含 API Key）')

    def choose_driver(self):
        path = filedialog.askopenfilename(title='选择浏览器驱动', filetypes=[('驱动', '*.exe')], parent=self)
        if path:
            self.vars['driver_path'].set(path)

    def start(self):
        self.refresh_accounts()
        account = next((a for a in self.app.accounts if a.get('username') == self.account.get()), {})
        try:
            cfg = validate_settings(self.settings())
            self.app._ensure_disclaimer()
            if self.app.disclaimer_needed():
                return
            self.runner.start(account, cfg)
        except ValueError as exc:
            messagebox.showerror('无法开始', str(exc), parent=self)
            return
        self.start_button.configure(state='disabled')
        self.status.set('正在准备课程任务')

    def stop(self):
        self.runner.stop()
        if self.runner.running:
            self.status.set('正在停止课程任务…')

    def poll(self):
        try:
            while True:
                kind, text = self.runner.events.get_nowait()
                if kind in ('status', 'error', 'done'):
                    self.status.set(text)
                self.output.configure(state='normal')
                self.output.insert('end', text + '\n')
                if int(self.output.index('end-1c').split('.')[0]) > 500:
                    self.output.delete('1.0', '100.0')
                self.output.see('end')
                self.output.configure(state='disabled')
        except queue.Empty:
            pass
        self.start_button.configure(state='disabled' if self.runner.running else 'normal')
        self._poll_id = self.app.after(150, self.poll)

    def destroy(self):
        self.runner.stop()
        if self._poll_id:
            self.app.after_cancel(self._poll_id)
        super().destroy()
