"""CxSign 界面离线集成测试：不读取真实账号，不接触学习通网络。"""
import unittest
from unittest.mock import patch, AsyncMock
import tkinter as tk

import desktop_ui
from desktop_ui import App, merge_locations
from desktop_core import DEFAULT_LOCATIONS


SCUFE_PROFILE = {
    'key': 'scufe',
    'display_name': 'SCUFE Edition',
    'display_name_zh': '山西财经大学版',
    'preset_locations': [dict(p) for p in DEFAULT_LOCATIONS],
}
GENERIC_PROFILE = {
    'key': 'generic',
    'display_name': 'Generic Edition',
    'display_name_zh': '通用版',
    'preset_locations': [],
}


def collect_texts(widget):
    texts = []
    for child in widget.winfo_children():
        try:
            t = child.cget('text')
            if t:
                texts.append(str(t))
        except tk.TclError:
            pass
        texts.extend(collect_texts(child))
    return texts


class UiTests(unittest.TestCase):
    def setUp(self):
        self.settings = {'course': 'test_0', 'unrelated_setting': 'keep'}
        self.accounts = [{'username': 'example-a'}, {'username': 'example-b'}]
        self.reader = patch('desktop_ui.read_json', side_effect=lambda name, default: {
            'user.json': self.accounts,
            'ui.local.json': dict(self.settings),
            'locations.local.json': [],
        }.get(name, default))
        self.reader.start()
        self.writer = patch('desktop_ui.write_json')
        self.write = self.writer.start()

    def make_app(self, edition='scufe', config_extra=None):
        config = {'edition': edition, 'dev_mode': True}
        if config_extra:
            config.update(config_extra)
        profile = SCUFE_PROFILE if edition == 'scufe' else GENERIC_PROFILE
        self._disclaimer_patch = patch.object(App, '_show_disclaimer')
        self._disclaimer_patch.start()
        self.addCleanup(self._disclaimer_patch.stop)
        app = App(config=config, profile=dict(profile))
        app.withdraw()
        app.update_idletasks()
        return app

    def tearDown(self):
        if hasattr(self, 'app') and self.app.winfo_exists():
            self.app.update_idletasks()
            for timer in self.app.tk.call('after', 'info'):
                self.app.after_cancel(timer)
            self.app.destroy()
        self.writer.stop()
        self.reader.stop()

    # ===== Edition =====
    def test_scufe_loads_presets_and_default_fixed_location(self):
        self.app = self.make_app('scufe')
        self.assertEqual(len(self.app.locations), len(DEFAULT_LOCATIONS))
        self.assertEqual(self.app.selected_fixed_location(), DEFAULT_LOCATIONS[0])
        self.assertEqual(self.app.fixed_name.get(), DEFAULT_LOCATIONS[0]['name'])

    def test_generic_has_no_presets(self):
        self.app = self.make_app('generic')
        self.assertEqual(self.app.locations, [])
        self.assertEqual(self.app.fixed_name.get(), '')

    def test_custom_location_merged_after_presets(self):
        self.app = self.make_app('scufe')
        custom = {'name': '自定义楼', 'longitude': 113.0, 'latitude': 38.0}
        merged = merge_locations(SCUFE_PROFILE['preset_locations'], [custom])
        self.assertEqual(merged[-1]['name'], '自定义楼')
        self.assertEqual(merged[-1]['longitude'], 113.0)

    # ===== 首次须知 =====
    def test_disclaimer_needed_when_not_accepted(self):
        self.app = self.make_app('scufe', config_extra={'dev_mode': False})
        self.assertTrue(self.app.disclaimer_needed())

    def test_disclaimer_skipped_in_dev_mode(self):
        self.app = self.make_app('scufe', config_extra={'dev_mode': True})
        self.assertFalse(self.app.disclaimer_needed())

    def test_disclaimer_skipped_when_accepted(self):
        self.settings['disclaimer_accepted'] = True
        self.app = self.make_app('scufe', config_extra={'dev_mode': False})
        self.assertFalse(self.app.disclaimer_needed())

    def test_ensure_disclaimer_shows_when_needed(self):
        self.app = self.make_app('scufe', config_extra={'dev_mode': False})
        self.app._ensure_disclaimer()
        self.assertTrue(self.app._show_disclaimer.called)

    def test_ensure_disclaimer_skips_in_dev_mode(self):
        self.app = self.make_app('scufe')
        self.app._ensure_disclaimer()
        self.assertFalse(self.app._show_disclaimer.called)

    # ===== 签到调度 =====
    def test_fixed_dispatch_snapshot(self):
        self.app = self.make_app('scufe')
        with patch('desktop_ui.threading.Thread') as thread, patch('desktop_ui.run_batch', new_callable=AsyncMock) as run:
            self.app.start(True)
            target = thread.call_args.kwargs['target']
            target()
            self.app.poll()
        self.assertTrue(run.await_args.args[3])
        self.assertEqual(run.await_args.kwargs['fixed_location'], DEFAULT_LOCATIONS[0])
        self.assertEqual(self.write.call_args.args[1]['location_mode'], 'fixed')
        self.assertEqual(self.write.call_args.args[1]['course'], 'test_0')

    def test_auto_query_dispatch(self):
        self.app = self.make_app('scufe')
        self.app.mode.set('auto')
        with patch('desktop_ui.threading.Thread') as thread, patch('desktop_ui.run_batch', new_callable=AsyncMock) as run:
            self.app.start(False)
            thread.call_args.kwargs['target']()
            self.app.poll()
        self.assertIsNone(run.await_args.kwargs['fixed_location'])
        self.assertFalse(run.await_args.args[3])

    def test_missing_account_blocks_start(self):
        self.app = self.make_app('scufe')
        self.app.accounts = []
        self.app.refresh_accounts()
        self.app.account_list.selection_clear(0, 'end')
        with patch('desktop_ui.threading.Thread') as thread, patch('desktop_ui.messagebox.showinfo') as info:
            self.app.start(True)
        thread.assert_not_called()
        info.assert_called_once()

    def test_deleted_fixed_location_blocks_start(self):
        self.app = self.make_app('scufe')
        self.app.locations = [dict(DEFAULT_LOCATIONS[1])]
        self.app.refresh_places()
        with patch('desktop_ui.threading.Thread') as thread, patch('desktop_ui.messagebox.showerror') as error:
            self.app.start(True)
        thread.assert_not_called()
        error.assert_called_once()

    # ===== 地点管理 =====
    def test_add_location_writes_custom_only(self):
        self.app = self.make_app('scufe')
        with patch.object(self.app, '_form', side_effect=lambda title, fields, save: save(['自定义楼', '113', '38'])):
            self.app.add_location()
        self.assertEqual(self.write.call_args.args[1], [{'name': '自定义楼', 'longitude': 113.0, 'latitude': 38.0}])

    def test_remove_custom_location(self):
        self.reader.stop()
        self.reader = patch('desktop_ui.read_json', side_effect=lambda name, default: {
            'user.json': self.accounts,
            'ui.local.json': dict(self.settings),
            'locations.local.json': [{'name': '自定义楼', 'longitude': 113.0, 'latitude': 38.0}],
        }.get(name, default))
        self.reader.start()
        self.app = self.make_app('scufe')
        self.app.place_list.selection_set(len(self.app.locations) - 1)
        self.app.remove_location()
        written = self.write.call_args.args[1]
        self.assertEqual(written, [])
        self.assertNotIn('自定义楼', [p['name'] for p in self.app.locations])

    def test_remove_preset_leaves_custom_file_empty(self):
        self.app = self.make_app('scufe')
        self.app.place_list.selection_set(0)
        self.app.remove_location()
        self.assertEqual(self.write.call_args.args[1], [])

    # ===== 资源页 =====
    def test_resources_scufe_shows_exam_card(self):
        self.app = self.make_app('scufe')
        self.app.show_page('resources')
        texts = collect_texts(self.app.pages['resources'])
        self.assertIn('山西财经大学历年期末资料', texts)

    def test_resources_generic_shows_community(self):
        self.app = self.make_app('generic')
        self.app.show_page('resources')
        texts = collect_texts(self.app.pages['resources'])
        self.assertIn('社区资源', texts)
        self.assertNotIn('山西财经大学历年期末资料', texts)
        self.assertFalse(any('山西财经大学' in text for text in texts))

    # ===== 窗口适配 =====
    def test_screenshot_app_does_not_read_local_preferences(self):
        from make_screenshots import make_app
        self.settings['last_result'] = 'PRIVATE_RESULT_SENTINEL'
        self.app = make_app('generic')
        self.assertEqual(self.app.preferences, {})
        self.assertEqual(self.app.last_result, '')
        self.assertEqual(self.app.locations, [])

    def test_controls_fit_minimum_window_size(self):
        self.app = self.make_app('scufe')
        self.app.show_page('sign')
        self.app.geometry('920x640')
        self.app.deiconify()
        self.app.update()
        for widget in (self.app.fixed_picker, self.app.results, self.app.submit):
            right = widget.winfo_rootx() - self.app.winfo_rootx() + widget.winfo_width()
            bottom = widget.winfo_rooty() - self.app.winfo_rooty() + widget.winfo_height()
            self.assertLessEqual(right, self.app.winfo_width())
            self.assertLessEqual(bottom, self.app.winfo_height())
            self.assertGreater(widget.winfo_height(), 15)
        self.app.withdraw()


if __name__ == '__main__':
    unittest.main()
