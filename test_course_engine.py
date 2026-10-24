import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import course_worker as worker

class CourseWorkerTests(unittest.TestCase):
    def config(self):
        return {"account": {"uname": "student", "password": "secret"}, "courses": ["数学"]}

    def test_reject_path_traversal(self):
        for course in ["../escape", "x\\y", "C:secret", "a/../b", ".."]:
            cfg = self.config(); cfg["courses"] = [course]
            with self.assertRaises(ValueError): worker.validate_config(cfg)

    def test_ai_requires_explicit_key_and_model(self):
        cfg = self.config(); cfg["choice"] = "DeepSeek AI"
        with self.assertRaises(ValueError): worker.validate_config(cfg)

    def test_initialize_has_no_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            worker.initialize_state(Path(folder), worker.validate_config(self.config()))
            text = (Path(folder)/"task/tool/account_info.json").read_text()
            self.assertNotIn("secret", text)
            self.assertNotIn("student", text)

    def test_error_returns_nonzero_without_secret(self):
        cfg = self.config()
        output = io.StringIO()
        with patch.object(worker, "execute", side_effect=RuntimeError("secret")), patch("sys.stdin", io.StringIO(json.dumps(cfg))), patch("sys.stdout", output):
            self.assertEqual(worker.main(), 1)
        self.assertNotIn("secret", output.getvalue())

    def test_quit_on_engine_failure(self):
        from third_party.course_engine import adapter
        from unittest.mock import Mock
        driver = Mock()
        with patch.object(adapter, "create_driver", return_value=driver), patch.object(adapter, "login", side_effect=RuntimeError("fail")):
            with self.assertRaises(RuntimeError): adapter.run(worker.validate_config(self.config()))
        driver.quit.assert_called_once()

    def test_navigation_failure_quits_driver(self):
        from third_party.course_engine import adapter, navigation
        from unittest.mock import Mock
        driver = Mock()
        with patch.object(adapter, "create_driver", return_value=driver), patch.object(adapter, "login"), patch.object(navigation, "choice_course", side_effect=RuntimeError("navigation failed")):
            with self.assertRaises(RuntimeError): adapter.run(worker.validate_config(self.config()))
        driver.quit.assert_called_once()

    def test_manual_video_question_does_not_answer(self):
        from third_party.course_engine.task.watch_vido import check_video_question
        from unittest.mock import Mock
        driver = Mock()
        check_video_question(driver, "", "手动答题")
        self.assertEqual(driver.find_element.call_count, 1)
        driver.find_element.return_value.find_element.assert_not_called()

    def test_own_ai_only_and_structured_answer(self):
        import asyncio
        from third_party.course_engine.task.tool import ai_wen_da
        with patch.object(ai_wen_da, "DeepSeekAsk", return_value='["答案"]') as ask:
            self.assertEqual(asyncio.run(ai_wen_da.main("单选题", "问题", ["答案"], "my-key")), ["答案"])
            ask.assert_called_once()
        with patch.object(ai_wen_da, "DeepSeekAsk") as ask:
            self.assertEqual(asyncio.run(ai_wen_da.main("单选题", "问题", [], "")), [])
            ask.assert_not_called()

