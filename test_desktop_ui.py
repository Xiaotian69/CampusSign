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
        self.assertFalse(any('山西财经大学' in t for t in collect_texts(self.app.pages['home'])))

    def test_contact_visible_only_in_help_and_about(self):
        self.app = self.make_app('scufe')
        email = desktop_ui.app_config.CONTACT_EMAIL
        self.assertNotIn(email, collect_texts(self.app.pages['home']))
        for page in ('help', 'about'):
            self.assertIn(email, collect_texts(self.app.pages[page]))

    def test_custom_location_merged_after_presets(self):
        self.app = self.make_app('scufe')
        custom = {'name': '自定义楼', 'longitude': 113.0, 'latitude': 38.0}
        merged = merge_locations(SCUFE_PROFILE['preset_locations'], [custom])
        self.assertEqual(merged[-1]['name'], '自定义楼')
        self.assertEqual(merged[-1]['longitude'], 113.0)

    # ===== 首次须知 =====
    def test_real_first_start_maps_main_and_disclaimer(self):
        self.app = App(config={'edition': 'generic', 'dev_mode': False}, profile=GENERIC_PROFILE)
        visible = []
        def probe():
            notices = [w for w in self.app.winfo_children() if isinstance(w, tk.Toplevel)]
            visible.append(bool(self.app.winfo_viewable() and notices and notices[0].winfo_viewable()))
            for window in notices:
                window.destroy()
            self.app.after(1, self.app.quit)
        self.app.after(500, probe)
        self.app.mainloop()
        self.assertEqual(visible, [True])

    def test_disclaimer_needed_when_not_accepted(self):
        self.app = self.make_app('scufe', config_extra={'dev_mode': False})
        self.assertTrue(self.app.disclaimer_needed())

    def test_disclaimer_skipped_in_dev_mode(self):
        self.app = self.make_app('scufe', config_extra={'dev_mode': True})
        self.assertFalse(self.app.disclaimer_needed())

    def test_disclaimer_skipped_when_accepted(self):
        self.settings['disclaimer_accepted'] = True
        self.settings['disclaimer_version'] = desktop_ui.disclaimer.DISCLAIMER_VERSION
        self.app = self.make_app('scufe', config_extra={'dev_mode': False})
        self.assertFalse(self.app.disclaimer_needed())

    def test_disclaimer_shown_once_more_after_content_update(self):
        self.settings['disclaimer_accepted'] = True  # 旧版本只保存了布尔值
        self.app = self.make_app('scufe', config_extra={'dev_mode': False})
        self.assertTrue(self.app.disclaimer_needed())

    def _real_disclaimer(self, action, area=(0, 0, 800, 480), continue_text='同意并继续'):
        """在很矮的屏幕上打开真实须知窗口，执行 action(win) 后返回 (结果, 观测)。"""
        self.app = self.make_app('scufe', config_extra={'dev_mode': False})
        self._disclaimer_patch.stop()
        for timer in self.app.tk.call('after', 'info'):  # 取消启动时自动弹出的须知
            self.app.after_cancel(timer)
        self.app.deiconify()
        seen = {}

        def probe():
            win = [w for w in self.app.winfo_children() if isinstance(w, tk.Toplevel)][0]
            win.update()
            buttons = [w for w in win.winfo_children()[0].winfo_children()]
            seen['buttons'] = [b.cget('text') for b in buttons]
            seen['visible'] = all(b.winfo_viewable() and
                                  b.winfo_y() + b.winfo_height() + b.master.winfo_y() <= win.winfo_height()
                                  for b in buttons)
            seen['fits'] = win.winfo_height() <= area[3] and win.winfo_width() <= area[2]
            action(win, buttons)
        self.app.after(200, probe)
        with patch('window_utils.work_area', return_value=area):
            result = self.app._show_disclaimer(True, continue_text)
        return result, seen

    def test_disclaimer_buttons_visible_on_small_screen_and_accept_continues(self):
        result, seen = self._real_disclaimer(lambda win, buttons: buttons[-1].invoke())
        self.assertTrue(seen['visible'])
        self.assertTrue(seen['fits'])
        self.assertEqual(seen['buttons'], ['取消', '同意并继续'])
        self.assertTrue(result)
        self.assertFalse(self.app.disclaimer_needed())
        saved = self.write.call_args.args[1]
        self.assertEqual(saved['disclaimer_version'], desktop_ui.disclaimer.DISCLAIMER_VERSION)

    def test_disclaimer_close_button_counts_as_cancel(self):
        result, _ = self._real_disclaimer(lambda win, buttons: win.tk.call(win.protocol('WM_DELETE_WINDOW')))
        self.assertFalse(result)
        self.assertTrue(self.app.disclaimer_needed())
        self.write.assert_not_called()

    def test_disclaimer_cancel_keeps_app_open(self):
        result, _ = self._real_disclaimer(lambda win, buttons: buttons[0].invoke())
        self.assertFalse(result)
        self.assertTrue(self.app.winfo_exists())

    def test_disclaimer_save_failure_is_reported_but_session_continues(self):
        self.write.side_effect = OSError('read-only')
        with patch('desktop_ui.messagebox.showwarning') as warning:
            result, _ = self._real_disclaimer(lambda win, buttons: buttons[-1].invoke())
        self.assertTrue(result)
        warning.assert_called_once()
        self.assertFalse(self.app.disclaimer_needed())

    def test_startup_disclaimer_offers_quit(self):
        _, seen = self._real_disclaimer(lambda win, buttons: buttons[-1].invoke(), continue_text=None)
        self.assertEqual(seen['buttons'], ['退出程序', '我已阅读并同意'])

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

    # ===== 课程列表 =====
    def test_refresh_courses_fills_picker_and_caches(self):
        self.app = self.make_app('scufe')
        owners = {'概率论': ['example-b'], '高等数学': ['example-a', 'example-b']}
        with patch('desktop_ui.threading.Thread') as thread, \
                patch('desktop_ui.list_courses', new_callable=AsyncMock, return_value=(owners, {})) as fetch:
            self.app.refresh_courses()
            self.assertTrue(self.app.busy)
            thread.call_args.kwargs['target']()
            self.app.poll()
        self.assertEqual([a['username'] for a in fetch.await_args.args[0]], ['example-a', 'example-b'])
        self.assertFalse(self.app.busy)
        self.assertEqual(list(self.app.course_picker.cget('values')), ['概率论', '高等数学'])
        self.assertEqual(self.write.call_args.args[1]['course_list'], owners)
        self.app.course.set('高等数学')
        self.app.update_course_hint()
        self.assertIn('example-a、example-b', self.app.course_hint.get())

    def test_failed_refresh_keeps_cached_courses(self):
        self.settings['course_list'] = {'高等数学': ['example-a']}
        self.app = self.make_app('scufe')
        with patch('desktop_ui.threading.Thread') as thread, \
                patch('desktop_ui.list_courses', new_callable=AsyncMock, return_value=({}, {'example-a': '登录失败'})):
            self.app.refresh_courses()
            thread.call_args.kwargs['target']()
            self.app.poll()
        self.assertEqual(list(self.app.course_picker.cget('values')), ['高等数学'])
        self.assertIn('登录失败', self.app.course_hint.get())

    def test_refresh_courses_needs_account(self):
        self.app = self.make_app('scufe')
        self.app.account_list.selection_clear(0, 'end')
        with patch('desktop_ui.threading.Thread') as thread, patch('desktop_ui.messagebox.showinfo') as info:
            self.app.refresh_courses()
        thread.assert_not_called()
        info.assert_called_once()

    def test_course_filter_keeps_typed_text(self):
        self.settings['course_list'] = {'高等数学': ['example-a'], '线性代数': ['example-a'], '数学建模': ['example-b']}
        self.app = self.make_app('scufe')
        self.app.course.set('数学')
        self.app.filter_courses()
        self.assertEqual(list(self.app.course_picker.cget('values')), ['高等数学', '数学建模'])
        self.assertEqual(self.app.course.get(), '数学')

    # ===== 地点搜索 =====
    def test_search_dialog_adds_renamed_result(self):
        self.app = self.make_app('generic')
        dialog = self.app.search_location()
        dialog.ak.set('example-ak')
        dialog.region.set('太原')
        dialog.keyword.set('立信楼')
        places = [{'name': '立信楼', 'address': '坞城路696号', 'longitude': 112.5930636, 'latitude': 37.792118}]
        with patch('desktop_ui.threading.Thread') as thread, \
                patch('desktop_ui.search_places', new_callable=AsyncMock, return_value=places) as search:
            dialog.search()
            thread.call_args.kwargs['target']()
            self.app.poll()
        self.assertEqual(search.await_args.args, ('立信楼', '太原', 'example-ak'))
        self.assertEqual(self.app.preferences['baidu_ak'], 'example-ak')
        self.assertEqual(len(dialog.tree.get_children()), 1)
        dialog.tree.selection_set('0')
        dialog.window.update()
        self.assertEqual(dialog.name.get(), '立信楼')
        dialog.name.set('山西财经大学-立信楼')
        dialog.add()
        self.assertEqual(self.write.call_args.args,
                         ('locations.local.json', [{'name': '山西财经大学-立信楼', 'longitude': 112.5930636, 'latitude': 37.792118}]))
        self.assertEqual(self.app.locations[-1]['name'], '山西财经大学-立信楼')

    def test_map_pick_url_prefills_name_and_adds(self):
        self.app = self.make_app('generic')
        dialog = self.app.search_location()
        dialog.coord_text.set('https://map.baidu.com/search/%E7%AB%8B%E4%BF%A1%E6%A5%BC//@12958175,4825923,19z')
        dialog.add_picked()
        name, lng, lat = [self.write.call_args.args[1][0][k] for k in ('name', 'longitude', 'latitude')]
        self.assertEqual(self.write.call_args.args[0], 'locations.local.json')
        self.assertEqual(name, '立信楼')
        self.assertAlmostEqual(lng, 116.404, places=3)
        self.assertAlmostEqual(lat, 39.915, places=3)

    def test_map_pick_rejects_bad_text_without_saving(self):
        self.app = self.make_app('generic')
        dialog = self.app.search_location()
        dialog.coord_text.set('不是坐标')
        dialog.pick_name.set('楼')
        self.write.reset_mock()
        dialog.add_picked()
        self.write.assert_not_called()
        self.assertIn('没有识别到坐标', dialog.pick_hint.get())

    def test_search_error_shown_in_dialog(self):
        self.app = self.make_app('generic')
        dialog = self.app.search_location()
        with patch('desktop_ui.threading.Thread') as thread, \
                patch('desktop_ui.search_places', new_callable=AsyncMock, side_effect=ValueError('请先填写百度地图 AK')):
            dialog.search()
            thread.call_args.kwargs['target']()
            self.app.poll()
        self.assertEqual(dialog.hint.get(), '请先填写百度地图 AK')
        self.assertEqual(str(dialog.button.cget('state')), 'normal')

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
