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

if __name__ == "__main__": unittest.main()
