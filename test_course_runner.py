import datetime as dt
import io
import json
from pathlib import Path
import tempfile
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
