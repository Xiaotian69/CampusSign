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
    'courses': [], 'browser': 'edge', 'driver_path': '', 'login_mode': 'qr',
    'task_type': '课程', 'choice': '不刷题', 'speed': 1.0,
    'api_key': '', 'ai_model': 'deepseek-chat',
    'discussion_choice': '跳过讨论', 'after_finish_question': '仅自动保存',
    'homework': '自动选择', 'lock_screen': False, 'start_at': '', 'end_at': '',
    'parallel': 1,
}


def parse_time(value):
    return dt.datetime.strptime(value.strip(), '%Y-%m-%d %H:%M') if value.strip() else None


def validate_settings(settings):
    cfg = {k: settings.get(k, v) for k, v in DEFAULTS.items()}
    courses = cfg['courses']
    if isinstance(courses, str):
        courses = courses.splitlines()
    if not isinstance(courses, list):
        raise ValueError('课程列表格式错误')
    cfg['courses'] = list(dict.fromkeys(str(c).strip() for c in courses if str(c).strip()))
    if not cfg['courses']:
        raise ValueError('请至少输入一门课程，每行一门')
    if any(re.search(r'[\\/:*?"<>|\x00-\x1f]', c) or '..' in c or len(c) > 100 or c.endswith('.')
           for c in cfg['courses']):
        raise ValueError('课程名不能包含路径字符、以句点结尾或超过 100 字符')
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
        'browser': ('edge', 'chrome'), 'login_mode': ('account', 'qr'),
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


class CourseRunner:
    def __init__(self, root):
        self.root = Path(root)
        self.events = queue.Queue(maxsize=1000)
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.process = None
        self.thread = None

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

    def start(self, account, settings):
        if self.running:
            raise ValueError('课程任务正在运行，请先停止')
        cfg = validate_settings(settings)
        if not account.get('username'):
            raise ValueError('请选择一个现有账号')
        if cfg['login_mode'] == 'account' and not account.get('password'):
            raise ValueError('该账号没有保存密码，请改用扫码登录')
        self.cancel.clear()
        self.thread = threading.Thread(target=self._run, args=(dict(account), cfg), daemon=True)
        self.thread.start()

    def _run(self, account, cfg):
        try:
            start = parse_time(cfg['start_at'])
            if start and start > dt.datetime.now():
                self.emit('status', '等待定时开始（请保持本软件运行）')
                while start > dt.datetime.now():
                    if self.cancel.wait(max(0.001, min(0.5, (start - dt.datetime.now()).total_seconds()))):
                        return
            if not self.cancel.is_set():
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
            self.emit('done', '已停止' if self.cancel.is_set() else '任务进程已结束，请核对课程进度')

    def _execute(self, account, cfg):
        account_id = hashlib.sha256(account['username'].encode()).hexdigest()[:16]
        run_dir = self.root / account_id / uuid.uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        payload = dict(cfg, account={'uname': account['username'], 'password': account.get('password', ''),
                                    'fid': account.get('schoolid', '')})
        command = ([sys.executable, '--course-worker'] if getattr(sys, 'frozen', False)
                   else [sys.executable, '-u', str(resource_root() / 'course_worker.py')])
        environment = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
        with self.lock:
            if self.cancel.is_set():
                return
            self.process = subprocess.Popen(command, cwd=run_dir, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            encoding='utf-8', errors='replace', env=environment,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            process = self.process
        secrets = (account['username'], account.get('password'), cfg['api_key'])
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False))
            process.stdin.close()
            self.emit('status', '课程任务运行中')
            def read_output():
                for line in process.stdout:
                    self.emit('log', redact(line.rstrip(), secrets))
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
                self.emit('error', f'课程进程异常退出（{code}），请检查上方信息')
        finally:
            if process.poll() is None:
                self._terminate(process)
            with self.lock:
                self.process = None
            if process.stdout:
                process.stdout.close()

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
