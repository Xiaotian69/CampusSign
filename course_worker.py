"""Isolated course worker. Read one JSON configuration from stdin, never argv."""
import json
import math
import re
import sys
from pathlib import Path


def restore_worker_streams():
    """Restore inherited pipes hidden by a windowed Python executable."""
    import os
    if os.name != 'nt':
        return
    import ctypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_ulong]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    for name, number, flags, mode in (('stdin', -10, os.O_RDONLY, 'r'),
                                     ('stdout', -11, os.O_WRONLY, 'w'),
                                     ('stderr', -12, os.O_WRONLY, 'w')):
        if getattr(sys, name) is None:
            handle = kernel.GetStdHandle(number & 0xffffffff)
            if handle in (None, ctypes.c_void_p(-1).value):
                raise RuntimeError('课程工作进程需要由主窗口启动')
            fd = msvcrt.open_osfhandle(handle, flags)
            setattr(sys, name, os.fdopen(fd, mode, encoding='utf-8', errors='replace', buffering=1))


EVENT_PREFIX = "@@CXSIGN "


def emit_event(stream, **event):
    """Structured status line for the main window; never contains credentials."""
    stream.write(EVENT_PREFIX + json.dumps(event, ensure_ascii=False) + "\n")
    stream.flush()


def describe_error(exc):
    """User-facing reason without exception text, which may contain secrets."""
    name = type(exc).__name__
    if name == "BrowserStartError":
        return str(exc)
    if isinstance(exc, TimeoutError):
        return "等待登录或官方验证超时，浏览器已关闭；请重新点击“登录学习通”。"
    if name in ("NoSuchWindowException", "InvalidSessionIdException"):
        return "浏览器窗口已被关闭。"
    if isinstance(exc, ModuleNotFoundError):
        return "缺少课程可选依赖，请安装 requirements-course.txt。"
    return "课程任务失败（" + name + "）；请检查浏览器页面。"


def validate_session(payload):
    if not isinstance(payload, dict):
        raise ValueError("配置必须是对象")
    session = {"browser": payload.get("browser", "auto"), "driver_path": payload.get("driver_path", ""),
               "login_mode": payload.get("login_mode", "qr"), "account": payload.get("account", {})}
    if session["browser"] not in ("auto", "edge", "chrome"): raise ValueError("不支持的浏览器")
    if session["login_mode"] not in ("account", "qr"): raise ValueError("不支持的登录方式")
    if not isinstance(session["driver_path"], str): raise ValueError("驱动路径格式错误")
    account = session["account"]
    if not isinstance(account, dict): raise ValueError("账号格式错误")
    if session["login_mode"] == "account" and not (account.get("uname") and account.get("password")):
        raise ValueError("缺少账号或密码")
    return session


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("配置必须是对象")
    c = dict(config)
    defaults = {"browser": "auto", "driver_path": "", "task_type": "课程", "choice": "不刷题", "api_key": "", "ai_model": "", "speed": 1.0, "discussion_choice": "跳过讨论", "after_finish_question": "仅自动保存", "homework": "自动选择", "login_mode": "account", "lock_screen": False}
    for key, value in defaults.items(): c.setdefault(key, value)
    allowed = {"browser": ("auto", "edge", "chrome"), "task_type": ("课程", "作业"), "choice": ("不刷题", "DeepSeek AI", "随机答题"), "discussion_choice": ("跳过讨论", "DeepSeek AI"), "after_finish_question": ("仅自动保存", "强制自动提交"), "homework": ("自动选择", "手动选择"), "login_mode": ("account", "qr")}
    for key, values in allowed.items():
        if c[key] not in values: raise ValueError("不支持的配置项：" + key)
    courses = c.get("courses")
    if not isinstance(courses, list) or not courses: raise ValueError("请输入课程名称")
    for name in courses:
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name in (".", "..") or name.endswith((".", " ")):
            raise ValueError("课程名称包含不安全字符")
    account = c.get("account", {})
    if not isinstance(account, dict): raise ValueError("账号格式错误")
    if c["login_mode"] == "account" and not (account.get("uname") and account.get("password")):
        raise ValueError("缺少账号或密码")
    c["speed"] = float(c["speed"])
    if not math.isfinite(c["speed"]) or not 0.5 <= c["speed"] <= 16: raise ValueError("倍速应在 0.5 到 16 之间")
    if c["choice"] == "DeepSeek AI" or c["discussion_choice"] == "DeepSeek AI":
        if not c["api_key"] or not c["ai_model"].strip(): raise ValueError("AI 需要自己的密钥和模型名称")
    if c["task_type"] == "作业" and c["choice"] == "不刷题": raise ValueError("作业任务需要选择答题方式")
    return c


