"""课程页面离线检查，不启动浏览器。"""
import unittest
from unittest.mock import patch
import test_desktop_ui
from test_desktop_ui import collect_texts


class CourseUiTests(unittest.TestCase):
    setUp = test_desktop_ui.UiTests.setUp
    tearDown = test_desktop_ui.UiTests.tearDown
    make_app = test_desktop_ui.UiTests.make_app

    def test_qr_login_works_without_saved_account(self):
        self.accounts = []
        self.app = self.make_app()
        page = self.app.pages['courses']
        with patch.object(page.runner, 'login') as login:
            page.login()
        login.assert_called_once()
        self.assertEqual(login.call_args.args[0], {})
        self.assertEqual(login.call_args.args[1]['login_mode'], 'qr')

    def test_login_waits_for_disclaimer_then_continues(self):
        self.app = self.make_app(config_extra={'dev_mode': False})
        page = self.app.pages['courses']
        self.app._show_disclaimer.return_value = False
        with patch.object(page.runner, 'login') as login:
            page.login()
            login.assert_not_called()
            self.assertIn('未同意', page.status.get())
            # 同意后同一次点击继续登录，不需要再找按钮。
            self.app._show_disclaimer.return_value = True
            page.login()
            login.assert_called_once()

    def test_login_does_not_start_course_task(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        with patch.object(page.runner, 'login'), patch.object(page.runner, 'run_courses') as run, \
                patch.object(page.runner, 'start') as start:
            page.login()
        run.assert_not_called()
        start.assert_not_called()

    def test_start_requires_login(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        page.courses.insert('1.0', '示例课程')
        with patch('course_ui.messagebox.showerror') as error:
            page.start()
        error.assert_called_once()
        self.assertIn('登录', error.call_args.args[1])

    def test_start_runs_selected_and_manual_courses(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        page.set_courses(['课程甲', '课程乙'])
        page.course_list.selection_set(1)
        page.courses.insert('1.0', '手动课程')
        with patch.object(page.runner, 'run_courses') as run:
            page.start()
        self.assertEqual(run.call_args.args[0]['courses'], ['课程乙', '手动课程'])

    def test_parallel_uses_independent_workers(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        page.vars['parallel'].set('2')
        page.courses.insert('1.0', '课程甲\n课程乙')
        with patch.object(page.runner, 'start') as start, patch.object(page.runner, 'run_courses') as run:
            page.start()
        start.assert_called_once()
        run.assert_not_called()

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
        page.vars['speed'].set('abc')
        with patch.object(page.runner, 'run_courses', wraps=page.runner.run_courses), \
                patch('course_ui.messagebox.showerror') as error:
            page.courses.insert('1.0', '示例课程')
            page.start()
        error.assert_called_once()
        self.assertFalse(page.runner.running)

    def test_default_page_hides_internal_values_and_advanced_options(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        texts = ' '.join(collect_texts(page))
        self.assertIn('扫码登录', texts)
        self.assertIn('不答题', texts)
        for internal in (' qr', 'edge', 'account', 'API Key'):
            self.assertNotIn(internal, texts)
        page.open_advanced()
        advanced = ' '.join(collect_texts(page._advanced))
        self.assertIn('自动提交（正式交卷）', ' '.join(str(b.cget('values')) for b in self._comboboxes(page._advanced)))
        self.assertIn('DeepSeek API Key', advanced)
        page._advanced.destroy()

    def test_advanced_choice_stores_config_value(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        page.open_advanced()
        box = self._comboboxes(page._advanced)[0]  # 登录方式
        box.set('账号密码登录')
        box.event_generate('<<ComboboxSelected>>')
        self.assertEqual(page.vars['login_mode'].get(), 'account')
        page._advanced.destroy()

    def test_unknown_saved_value_falls_back_to_default(self):
        self.settings['course_learning'] = {'browser': 'firefox', 'choice': '随机答题'}
        self.app = self.make_app()
        page = self.app.pages['courses']
        self.assertEqual(page.vars['browser'].get(), 'auto')
        self.assertEqual(page.vars['choice'].get(), '随机答题')
        self.assertIn('随机答题', page.summary.cget('text'))

    def test_error_event_expands_details(self):
        self.app = self.make_app()
        page = self.app.pages['courses']
        page.runner.emit('error', '无法启动浏览器')
        page.poll()
        self.assertTrue(page.details.winfo_manager())
        self.assertEqual(page.status.get(), '无法启动浏览器')

    def test_log_remains_readable_at_minimum_window_size(self):
        self.app = self.make_app()
        self.app.geometry('920x640')
        self.app.show_page('courses')
        page = self.app.pages['courses']
        page.set_courses([f'课程{i}' for i in range(20)])
        page.toggle_details(True)
        self.app.deiconify()
        self.app.update()
        self.assertGreaterEqual(page.output.winfo_height(), 35)
        self.assertGreaterEqual(page.course_list.winfo_height(), 35)
        bottom = page.output.winfo_rooty() + page.output.winfo_height()
        self.assertLessEqual(bottom, self.app.winfo_rooty() + self.app.winfo_height())

    @staticmethod
    def _comboboxes(widget):
        from tkinter import ttk
        found = []
        for child in widget.winfo_children():
            if isinstance(child, ttk.Combobox):
                found.append(child)
            found.extend(CourseUiTests._comboboxes(child))
        return found


if __name__ == '__main__':
    unittest.main()
