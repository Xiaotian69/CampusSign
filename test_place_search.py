"""百度地点检索离线测试：不接触真实网络，不需要真实 AK。"""
import json
import unittest
from unittest.mock import patch

from place_search import parse_place_results, search_places, parse_coordinate_text


class ParseTests(unittest.TestCase):
    def test_results_keep_bd09_coordinates_and_address(self):
        data = {'status': 0, 'message': 'ok', 'results': [
            {'name': '山西财经大学-立信楼', 'location': {'lat': 37.792118, 'lng': 112.5930636},
             'province': '山西省', 'city': '太原市', 'area': '小店区', 'address': '坞城路696号'},
            {'name': '无坐标', 'address': 'x'},
            {'name': '', 'location': {'lat': 37, 'lng': 112}},
        ]}
        self.assertEqual(parse_place_results(data), [
            {'name': '山西财经大学-立信楼', 'address': '山西省太原市小店区坞城路696号',
             'longitude': 112.5930636, 'latitude': 37.792118}])

    def test_address_already_containing_region_is_not_repeated(self):
        base = {'location': {'lat': 37.79, 'lng': 112.59}, 'province': '山西省', 'city': '太原市', 'area': '小店区'}
        data = {'status': 0, 'results': [
            dict(base, name='立信楼', address='山西省太原市小店区坞城南路696号'),
            dict(base, name='南院', address='太原市小店区坞城路696号')]}
        self.assertEqual([p['address'] for p in parse_place_results(data)],
                         ['山西省太原市小店区坞城南路696号', '山西省太原市小店区坞城路696号'])

    def test_error_status_raises_readable_message(self):
        with self.assertRaises(ValueError) as ctx:
            parse_place_results({'status': 5, 'message': 'APP不存在，AK有误请检查再重试'})
        self.assertIn('AK', str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            parse_place_results({'status': 999, 'message': '奇怪的错误'})
        self.assertIn('奇怪的错误', str(ctx.exception))

    def test_empty_results(self):
        self.assertEqual(parse_place_results({'status': 0, 'results': []}), [])


class CoordinateTests(unittest.TestCase):
    def test_baidu_map_url_center_converts_to_bd09(self):
        url = 'https://map.baidu.com/search/%E5%A4%A9%E5%AE%89%E9%97%A8//@12958175,4825923,19z?querytype=s'
        lng, lat, note = parse_coordinate_text(url)
        self.assertAlmostEqual(lng, 116.404, places=3)
        self.assertAlmostEqual(lat, 39.915, places=3)
        self.assertIn('网址', note)

    def test_bare_mercator_pair_is_recognised(self):
        lng, lat, _ = parse_coordinate_text('12529930.9,4535569.28')
        self.assertAlmostEqual(lng, 112.557, places=2)
        self.assertAlmostEqual(lat, 37.877, places=2)

    def test_bd09_pair_kept_and_lat_first_swapped(self):
        self.assertEqual(parse_coordinate_text('112.5930636, 37.792118')[:2], (112.5930636, 37.792118))
        self.assertEqual(parse_coordinate_text('37.792118，112.5930636')[:2], (112.5930636, 37.792118))

    def test_gcj02_and_wgs84_convert_towards_bd09(self):
        lng, lat, _ = parse_coordinate_text('116.397428,39.90923', 'gcj02')
        self.assertAlmostEqual(lng, 116.4038, places=3)
        self.assertAlmostEqual(lat, 39.9156, places=3)
        lng, lat, _ = parse_coordinate_text('116.391248,39.907501', 'wgs84')
        self.assertAlmostEqual(lng, 116.4039, places=3)
        self.assertAlmostEqual(lat, 39.9152, places=3)

    def test_unrecognised_text_rejected(self):
        for text in ['', '立信楼', '1,2,3', 'https://map.baidu.com/']:
            with self.assertRaises(ValueError): parse_coordinate_text(text)


class FakeResponse:
    def __init__(self, body): self.body = body
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    def raise_for_status(self): pass
    async def text(self): return self.body


class FakeSession:
    requests = []
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    def get(self, url, params=None):
        FakeSession.requests.append((url, params))
        return FakeResponse(json.dumps({'status': 0, 'results': [
            {'name': '立信楼', 'location': {'lat': 37.79, 'lng': 112.59}}]}))


class SearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeSession.requests = []

    async def test_missing_ak_or_keyword_never_requests(self):
        with patch('place_search.aiohttp.ClientSession', FakeSession):
            with self.assertRaises(ValueError): await search_places('立信楼', '太原', '  ')
            with self.assertRaises(ValueError): await search_places('  ', '太原', 'key')
        self.assertEqual(FakeSession.requests, [])

    async def test_city_limits_search_and_blank_city_means_nationwide(self):
        with patch('place_search.aiohttp.ClientSession', FakeSession):
            places = await search_places(' 立信楼 ', '太原', 'key')
            await search_places('立信楼', '', 'key')
        self.assertEqual(places[0]['longitude'], 112.59)
        (_, city), (_, nationwide) = FakeSession.requests
        self.assertEqual((city['query'], city['region'], city['city_limit'], city['ak']), ('立信楼', '太原', 'true', 'key'))
        self.assertEqual((nationwide['region'], nationwide['city_limit']), ('全国', 'false'))


if __name__ == '__main__':
    unittest.main()