def initialize_state(folder, config):
    (folder / "task/tool").mkdir(parents=True, exist_ok=True)
    (folder / "task/record").mkdir(parents=True, exist_ok=True)
    for name in ("course_name.json", "course_process.json"):
        path = folder / "task/tool" / name
        if not path.exists(): path.write_text("{}", encoding="utf-8")
    (folder / "task/tool/account_info.json").write_text(json.dumps({"speed": config["speed"]}), encoding="utf-8")


def execute(config):
    initialize_state(Path.cwd(), config)
    from third_party.course_engine.adapter import run
    run(config)


class RedactedOutput:
    def __init__(self, stream, secrets):
        self.stream = stream
        self.secrets = [str(s) for s in secrets if s]
    def add(self, secret):
        if secret: self.secrets.append(str(secret))
    def write(self, text):
        for secret in self.secrets: text = text.replace(secret, "[已隐藏]")
        return self.stream.write(text)
    def flush(self): self.stream.flush()


def run_session(payload, commands, stream):
    """Log in once, report courses, then run commands from stdin until quit/EOF.

    Commands (one JSON per line): {"cmd": "run", "config": {...}}, {"cmd": "refresh"}, {"cmd": "quit"}.
    """
    try:
        session = validate_session(payload)
    except ValueError as exc:
        emit_event(stream, event="error", message="配置无效：" + str(exc))
        return 1
    account = session["account"]
    output = RedactedOutput(stream, [account.get("uname"), account.get("password")])
    notify = lambda **event: emit_event(output, **event)
    from contextlib import redirect_stdout, redirect_stderr
    driver = None
    config = {}
    with redirect_stdout(output), redirect_stderr(output):
        try:
            from third_party.course_engine import adapter
            notify(event="state", state="driver")
            driver = adapter.create_driver(session)
            notify(event="state", state="waiting_login")
            adapter.login(driver, session)
            notify(event="state", state="loading_courses")
            notify(event="courses", items=adapter.list_courses(driver))
            notify(event="state", state="ready")
            for line in iter(commands.readline, ""):
                command = json.loads(line)
                if command.get("cmd") == "quit":
                    break
                if command.get("cmd") == "refresh":
                    notify(event="state", state="loading_courses")
                    notify(event="courses", items=adapter.list_courses(driver))
                elif command.get("cmd") == "run":
                    try:
                        config = validate_config(dict(command.get("config", {}), **session))
                    except ValueError as exc:
                        notify(event="error", message="配置无效：" + str(exc))
                        notify(event="state", state="ready")
                        continue
                    output.add(config.get("api_key"))
                    initialize_state(Path.cwd(), config)
                    notify(event="state", state="running")
                    results = adapter.run_courses(driver, config, keep_going=True)
                    adapter.release_keep_awake(config)
                    notify(event="run_done", results=results)
                notify(event="state", state="ready")
            return 0
        except Exception as exc:
            notify(event="error", message=describe_error(exc))
            return 1
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            if config:
                from third_party.course_engine.adapter import release_keep_awake
                release_keep_awake(config)


def main():
    restore_worker_streams()
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(sys.stdin.readline())
        if isinstance(payload, dict) and payload.get("mode") == "session":
            return run_session(payload, sys.stdin, sys.stdout)
        try:
            config = validate_config(payload)
        except ValueError as exc:
            print("配置无效：" + str(exc), flush=True)
            return 1
        from contextlib import redirect_stdout, redirect_stderr
        account = config.get("account", {})
        output = RedactedOutput(sys.stdout, [account.get("uname"), account.get("password"), config.get("api_key")])
        with redirect_stdout(output), redirect_stderr(output):
            execute(config)
        print("课程队列处理结束；请在官方页面核对任务完成情况。", flush=True)
        return 0
    except Exception as exc:
        # Exception messages may contain credentials, HTTP headers or AI prompts;
        # describe_error only passes through messages written by this project.
        print(describe_error(exc), flush=True)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
