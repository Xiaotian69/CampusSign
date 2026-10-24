"""课程工作进程调度；不导入或调用签到核心。"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import uuid

from paths import resource_root


DEFAULTS = {
    'courses': [], 'browser': 'auto', 'driver_path': '', 'login_mode': 'qr',
    'task_type': '课程', 'choice': '不刷题', 'speed': 1.0,
    'api_key': '', 'ai_model': 'deepseek-chat',
    'discussion_choice': '跳过讨论', 'after_finish_question': '仅自动保存',
    'homework': '自动选择', 'lock_screen': False, 'start_at': '', 'end_at': '',
    'parallel': 1,
}


def parse_time(value):
    return dt.datetime.strptime(value.strip(), '%Y-%m-%d %H:%M') if value.strip() else None


def validate_settings(settings, require_courses=True):
    cfg = {k: settings.get(k, v) for k, v in DEFAULTS.items()}
    courses = cfg['courses']
    if isinstance(courses, str):
        courses = courses.splitlines()
    if not isinstance(courses, list):
        raise ValueError('课程列表格式错误')
    cfg['courses'] = list(dict.fromkeys(str(c).strip() for c in courses if str(c).strip()))
    if not cfg['courses'] and require_courses:
        raise ValueError('请至少选择或输入一门课程')
    if any(re.search(r'[\\/:*?"<>|\x00-\x1f]', c) or '..' in c or len(c) > 100 or c.endswith('.')
           for c in cfg['courses']):
        raise ValueError('课程名不能包含 \\ / : * ? " < > | 等字符、以句点结尾或超过 100 字符；'
                         '可在手动输入框只填写课程名中的一段文字')
    try:
        cfg['speed'] = float(cfg['speed'])
    except (TypeError, ValueError):
        raise ValueError('倍速必须是数字') from None
    if not math.isfinite(cfg['speed']) or not 0.5 <= cfg['speed'] <= 16:
        raise ValueError('倍速范围为 0.5–16')
    try:
        cfg['parallel'] = int(cfg['parallel'])
    except (TypeError, ValueError):
        raise ValueError('同时运行课程数必须是整数') from None
    if not 1 <= cfg['parallel'] <= 3:
        raise ValueError('同时运行课程数范围为 1–3')
    choices = {
        'browser': ('auto', 'edge', 'chrome'), 'login_mode': ('account', 'qr'),
        'task_type': ('课程', '作业'), 'choice': ('不刷题', 'DeepSeek AI', '随机答题'),
        'discussion_choice': ('跳过讨论', 'DeepSeek AI'),
        'after_finish_question': ('仅自动保存', '强制自动提交'),
        'homework': ('自动选择', '手动选择'),
    }
    for key, allowed in choices.items():
        if cfg[key] not in allowed:
            raise ValueError(f'无效设置：{key}')
    if cfg['task_type'] == '作业' and cfg['choice'] != 'DeepSeek AI':
        raise ValueError('作业模式请选择 DeepSeek AI 答题方式')
    if (cfg['choice'] == 'DeepSeek AI' or cfg['discussion_choice'] == 'DeepSeek AI'
            or cfg['task_type'] == '作业') and not str(cfg['api_key']).strip():
        raise ValueError('AI 答题、讨论和作业功能需要填写自己的 API Key')
    if not str(cfg['ai_model']).strip():
        raise ValueError('请填写 AI 模型名称')
    try:
        start, end = parse_time(cfg['start_at']), parse_time(cfg['end_at'])
    except (ValueError, AttributeError):
        raise ValueError('定时时间格式：YYYY-MM-DD HH:MM，留空表示不设置') from None
    if end and end <= (start or dt.datetime.now()):
        raise ValueError('结束时间必须晚于开始时间和当前时间')
    if end and end <= dt.datetime.now():
        raise ValueError('结束时间已经过去')
    return cfg


def redact(text, secrets=()):
    text = re.sub(r'\x1b\[[0-9;]*m', '', str(text))
    for secret in sorted((str(s) for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[已隐藏]')
    text = re.sub(r'(?i)(password|token|api[_ -]?key|cookie)(\s*[:=]\s*)\S+', r'\1\2[已隐藏]', text)
    text = re.sub(r'(?i)Bearer\s+\S+|sk-[\w-]+', '[已隐藏]', text)
    text = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '[手机号]', text)
    return text

def validate_login(settings):
    """登录只需要浏览器和登录方式；答题等设置在开始课程时再校验。"""
    cfg = {k: settings.get(k, DEFAULTS[k]) for k in ('browser', 'driver_path', 'login_mode')}
    if cfg['browser'] not in ('auto', 'edge', 'chrome'):
        raise ValueError('无效设置：browser')
    if cfg['login_mode'] not in ('account', 'qr'):
        raise ValueError('无效设置：login_mode')
    cfg['driver_path'] = str(cfg['driver_path'] or '').strip()
    return cfg


EVENT_PREFIX = '@@CXSIGN '

STATE_TEXT = {
    'idle': '未登录 · 点击“登录学习通”打开官方页面',
    'starting': '正在启动课程进程…',
    'driver': '正在启动浏览器（首次使用可能需要联网下载驱动，请稍候）…',
    'waiting_login': '请在弹出的浏览器中扫码或登录学习通（10 分钟内有效）',
    'loading_courses': '登录成功，正在读取课程列表…',
    'ready': '已登录 · 选择课程后点击“开始”',
    'waiting_start': '等待定时开始（请保持本软件运行）',
    'running': '课程任务运行中 · 点击“停止”会关闭本次浏览器',
    'stopping': '正在停止并关闭本次浏览器…',
}


class CourseRunner:
    """管理本程序启动的课程进程：一个登录会话，或并行模式下的多个独立进程。"""

    def __init__(self, root):
        self.root = Path(root)
        self.events = queue.Queue(maxsize=1000)
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.processes = set()
        self.session = None
        self.thread = None
        self.state = 'idle'
        self._secrets = []

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def emit(self, kind, message):
        try:
            self.events.put_nowait((kind, message))
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            self.events.put_nowait((kind, message))

    def _set_state(self, state, text=None):
        self.state = state
        self.emit('state', state)
        self.emit('status', text or STATE_TEXT[state])

    # ----- 登录会话：登录一次，之后按需处理所选课程 -----
    def login(self, account, settings):
        if self.running:
            raise ValueError('浏览器已打开；如需重新登录，请先点击“停止”')
        cfg = validate_login(settings)
        account = dict(account or {})
        if cfg['login_mode'] == 'account':
            if not (account.get('username') and account.get('password')):
                raise ValueError('账号密码登录需要先在“签到”页添加带密码的账号；也可以改用扫码登录')
        else:
            account = {}  # 扫码登录不发送已保存的账号密码
        self.cancel.clear()
        self._secrets = [account.get('username'), account.get('password')]
        self._set_state('starting')
        self.thread = threading.Thread(target=self._session, args=(account, cfg), daemon=True)
        self.thread.start()

    def _session(self, account, cfg):
        payload = {'mode': 'session', 'browser': cfg['browser'], 'driver_path': cfg['driver_path'],
                   'login_mode': cfg['login_mode'], 'account': self._account_payload(account)}
        process, failed = None, False
        try:
            process = self._spawn(self._run_dir(account), payload)
            if process is None:
                return
            self.session = process
            for line in process.stdout:
                failed = self._handle_line(line) or failed
            code = process.wait(timeout=10)
            if code and not self.cancel.is_set() and not failed:
                self.emit('error', f'课程进程异常退出（{code}），请展开“运行详情”查看')
        except Exception as exc:
            self.emit('error', '课程进程启动失败：' + type(exc).__name__)
        finally:
            self.session = None
            if process is not None:
                self._terminate(process)
                self._close(process)
            self._set_state('idle', '已停止，本次浏览器已关闭' if self.cancel.is_set()
                            else '浏览器已关闭 · 如需继续请重新登录')

    def _handle_line(self, line):
        """处理 worker 的一行输出；worker 报告错误时返回 True。"""
        line = line.rstrip('\r\n')
        if line.startswith(EVENT_PREFIX):
            try:
                event = json.loads(line[len(EVENT_PREFIX):])
            except ValueError:
                event = None
            if isinstance(event, dict):
                kind = event.get('event')
                if kind == 'state' and event.get('state') in STATE_TEXT:
                    # 处理结束后 worker 会再报一次 ready，保留结果摘要不覆盖。
                    if not (event['state'] == 'ready' and self.state == 'ready'):
                        self._set_state(event['state'])
                elif kind == 'courses':
                    items = [redact(c, self._secrets) for c in event.get('items', []) if isinstance(c, str)]
                    self.emit('courses', items)
                    if not items:
                        self.emit('log', '未能读取课程列表，请在手动输入框填写课程名')
                elif kind == 'run_done':
                    results = [(redact(c, self._secrets), redact(r, self._secrets))
                               for c, r in event.get('results', [])]
                    self.emit('results', results)
                    failed = sum(1 for _, r in results if r.startswith('失败'))
                    self._set_state('ready', f'本次处理结束：{len(results) - failed} 门处理到末尾，{failed} 门失败'
                                    ' · 完成情况以学习通页面为准')
                elif kind == 'error':
                    self.emit('error', redact(event.get('message', '课程任务失败'), self._secrets))
                    return True
                return False
        self.emit('log', redact(line, self._secrets))
        return False

    def refresh_courses(self):
        if self.state != 'ready' or self.session is None:
            raise ValueError('请先登录学习通')
        self._send(self.session, {'cmd': 'refresh'})

    def run_courses(self, settings):
        cfg = validate_settings(settings)
        if cfg['parallel'] > 1:
            raise ValueError('同时运行多门课程时请使用并行模式')
        if self.state != 'ready' or self.session is None:
            raise ValueError('请先点击“登录学习通”并在浏览器中完成登录')
        self._secrets.append(cfg['api_key'])
        command = {'cmd': 'run', 'config': {k: v for k, v in cfg.items()
                                            if k not in ('start_at', 'end_at', 'parallel')}}
        self._set_state('running')
        threading.Thread(target=self._schedule, args=(self.session, command, cfg), daemon=True).start()

    def _schedule(self, session, command, cfg):
        start, end = parse_time(cfg['start_at']), parse_time(cfg['end_at'])
        if start and start > dt.datetime.now():
            self._set_state('waiting_start')
            while start > dt.datetime.now():
                wait = max(0.001, min(0.5, (start - dt.datetime.now()).total_seconds()))
                if self.cancel.wait(wait) or session.poll() is not None:
                    return
            self._set_state('running')
        if not self._send(session, command):
            return
        while end and self.state == 'running' and session.poll() is None and not self.cancel.is_set():
            if dt.datetime.now() >= end:
                self.emit('status', '已到定时结束时间，正在关闭浏览器')
                self.stop()
                return
            self.cancel.wait(0.5)

    def _send(self, process, command):
        try:
            with self.lock:
                process.stdin.write(json.dumps(command, ensure_ascii=False) + '\n')
                process.stdin.flush()
            return True
        except (OSError, ValueError, AttributeError):
            self.emit('error', '课程进程已结束，请重新登录')
            return False

    # ----- 并行模式：每门课程独立浏览器、独立登录 -----
    def start(self, account, settings):
        if self.running:
            raise ValueError('课程任务正在运行，请先停止')
        cfg = validate_settings(settings)
        account = dict(account or {})
        if cfg['login_mode'] == 'account' and not (account.get('username') and account.get('password')):
            raise ValueError('账号密码登录需要先在“签到”页添加带密码的账号；也可以改用扫码登录')
        if cfg['login_mode'] == 'qr':
            account = {}
        self.cancel.clear()
        self._secrets = [account.get('username'), account.get('password'), cfg['api_key']]
        self.thread = threading.Thread(target=self._run, args=(account, cfg), daemon=True)
        self.thread.start()

    def _run(self, account, cfg):
        try:
            start = parse_time(cfg['start_at'])
            if start and start > dt.datetime.now():
                self._set_state('waiting_start')
                while start > dt.datetime.now():
                    if self.cancel.wait(max(0.001, min(0.5, (start - dt.datetime.now()).total_seconds()))):
                        return
            if not self.cancel.is_set():
                self._set_state('running', f'正在处理 {len(cfg["courses"])} 门课程 · 每个浏览器需分别登录')
                if cfg['parallel'] == 1:
                    self._execute(account, cfg)
                else:
                    with ThreadPoolExecutor(max_workers=cfg['parallel']) as pool:
                        futures = [pool.submit(self._execute, account, dict(cfg, courses=[course]))
                                   for course in cfg['courses']]
                        for future in as_completed(futures):
                            future.result()
        except Exception as exc:
            self.emit('error', '课程任务失败：' + type(exc).__name__)
        finally:
            self._set_state('idle', '已停止' if self.cancel.is_set() else '任务进程已结束，请核对课程进度')

    def _execute(self, account, cfg):
        payload = dict(cfg, account=self._account_payload(account))
        process = self._spawn(self._run_dir(account), payload, close_stdin=True)
        if process is None:
            return
        label = '[' + cfg['courses'][0] + '] ' if cfg['parallel'] > 1 else ''
        try:
            def read_output():
                for line in process.stdout:
                    self.emit('log', label + redact(line.rstrip(), self._secrets))
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            end = parse_time(cfg['end_at'])
            while process.poll() is None:
                if self.cancel.wait(0.2) or (end and dt.datetime.now() >= end):
                    self.cancel.set()
                    self._terminate(process)
                    break
            code = process.wait(timeout=10)
            reader.join(2)
            if code and not self.cancel.is_set():
                self.emit('error', f'{label}课程进程异常退出（{code}），请展开“运行详情”查看')
        finally:
            if process.poll() is None:
                self._terminate(process)
            self._close(process)

    # ----- 进程管理：只结束本程序启动的进程树 -----
    @staticmethod
    def _account_payload(account):
        return {'uname': account.get('username', ''), 'password': account.get('password', ''),
                'fid': account.get('schoolid', '')}

    def _run_dir(self, account):
        account_id = hashlib.sha256((account.get('username') or 'qr').encode()).hexdigest()[:16]
        run_dir = self.root / account_id / uuid.uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _spawn(self, run_dir, payload, close_stdin=False):
        command = ([sys.executable, '--course-worker'] if getattr(sys, 'frozen', False)
                   else [sys.executable, '-u', str(resource_root() / 'course_worker.py')])
        environment = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
        with self.lock:
            if self.cancel.is_set():
                return None
            process = subprocess.Popen(command, cwd=run_dir, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       encoding='utf-8', errors='replace', env=environment,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.processes.add(process)
            # 凭据只经由标准输入传递，不出现在命令行参数中。
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + '\n')
            process.stdin.flush()
            if close_stdin:
                process.stdin.close()
        return process

    def _close(self, process):
        with self.lock:
            self.processes.discard(process)
        for stream in (process.stdin, process.stdout):
            try:
                if stream:
                    stream.close()
            except (OSError, ValueError):
                pass

    @staticmethod
    def _terminate(process):
        if process.poll() is not None:
            return
        if os.name == 'nt':
            try:
                result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                if result.returncode and process.poll() is None:
                    process.kill()
            except subprocess.TimeoutExpired:
                process.kill()
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def stop(self):
        self.cancel.set()
        with self.lock:
            processes = list(self.processes)
        if processes:
            # 只有 worker 空闲等待命令时才能自行退出；运行中直接结束进程树。
            idle = self.state in ('ready', 'waiting_start')
            self._set_state('stopping')
            threading.Thread(target=self._shutdown, args=(processes, idle), daemon=True).start()

    def _shutdown(self, processes, idle=False):
        session = self.session
        if idle and session in processes and session.poll() is None:
            # 先请求 worker 自行关闭浏览器，超时再结束整个进程树。
            self._send(session, {'cmd': 'quit'})
            try:
                session.wait(timeout=8)
            except subprocess.TimeoutExpired:
                pass
        for process in processes:
            self._terminate(process)
