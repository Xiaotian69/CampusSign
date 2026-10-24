"""课程学习页面：登录 → 选择课程 → 开始 → 查看状态/停止。

可选浏览器依赖仅在工作进程内加载；不常用的设置收在“高级设置”弹窗中。
"""
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from course_runner import CourseRunner, DEFAULTS
from paths import data_root
from window_utils import place_in_work_area


# 界面显示文字 ↔ 保存的配置值（配置值保持不变，兼容已有设置）。
OPTIONS = {
    'login_mode': [('qr', '扫码登录'), ('account', '账号密码登录')],
    'browser': [('auto', '自动（优先微软 Edge）'), ('edge', '微软 Edge'), ('chrome', '谷歌 Chrome')],
    'task_type': [('课程', '章节任务'), ('作业', '作业（AI 填写后只保存，不提交）')],
    'choice': [('不刷题', '不答题（跳过章节测验）'), ('DeepSeek AI', 'DeepSeek AI 答题'),
               ('随机答题', '随机答题（答案随机）')],
    'after_finish_question': [('仅自动保存', '只保存答案，不提交'), ('强制自动提交', '自动提交（正式交卷）')],
    'discussion_choice': [('跳过讨论', '跳过讨论'), ('DeepSeek AI', 'DeepSeek AI 发表讨论')],
    'homework': [('自动选择', '自动选择作业'), ('手动选择', '在浏览器中手动选择作业')],
    'parallel': [('1', '1（推荐）'), ('2', '2'), ('3', '3')],
}
STORED = ('login_mode', 'browser', 'driver_path', 'task_type', 'choice', 'after_finish_question',
          'discussion_choice', 'homework', 'speed', 'ai_model', 'start_at', 'end_at', 'parallel')


def label_of(key, value):
    return dict(OPTIONS[key]).get(str(value), str(value))


