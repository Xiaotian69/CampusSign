import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

from course_runner import validate_settings, redact, CourseRunner


class CourseRunnerTests(unittest.TestCase):
    def test_validation_and_no_secrets_in_arguments(self):
        cfg = validate_settings({'courses': '示例课程A\n示例课程B', 'speed': '1.5'})
        self.assertEqual(cfg['courses'], ['示例课程A', '示例课程B'])
        self.assertEqual(cfg['speed'], 1.5)
        for bad in ('../逃逸', 'a/b', 'a\\b', 'a:b'):
            with self.assertRaises(ValueError):
                validate_settings({'courses': bad})

    def test_invalid_settings_fail_before_spawn(self):
        for extra in ({'speed': 'nan'}, {'speed': '0'}, {'courses': ''},
                      {'start_at': 'wrong'}, {'browser': 'bad'},
                      {'choice': 'DeepSeek AI', 'api_key': ''}):
            with self.assertRaises(ValueError):
                validate_settings({'courses': '示例课程', **extra})

    def test_time_order(self):
        with self.assertRaises(ValueError):
            validate_settings({'courses': '示例课程', 'start_at': '2099-01-02 10:00',
                               'end_at': '2099-01-02 09:00'})

    def test_redaction(self):
        text = redact('password=example-secret token=abcd Bearer abc sk-test123', ['example-secret'])
        self.assertNotIn('example-secret', text)
        self.assertNotIn('abcd', text)
        self.assertNotIn('sk-test123', text)

    def test_worker_credentials_stdin_only_and_unique_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = CourseRunner(Path(tmp))
            proc = MagicMock()
            proc.stdin = io.StringIO()
            # Preserve stdin contents after runner closes it.
            proc.stdin.close = lambda: None
            proc.stdout = io.StringIO('done\n')
            proc.wait.return_value = 0
            proc.poll.return_value = 0
            with patch('course_runner.subprocess.Popen', return_value=proc) as spawn:
                runner._execute({'username': 'example-user', 'password': 'example-secret'},
                                validate_settings({'courses': '示例课程'}))
            args = spawn.call_args.args[0]
            self.assertNotIn('example-secret', str(args))
            self.assertNotIn('example-user', str(args))
            self.assertEqual(json.loads(proc.stdin.getvalue())['account']['password'], 'example-secret')
            self.assertTrue(Path(spawn.call_args.kwargs['cwd']).is_relative_to(Path(tmp)))
            self.assertNotIn('example-user', str(spawn.call_args.kwargs['cwd']))

    def test_stop_scheduled_task_does_not_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = CourseRunner(Path(tmp))
            with patch.object(runner, '_execute') as execute:
                runner.start({'username': 'example'}, {'courses': '示例课程', 'start_at': '2099-01-01 12:00'})
                runner.stop()
                runner.thread.join(2)
                execute.assert_not_called()
            self.assertFalse(runner.running)

    def test_parallel_courses_dispatch_separate_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = CourseRunner(Path(tmp))
            with patch.object(runner, '_execute') as execute:
                runner.start({'username': 'example'}, {'courses': '课程甲\n课程乙', 'parallel': 2})
                runner.thread.join(3)
                self.assertEqual(execute.call_count, 2)
                self.assertEqual(sorted(c.args[1]['courses'] for c in execute.call_args_list), [['课程乙'], ['课程甲']])

    def test_qr_login_sends_no_saved_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = CourseRunner(Path(tmp))
            with patch.object(runner, '_spawn', return_value=None) as spawn:
                runner.login({'username': 'example-user', 'password': 'example-secret'}, {'login_mode': 'qr'})
                runner.thread.join(2)
            payload = spawn.call_args.args[1]
            self.assertEqual(payload['mode'], 'session')
            self.assertEqual(payload['account']['uname'], '')
            self.assertEqual(payload['account']['password'], '')

    def test_login_ignores_course_and_ai_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = CourseRunner(Path(tmp))
            with patch.object(runner, '_spawn', return_value=None) as spawn:
                # 尚未选课程、AI 设置不完整也可以先登录。
                runner.login({}, {'courses': '', 'choice': 'DeepSeek AI', 'api_key': ''})
                runner.thread.join(2)
            spawn.assert_called_once()

    def test_account_login_requires_saved_password(self):
        runner = CourseRunner(Path(tempfile.gettempdir()))
        with self.assertRaises(ValueError):
            runner.login({'username': 'example-user'}, {'login_mode': 'account'})
        self.assertIsNone(runner.thread)

    def test_worker_events_drive_state_and_courses(self):
        runner = CourseRunner(Path(tempfile.gettempdir()))
        runner._secrets = ['example-secret']
        runner._handle_line('@@CXSIGN {"event": "state", "state": "waiting_login"}\n')
        runner._handle_line('@@CXSIGN {"event": "courses", "items": ["课程甲", "课程乙"]}\n')
        runner._handle_line('@@CXSIGN {"event": "state", "state": "ready"}\n')
        runner._handle_line('@@CXSIGN {"event": "run_done", "results": [["课程甲", "已遍历"], ["课程乙", "失败：未找到课程页面"]]}\n')
        runner._handle_line('@@CXSIGN {"event": "state", "state": "ready"}\n')
        self.assertTrue(runner._handle_line('@@CXSIGN {"event": "error", "message": "无法启动浏览器"}\n'))
        runner._handle_line('password=example-secret\n')
        events = []
        while not runner.events.empty():
            events.append(runner.events.get_nowait())
        self.assertIn(('courses', ['课程甲', '课程乙']), events)
        statuses = [m for k, m in events if k == 'status']
        self.assertIn('请在弹出的浏览器中扫码或登录学习通（10 分钟内有效）', statuses)
        # 结束摘要不应被随后重复的 ready 覆盖。
        self.assertTrue(statuses[-1].startswith('本次处理结束：1 门处理到末尾，1 门失败'))
        self.assertIn(('error', '无法启动浏览器'), events)
        self.assertNotIn('example-secret', str(events))
        self.assertEqual(runner.state, 'ready')

    def test_run_requires_login(self):
        runner = CourseRunner(Path(tempfile.gettempdir()))
        with self.assertRaises(ValueError):
            runner.run_courses({'courses': '示例课程'})

    def test_run_sends_command_to_logged_in_session(self):
        runner = CourseRunner(Path(tempfile.gettempdir()))
        session = MagicMock()
        session.stdin = io.StringIO()
        session.poll.return_value = None
        runner.session, runner.state = session, 'ready'
        runner.run_courses({'courses': '课程甲', 'api_key': ''})
        for _ in range(50):
            if session.stdin.getvalue():
                break
            threading.Event().wait(0.02)
        command = json.loads(session.stdin.getvalue())
        self.assertEqual(command['cmd'], 'run')
        self.assertEqual(command['config']['courses'], ['课程甲'])
        self.assertNotIn('start_at', command['config'])
        self.assertEqual(runner.state, 'running')

    def test_stop_idle_session_asks_worker_to_close_browser_first(self):
        runner = CourseRunner(Path(tempfile.gettempdir()))
        session = MagicMock()
        session.stdin = io.StringIO()
        session.poll.return_value = None
        runner.session, runner.state = session, 'ready'
        runner.processes.add(session)
        with patch.object(CourseRunner, '_terminate') as terminate:
            runner.stop()
            for _ in range(100):
                if terminate.called:
                    break
                threading.Event().wait(0.02)
        self.assertEqual(json.loads(session.stdin.getvalue()), {'cmd': 'quit'})
        session.wait.assert_called_with(timeout=8)
        terminate.assert_called_with(session)
        self.assertEqual(runner.state, 'stopping')

    def test_stop_running_session_skips_graceful_wait(self):
        runner = CourseRunner(Path(tempfile.gettempdir()))
        session = MagicMock()
        session.stdin = io.StringIO()
        session.poll.return_value = None
        runner.session, runner.state = session, 'running'
        runner.processes.add(session)
        with patch.object(CourseRunner, '_terminate') as terminate:
            runner.stop()
            for _ in range(100):
                if terminate.called:
                    break
                threading.Event().wait(0.02)
        self.assertEqual(session.stdin.getvalue(), '')
        terminate.assert_called_with(session)

    def test_failed_taskkill_falls_back_to_bounded_kill(self):
        proc = MagicMock()
        proc.poll.return_value = None
        with patch('course_runner.os.name', 'nt'), patch('course_runner.subprocess.run') as run:
            run.return_value.returncode = 1
            CourseRunner._terminate(proc)
        proc.kill.assert_called_once()
        proc.wait.assert_called_with(timeout=5)


if __name__ == '__main__':
    unittest.main()