class CourseSessionTests(unittest.TestCase):
    def events(self, text):
        return [json.loads(line[len(worker.EVENT_PREFIX):]) for line in text.splitlines()
                if line.startswith(worker.EVENT_PREFIX)]

    def test_session_logs_in_lists_courses_then_runs_on_command(self):
        from third_party.course_engine import adapter
        from unittest.mock import Mock
        driver = Mock()
        commands = io.StringIO(json.dumps({"cmd": "run", "config": {"courses": ["课程甲"]}}) + "\n"
                               + json.dumps({"cmd": "quit"}) + "\n")
        out = io.StringIO()
        payload = {"mode": "session", "login_mode": "account", "account": {"uname": "student", "password": "secret"}}
        with tempfile.TemporaryDirectory() as folder, patch("course_worker.Path.cwd", return_value=Path(folder)), \
                patch.object(adapter, "create_driver", return_value=driver), patch.object(adapter, "login") as login, \
                patch.object(adapter, "list_courses", return_value=["课程甲", "课程乙"]), \
                patch.object(adapter, "run_courses", return_value=[("课程甲", "已遍历")]) as run:
            self.assertEqual(worker.run_session(payload, commands, out), 0)
        login.assert_called_once()
        self.assertEqual(run.call_args.args[1]["courses"], ["课程甲"])
        states = [e.get("state") for e in self.events(out.getvalue()) if e["event"] == "state"]
        self.assertEqual(states, ["driver", "waiting_login", "loading_courses", "ready", "running", "ready"])
        self.assertIn({"event": "courses", "items": ["课程甲", "课程乙"]}, self.events(out.getvalue()))
        driver.quit.assert_called_once()
        self.assertNotIn("secret", out.getvalue())

    def test_session_does_not_run_courses_before_command(self):
        from third_party.course_engine import adapter
        from unittest.mock import Mock
        with patch.object(adapter, "create_driver", return_value=Mock()), patch.object(adapter, "login"), \
                patch.object(adapter, "list_courses", return_value=[]), patch.object(adapter, "run_courses") as run:
            self.assertEqual(worker.run_session({"mode": "session"}, io.StringIO(""), io.StringIO()), 0)
        run.assert_not_called()

    def test_session_browser_failure_is_reported(self):
        from third_party.course_engine import adapter
        out = io.StringIO()
        error = adapter.BrowserStartError("无法启动浏览器（微软 Edge：NoSuchDriverException）。")
        with patch.object(adapter, "create_driver", side_effect=error):
            self.assertEqual(worker.run_session({"mode": "session"}, io.StringIO(""), out), 1)
        self.assertIn({"event": "error", "message": str(error)}, self.events(out.getvalue()))

    def test_session_login_timeout_closes_browser(self):
        from third_party.course_engine import adapter
        from unittest.mock import Mock
        driver, out = Mock(), io.StringIO()
        with patch.object(adapter, "create_driver", return_value=driver), \
                patch.object(adapter, "login", side_effect=TimeoutError("等待登录超时")):
            self.assertEqual(worker.run_session({"mode": "session"}, io.StringIO(""), out), 1)
        driver.quit.assert_called_once()
        self.assertIn("超时", out.getvalue())

    def test_session_rejects_account_mode_without_password(self):
        out = io.StringIO()
        payload = {"mode": "session", "login_mode": "account", "account": {"uname": "student"}}
        self.assertEqual(worker.run_session(payload, io.StringIO(""), out), 1)
        self.assertIn("缺少账号或密码", out.getvalue())

    def test_error_description_never_includes_exception_text(self):
        self.assertNotIn("secret", worker.describe_error(RuntimeError("password=secret")))

    def test_auto_browser_falls_back_to_chrome(self):
        from third_party.course_engine import adapter
        from selenium.common import WebDriverException
        from unittest.mock import Mock
        driver = Mock()
        with patch.object(adapter, "_create", side_effect=[WebDriverException("x"), driver]) as create:
            self.assertIs(adapter.create_driver({"browser": "auto", "driver_path": ""}), driver)
        self.assertEqual([c.args[0] for c in create.call_args_list], ["edge", "chrome"])
        with patch.object(adapter, "_create", side_effect=WebDriverException("x")):
            with self.assertRaises(adapter.BrowserStartError):
                adapter.create_driver({"browser": "edge", "driver_path": ""})

    def test_one_failed_course_does_not_stop_session_queue(self):
        from third_party.course_engine import adapter
        from unittest.mock import Mock
        config = worker.validate_config({"account": {}, "login_mode": "qr", "courses": ["课程甲", "课程乙"]})
        with patch.object(adapter, "run_course", side_effect=[RuntimeError("未找到课程页面"), None]), \
                patch.object(adapter, "browser_alive", return_value=True):
            results = adapter.run_courses(Mock(), config, keep_going=True)
        self.assertEqual(results, [("课程甲", "失败：未找到课程页面"), ("课程乙", "已遍历")])


if __name__ == "__main__": unittest.main()
