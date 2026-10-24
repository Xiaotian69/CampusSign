"""课程页面离线检查，不启动浏览器。"""
import unittest
from unittest.mock import patch
import test_desktop_ui


class CourseUiTests(unittest.TestCase):
    setUp = test_desktop_ui.UiTests.setUp
    tearDown = test_desktop_ui.UiTests.tearDown
    make_app = test_desktop_ui.UiTests.make_app

    def test_course_page_start_dispatches_existing_account(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        page.courses.insert('1.0', '示例课程')
        with patch.object(page.runner, 'start') as start:
            page.start()
            start.assert_called_once()
            self.assertEqual(start.call_args.args[0]['username'], 'example-a')
            self.assertEqual(start.call_args.args[1]['courses'], ['示例课程'])

    def test_save_settings_excludes_key(self):
        self.app = self.make_app('generic')
        page = self.app.pages['courses']
        page.vars['api_key'].set('example-secret')
        page.courses.insert('1.0', '示例课程')
        page.save()
        settings = self.app.preferences['course_learning']
        self.assertNotIn('api_key', settings)
        self.assertEqual(settings['courses'], ['示例课程'])
        self.write.assert_called()

    def test_invalid_input_does_not_start(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        with patch.object(page.runner, 'start') as start, patch('course_ui.messagebox.showerror') as error:
            page.start()
            start.assert_not_called()
            error.assert_called_once()

    def test_log_remains_readable_at_minimum_window_size(self):
        self.app = self.make_app()
        self.app.geometry('920x640')
        self.app.show_page('courses')
        self.app.deiconify()
        self.app.update()
        self.assertGreaterEqual(self.app.pages['courses'].output.winfo_height(), 35)


if __name__ == '__main__':
    unittest.main()
