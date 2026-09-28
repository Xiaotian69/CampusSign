import unittest
from unittest.mock import patch, AsyncMock
from desktop_core import run_batch, Client, DEFAULT_LOCATIONS
from desktop_core import choose_course, choose_location, validate_location, classify_result, verified_page


class SelectionTests(unittest.TestCase):
    def test_south_campus_reversed_address_from_screenshot(self):
        address = '山西财经大学(坞城校区)-南院山西省太原市小店区坞城校区坞城路696号'
        result = choose_location(address, DEFAULT_LOCATIONS)
        self.assertEqual(result['longitude'], DEFAULT_LOCATIONS[1]['longitude'])
        self.assertEqual(result['latitude'], DEFAULT_LOCATIONS[1]['latitude'])

    def test_known_alias_can_reverse_address_and_place(self):
        address = '山西财经大学-修德楼 太原市-小店区-坞城路696号山西财经大学(南校区)'
        self.assertEqual(choose_location(address, DEFAULT_LOCATIONS)['name'], DEFAULT_LOCATIONS[2]['name'])

    def test_reversed_address_does_not_accept_different_building(self):
        for address in ['山西财经大学(坞城校区)-北院山西省太原市小店区坞城校区坞城路696号',
                        '山西财经大学(坞城校区)-南院北门山西省太原市小店区坞城校区坞城路696号']:
            with self.assertRaises(ValueError): choose_location(address, DEFAULT_LOCATIONS)

    def test_reordered_collision_is_still_ambiguous(self):
        places = [{'name': '地址 地点', 'longitude': 112, 'latitude': 37},
                  {'name': '地点地址', 'longitude': 113, 'latitude': 38}]
        with self.assertRaises(ValueError): choose_location('地点地址', places)

    def test_xiude_known_names_match_one_reference_point(self):
        for address in ['山西财经大学-北院修德楼', '山西财经大学-修德楼',
                        '太原市-小店区-坞城路696号山西财经大学(南校区) 山西财经大学-修德楼',
                        '山西省太原市小店区坞城路696号山西财经大学(南校区) 山西财经大学-修德楼']:
            location = choose_location(address, DEFAULT_LOCATIONS)
            self.assertAlmostEqual(location['longitude'], 112.59333524899067)
            self.assertAlmostEqual(location['latitude'], 37.799147323313136)

    def test_xiude_alias_does_not_match_other_building(self):
        with self.assertRaises(ValueError):
            choose_location('山西财经大学-修德楼北侧其他楼', DEFAULT_LOCATIONS)

    def test_south_campus_has_its_own_preset(self):
        address = '山西省太原市小店区坞城校区坞城路696号 山西财经大学(坞城校区)-南院'
        location = choose_location(address, DEFAULT_LOCATIONS)
        self.assertAlmostEqual(location['longitude'], 112.5928775533086)
        self.assertAlmostEqual(location['latitude'], 37.7926179807907)
        self.assertNotEqual(location['name'], DEFAULT_LOCATIONS[0]['name'])

    def test_course_exact(self):
        self.assertEqual(choose_course([{'class_name': 'test_01'}, {'class_name': 'test_0'}], 'test_0')['class_name'], 'test_0')

    def test_duplicate_course_rejected(self):
        with self.assertRaises(ValueError):
            choose_course([{'class_name': 'test_0'}]*2, 'test_0')

    def test_unknown_location_rejected(self):
        with self.assertRaises(ValueError):
            choose_location('另一栋楼', [{'name': '立信楼', 'longitude': 112.5, 'latitude': 37.7}])

    def test_location_ambiguity_rejected(self):
        with self.assertRaises(ValueError):
            choose_location('立信楼', [{'name': '立信楼'}, {'name': '立信楼'}])

    def test_similar_building_does_not_match(self):
        with self.assertRaises(ValueError):
            choose_location('立信楼北侧新教学楼', [{'name': '立信楼', 'longitude': 112.5, 'latitude': 37.7}])

    def test_status_requires_specific_element_and_activity(self):
        html = '<input id="activeId" value="123"><span class="greenColor">签到成功</span>'
        self.assertTrue(verified_page(html, '123'))
        self.assertFalse(verified_page(html, '456'))
        self.assertFalse(verified_page(html.replace('签到成功', '尚未签到成功'), '123'))
        self.assertFalse(verified_page('<p>签到成功后请退出</p>', '123'))

    def test_invalid_coordinate_rejected(self):
        for lng, lat in [(200, 30), (112, 100), (float('nan'), 30)]:
            with self.assertRaises(ValueError): validate_location('楼', lng, lat)

    def test_server_error_never_success(self):
        for response in ['validate', 'error', '不在可签到范围内', '请重新登录']:
            self.assertNotEqual(classify_result(response, True), '签到成功')

    def test_success_needs_verification(self):
        self.assertEqual(classify_result('success', True), '签到成功')
        self.assertNotEqual(classify_result('success', False), '签到成功')


class BatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_location_ignores_missing_address_for_all_accounts(self):
        calls = []
        class FakeClient:
            def __init__(self, session): self.submitted = False
            async def login(self, account): self.username = account['username']
            async def course(self, name): return {}
            async def activities(self, course): return [{'id': 1, 'otherId': '4'}]
            async def verification(self, course, aid): return self.submitted
            async def address(self, *args): raise AssertionError('固定模式不依赖地点文字')
            async def sign(self, aid, location, address):
                calls.append((self.username, dict(location)))
                self.submitted = True
                return 'success'
        rows = []
        with patch('desktop_core.Client', FakeClient):
            await run_batch([{'username': 'a'}, {'username': 'b'}], 'test_0', [], True,
                            rows.append, fixed_location=DEFAULT_LOCATIONS[0])
        self.assertEqual({c[0] for c in calls}, {'a', 'b'})
        self.assertTrue(all(c[1] == DEFAULT_LOCATIONS[0] for c in calls))
        self.assertTrue(all(r[-1] == '签到成功' for r in rows))
        self.assertTrue(all(r[3] == DEFAULT_LOCATIONS[0]['name'] for r in rows))

    async def test_fixed_location_query_does_not_submit_or_hide_other_types(self):
        class FakeClient:
            def __init__(self, session): pass
            async def login(self, account): pass
            async def course(self, name): return {}
            async def activities(self, course):
                return [{'id': 1, 'otherId': '4'}, {'id': 2, 'otherId': '0', 'nameOne': '普通签到'}]
            async def verification(self, course, aid): return False
            async def address(self, *args): raise AssertionError('不应读取地点文字')
            async def sign(self, *args): raise AssertionError('仅查询不应提交')
        rows = []
        with patch('desktop_core.Client', FakeClient):
            await run_batch([{'username': 'a'}], 'test_0', [], False, rows.append,
                            fixed_location=DEFAULT_LOCATIONS[0])
        self.assertIn('固定位置', rows[0][-1])
        self.assertIn('暂不支持', rows[1][-1])

    async def test_invalid_fixed_coordinates_rejected_before_login(self):
        rows = []
        with patch('desktop_core.Client') as client:
            await run_batch([{'username': 'a'}], 'test_0', [], True, rows.append,
                            fixed_location={'name': '楼', 'longitude': float('nan'), 'latitude': 37})
        client.assert_not_called()
        self.assertIn('经纬度必须有效', rows[0][-1])

    async def test_unknown_address_remains_in_result_and_is_not_submitted(self):
        calls = []
        class FakeClient:
            def __init__(self, session): pass
            async def login(self, account): pass
            async def course(self, name): return {}
            async def activities(self, course): return [{'id': 1, 'otherId': '4'}]
            async def verification(self, course, aid): return False
            async def address(self, course, aid): return '未收录的楼'
            async def sign(self, *args): calls.append(args)
        rows = []
        with patch('desktop_core.Client', FakeClient):
            await run_batch([{'username': 'example'}], 'test_0', [], True, rows.append)
        self.assertEqual(rows[0][3], '未收录的楼')
        self.assertEqual(calls, [])

    async def test_submission_preserves_verified_legacy_wire_parameters(self):
        client = Client(None)
        client.get = AsyncMock(return_value='success')
        location = DEFAULT_LOCATIONS[0]
        await client.sign('123', location, location['name'])
        params = client.get.call_args.args[1]
        self.assertEqual(params['clientip'], '0.0.0.0')
        self.assertEqual(params['address'], '中国')
        self.assertEqual(params['latitude'], str(location['latitude']))
        self.assertEqual(params['longitude'], str(location['longitude']))
        self.assertEqual(params['ifTiJiao'], '1')

    async def test_batch_preserves_legacy_mobile_headers(self):
        sessions = []
        class FakeClient:
            def __init__(self, session): sessions.append(dict(session.headers))
            async def login(self, account): raise ValueError('测试停止')
        with patch('desktop_core.Client', FakeClient):
            await run_batch([{'username': 'example'}], 'test_0', [], False, lambda row: None)
        self.assertIn('ChaoXingStudy_3_6.0.8', sessions[0]['User-Agent'])
        self.assertEqual(sessions[0]['Accept-Language'], 'zh_CN')

    async def test_account_failure_isolated_and_already_signed_skipped(self):
        calls = []
        class FakeClient:
            def __init__(self, session): pass
            async def login(self, account):
                self.username = account['username']
                if self.username == 'bad': raise ValueError('登录失败')
            async def course(self, name): return {}
            async def activities(self, course): return [{'id': 1, 'otherId': '4'}]
            async def verification(self, course, aid): return True
            async def sign(self, *args): calls.append(args)
        rows = []
        with patch('desktop_core.Client', FakeClient):
            await run_batch([{'username': 'bad'}, {'username': 'good'}], 'test_0', [], True, rows.append)
        self.assertEqual(len(rows), 2)
        statuses = {row[0]: row[-1] for row in rows}
        self.assertEqual(statuses['bad'], '登录失败')
        self.assertEqual(statuses['good'], '已签到，跳过')
        self.assertEqual(calls, [])

    async def test_dry_run_does_not_submit(self):
        calls = []
        class FakeClient:
            def __init__(self, session): pass
            async def login(self, account): pass
            async def course(self, name): return {}
            async def activities(self, course): return [{'id': 1, 'otherId': '4'}]
            async def verification(self, course, aid): return False
            async def address(self, course, aid): return '测试楼'
            async def sign(self, *args): calls.append(args)
        rows = []
        with patch('desktop_core.Client', FakeClient):
            await run_batch([{'username': 'good'}], 'test_0', [{'name': '测试楼', 'longitude': 112, 'latitude': 37}], False, rows.append)
        self.assertEqual(calls, [])
        self.assertIn('可签到', rows[0][-1])


if __name__ == '__main__': unittest.main()