class CoursePage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg='white')
        self.app = app
        self.runner = CourseRunner(data_root() / 'course-data')
        self.preferences = dict(app.preferences.get('course_learning', {}))
        self.vars = {key: tk.StringVar(value=str(self.preferences.get(key, DEFAULTS[key]))) for key in STORED}
        for key, options in OPTIONS.items():
            if self.vars[key].get() not in dict(options):
                self.vars[key].set(str(DEFAULTS[key]))
        self.vars['api_key'] = tk.StringVar()  # 仅本次运行使用，不保存
        self.account = tk.StringVar(value=self.preferences.get('account', ''))
        self.keep_awake = tk.BooleanVar(value=bool(self.preferences.get('lock_screen', False)))
        self._advanced = None
        self._poll_id = None

        tk.Label(self, text='课程学习', bg='white', font=('Microsoft YaHei UI', 20, 'bold')).pack(anchor='w')
        tk.Label(self, text='在官方浏览器中登录后选择课程 · 位置签到仍在“签到”页面操作',
                 bg='white', fg='#6b7280').pack(anchor='w', pady=(2, 10))

        step1 = tk.Frame(self, bg='white')
        step1.pack(fill='x')
        tk.Label(step1, text='① 登录', bg='white', font=('Microsoft YaHei UI', 11, 'bold')).pack(side='left')
        self.login_button = ttk.Button(step1, text='登录学习通', style='Accent.TButton', command=self.login)
        self.login_button.pack(side='left', padx=(12, 8))
        self.login_hint = tk.Label(step1, bg='white', fg='#6b7280')
        self.login_hint.pack(side='left')

        step2 = tk.Frame(self, bg='white')
        step2.pack(fill='both', expand=True, pady=(12, 0))
        top = tk.Frame(step2, bg='white')
        top.pack(fill='x')
        tk.Label(top, text='② 选择课程', bg='white', font=('Microsoft YaHei UI', 11, 'bold')).pack(side='left')
        self.course_hint = tk.Label(top, text='登录后自动读取“我学的课”，可按住 Ctrl 多选', bg='white', fg='#6b7280')
        self.course_hint.pack(side='left', padx=12)
        self.refresh_button = ttk.Button(top, text='刷新列表', command=self.refresh_courses)
        self.refresh_button.pack(side='right')
        box = tk.Frame(step2, bg='white')
        box.pack(fill='both', expand=True, pady=(6, 0))
        self.course_list = tk.Listbox(box, selectmode='extended', height=4, exportselection=False,
                                      font=('Microsoft YaHei UI', 10), activestyle='none')
        self.course_list.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(box, command=self.course_list.yview)
        scroll.pack(side='right', fill='y')
        self.course_list.configure(yscrollcommand=scroll.set)
        tk.Label(step2, text='列表读取失败或找不到课程时，在这里手动输入（每行一门，可只填课程名中的一段）：',
                 bg='white', fg='#6b7280').pack(anchor='w', pady=(6, 2))
        self.courses = tk.Text(step2, height=2, font=('Microsoft YaHei UI', 10))
        self.courses.pack(fill='x')
        self.courses.insert('1.0', '\n'.join(self.preferences.get('courses', [])))

        step3 = tk.Frame(self, bg='white')
        step3.pack(fill='x', pady=(10, 0))
        tk.Label(step3, text='③ 运行', bg='white', font=('Microsoft YaHei UI', 11, 'bold')).pack(side='left')
        self.start_button = ttk.Button(step3, text='开始', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='left', padx=(12, 6))
        self.stop_button = ttk.Button(step3, text='停止', command=self.stop)
        self.stop_button.pack(side='left')
        self.details_button = ttk.Button(step3, text='运行详情 ▸', command=self.toggle_details)
        self.details_button.pack(side='right')
        ttk.Button(step3, text='高级设置…', command=self.open_advanced).pack(side='right', padx=6)

        self.summary = tk.Label(self, bg='white', fg='#6b7280', anchor='w', justify='left')
        self.summary.pack(fill='x', pady=(6, 0))
        self.status = tk.StringVar(value=self._idle_text())
        tk.Label(self, textvariable=self.status, bg='white', anchor='w', justify='left',
                 font=('Microsoft YaHei UI', 10, 'bold')).pack(fill='x', pady=(4, 0))
        self.details = tk.Frame(self, bg='white')
        self.output = tk.Text(self.details, height=6, state='disabled', wrap='word',
                              font=('Microsoft YaHei UI', 9))
        self.output.pack(fill='both', expand=True, pady=(5, 0))

        for var in self.vars.values():
            var.trace_add('write', lambda *_: self._refresh_summary())
        self.keep_awake.trace_add('write', lambda *_: self._refresh_summary())
        self._refresh_summary()
        self._update_controls()
        self._poll_id = self.app.after(150, self.poll)

    # ----- 显示 -----
    def _idle_text(self):
        return '未登录 · 点击“登录学习通”打开官方页面'

    def _refresh_summary(self):
        v = {k: var.get() for k, var in self.vars.items()}
        parts = [label_of('login_mode', v['login_mode']), label_of('browser', v['browser']).split('（')[0],
                 f"{v['speed']} 倍速", label_of('choice', v['choice']).split('（')[0]]
        if v['choice'] != '不刷题':
            parts.append(label_of('after_finish_question', v['after_finish_question']))
        parts.append(label_of('discussion_choice', v['discussion_choice']))
        if v['task_type'] == '作业':
            parts.append('作业模式（只保存）')
        if v['parallel'] != '1':
            parts.append(f"同时 {v['parallel']} 门（各自登录）")
        if v['start_at'].strip() or v['end_at'].strip():
            parts.append('已设定时')
        self.summary.configure(text='当前设置：' + ' · '.join(parts))
        self.login_hint.configure(text=f"{label_of('login_mode', v['login_mode'])} · 不需要先保存密码"
                                  if v['login_mode'] == 'qr' else '账号密码登录 · 在高级设置中选择账号')

    def _update_controls(self):
        state = self.runner.state
        parallel = self.vars['parallel'].get() != '1'
        busy = self.runner.running
        self.login_button.configure(state='disabled' if busy or parallel else 'normal')
        self.refresh_button.configure(state='normal' if state == 'ready' else 'disabled')
        can_start = (state == 'ready') or (parallel and not busy)
        self.start_button.configure(state='normal' if can_start else 'disabled')
        self.stop_button.configure(state='normal' if busy else 'disabled')

    def toggle_details(self, show=None):
        show = not self.details.winfo_ismapped() if show is None else show
        if show:
            self.details.pack(fill='both', expand=True)
            self.details_button.configure(text='运行详情 ▾')
        else:
            self.details.pack_forget()
            self.details_button.configure(text='运行详情 ▸')

    def set_courses(self, names):
        selected = set(self.selected_courses())
        self.course_list.delete(0, 'end')
        for name in names:
            self.course_list.insert('end', name)
            if name in selected:
                self.course_list.selection_set('end')
        self.course_hint.configure(text=f'共 {len(names)} 门，可按住 Ctrl 多选' if names
                                   else '未能读取课程列表，请在下方手动输入课程名')

    def selected_courses(self):
        return [self.course_list.get(i) for i in self.course_list.curselection()]

    def log(self, text):
        self.output.configure(state='normal')
        self.output.insert('end', text + '\n')
        if int(self.output.index('end-1c').split('.')[0]) > 500:
            self.output.delete('1.0', '100.0')
        self.output.see('end')
        self.output.configure(state='disabled')

    # ----- 设置 -----
    def settings(self):
        cfg = {k: v.get() for k, v in self.vars.items()}
        manual = [x.strip() for x in self.courses.get('1.0', 'end').splitlines() if x.strip()]
        cfg['courses'] = self.selected_courses() + manual
        cfg['lock_screen'] = self.keep_awake.get()
        return cfg

    def selected_account(self):
        return next((a for a in self.app.accounts if a.get('username') == self.account.get()), {})

    def save(self, quiet=False):
        # 保存不完整的 AI 设置也有用；有效性在开始时检查。
        cfg = {k: self.vars[k].get() for k in STORED}
        cfg['courses'] = [x.strip() for x in self.courses.get('1.0', 'end').splitlines() if x.strip()]
        cfg['lock_screen'] = self.keep_awake.get()
        cfg['account'] = self.account.get()
        self.app.preferences['course_learning'] = cfg
        try:
            self.app.save_preferences()
        except OSError:
            messagebox.showerror('保存失败', '无法写入本地设置，请检查文件权限。', parent=self)
            return False
        if not quiet:
            self.status.set('课程设置已保存（不含 API Key）')
        return True

    def choose_driver(self, parent=None):
        path = filedialog.askopenfilename(title='选择浏览器驱动', filetypes=[('驱动', '*.exe')], parent=parent or self)
        if path:
            self.vars['driver_path'].set(path)

    # ----- 操作 -----
    def login(self):
        if not self.app._ensure_disclaimer('同意并继续登录'):
            self.status.set('未同意用户须知，未打开浏览器')
            return
        try:
            self.runner.login(self.selected_account(), self.settings())
        except ValueError as exc:
            messagebox.showerror('无法登录', str(exc), parent=self)
            return
        self.set_courses([])
        self.course_hint.configure(text='登录后自动读取“我学的课”，可按住 Ctrl 多选')
        self._update_controls()

    def refresh_courses(self):
        try:
            self.runner.refresh_courses()
        except ValueError as exc:
            messagebox.showerror('无法刷新', str(exc), parent=self)

    def start(self):
        if not self.app._ensure_disclaimer('同意并继续'):
            self.status.set('未同意用户须知，未开始')
            return
        cfg = self.settings()
        try:
            if str(cfg['parallel']) != '1':
                self.runner.start(self.selected_account(), cfg)
            else:
                self.runner.run_courses(cfg)
        except ValueError as exc:
            messagebox.showerror('无法开始', str(exc), parent=self)
            return
        self.save(quiet=True)
        self._update_controls()

    def stop(self):
        self.runner.stop()
        self._update_controls()

    def poll(self):
        try:
            while True:
                kind, payload = self.runner.events.get_nowait()
                if kind == 'status':
                    self.status.set(payload)
                    self.log('· ' + payload)
                elif kind == 'error':
                    self.status.set(payload)
                    self.log('错误：' + payload)
                    self.toggle_details(True)
                elif kind == 'courses':
                    self.set_courses(payload)
                elif kind == 'results':
                    for course, outcome in payload:
                        self.log(f'{course}：{outcome}')
                elif kind == 'log':
                    self.log(payload)
        except queue.Empty:
            pass
        self._update_controls()
        self._poll_id = self.app.after(150, self.poll)

    # ----- 高级设置 -----
    def open_advanced(self):
        if self._advanced is not None and self._advanced.winfo_exists():
            self._advanced.lift()
            return
        win = self._advanced = tk.Toplevel(self)
        win.withdraw()
        win.title('课程学习 · 高级设置')
        win.transient(self.app)
        win.configure(bg='white')
        footer = tk.Frame(win, bg='white')
        footer.pack(side='bottom', fill='x', padx=20, pady=12)
        ttk.Button(footer, text='完成', style='Accent.TButton',
                   command=lambda: self.save(quiet=True) and win.destroy()).pack(side='right')
        ttk.Button(footer, text='恢复默认', command=self.reset_defaults).pack(side='right', padx=6)
        body = tk.Frame(win, bg='white')
        body.pack(fill='both', expand=True, padx=20, pady=(16, 0))
        # 两栏布局，避免在 1080p/125% 缩放下超出屏幕高度。
        columns = [tk.Frame(body, bg='white'), tk.Frame(body, bg='white')]
        columns[0].pack(side='left', fill='y', anchor='n')
        columns[1].pack(side='left', fill='y', anchor='n', padx=(24, 0))
        at = {'frame': columns[0], 'row': 0}

        def place(widget, column=1, **grid):
            widget.grid(row=at['row'], column=column, sticky='w', **grid)

        def heading(text):
            place(tk.Label(at['frame'], text=text, bg='white', font=('Microsoft YaHei UI', 10, 'bold')),
                  column=0, columnspan=3, pady=(10 if at['row'] else 0, 2))
            at['row'] += 1

        def note(text):
            # Tk 只在 ASCII 空格处换行；中文说明改用不换行空格，避免“大于 1 / 时”式断行。
            place(tk.Label(at['frame'], text=text.replace(' ', '\u00a0'), bg='white', fg='#6b7280',
                           wraplength=300, justify='left'),
                  columnspan=2, padx=6)
            at['row'] += 1

        def labelled(label, widget):
            place(tk.Label(at['frame'], text=label, bg='white'), column=0, pady=2)
            place(widget, padx=6)
            at['row'] += 1
            return widget

        def choice(label, key):
            options = OPTIONS[key]
            shown = tk.StringVar(value=label_of(key, self.vars[key].get()))
            box = ttk.Combobox(at['frame'], textvariable=shown, values=[t for _, t in options],
                               state='readonly', width=28)
            box.bind('<<ComboboxSelected>>', lambda _: self.vars[key].set(
                next(v for v, t in options if t == shown.get())))
            return labelled(label, box)

        def entry(label, key, secret=False):
            return labelled(label, ttk.Entry(at['frame'], textvariable=self.vars[key],
                                             show='*' if secret else '', width=30))

        heading('登录与浏览器')
        choice('登录方式', 'login_mode')
        labelled('账号（密码登录用）', ttk.Combobox(
            at['frame'], textvariable=self.account, state='readonly', width=28,
            values=[a.get('username', '') for a in self.app.accounts]))
        note('账号来自“签到”页的账号管理；扫码登录不需要保存账号或密码。')
        choice('浏览器', 'browser')
        entry('驱动路径（可留空）', 'driver_path')
        ttk.Button(at['frame'], text='选择驱动…', command=lambda: self.choose_driver(win)).grid(
            row=at['row'], column=1, sticky='w', padx=6, pady=(2, 0))
        at['row'] += 1

        heading('学习')
        choice('任务类型', 'task_type')
        entry('播放倍速（0.5–16）', 'speed')
        choice('同时运行课程数', 'parallel')
        note('大于 1 时，每门课程单独打开浏览器，需要分别登录；“登录学习通”按钮此时不使用。')
        entry('定时开始', 'start_at')
        entry('定时结束', 'end_at')
        note('格式 YYYY-MM-DD HH:MM，留空表示立即开始/不限时；到结束时间会关闭本次浏览器。')
        place(tk.Checkbutton(at['frame'], text='运行时保持电脑唤醒', variable=self.keep_awake, bg='white'), padx=2)
        at['row'] += 1

        at.update(frame=columns[1], row=0)
        heading('答题与 AI（默认关闭）')
        choice('章节测验', 'choice')
        choice('测验答完后', 'after_finish_question')
        note('“自动提交”会正式交卷且不可撤回；“只保存”需要你在官方页面检查后自行提交。作业模式始终只保存。')
        choice('讨论', 'discussion_choice')
        choice('作业选择', 'homework')
        entry('AI 模型', 'ai_model')
        entry('DeepSeek API Key', 'api_key', secret=True)
        note('API Key 只在本次运行使用，不写入设置文件；题目内容会发送给 DeepSeek。')

        place_in_work_area(self.app, win)
        win.deiconify()

    def reset_defaults(self):
        for key in STORED:
            self.vars[key].set(str(DEFAULTS[key]))
        self.keep_awake.set(False)
        if self._advanced is not None and self._advanced.winfo_exists():
            self._advanced.destroy()
            self.open_advanced()

    def destroy(self):
        self.runner.stop()
        if self._poll_id:
            self.app.after_cancel(self._poll_id)
        super().destroy()
