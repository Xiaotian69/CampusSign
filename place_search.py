"""地点坐标获取：百度地图关键词检索，以及粘贴网址/坐标识别。

关键词检索只在用户主动点击「搜索」时联网，且只向百度地图开放平台发送
关键词、城市与用户自己填写的 AK；AK 需自行申请（服务端类型），仅保存在本机。
网址/坐标识别完全离线：把百度地图网页版地址栏中的地图中心点（墨卡托坐标），
或 GCJ-02 / WGS-84 经纬度换算为地点库使用的百度 BD-09 经纬度。
二者都不接触学习通账号，也不参与签到流程。
"""
import json
import math
import re

import aiohttp

# 地点检索 v2.0（行政区划区域检索），默认返回 bd09ll 坐标，与地点库一致。
PLACE_SEARCH_URL = 'https://api.map.baidu.com/place/v2/search'
PAGE_SIZE = 20

# 常见错误状态码 → 面向用户的提示。
STATUS_HINTS = {
    2: '请求参数非法，请检查关键词与城市',
    3: '权限校验失败，请检查 AK 是否为服务端类型',
    4: '配额校验失败，今日调用量可能已用完',
    5: 'AK 不存在或非法，请检查填写的 AK',
    101: 'AK 对应的服务已被禁用',
    102: '不通过白名单或安全码，请把 AK 的 IP 白名单设为 0.0.0.0/0',
    401: '请求过于频繁，请稍后再试',
}


def parse_place_results(data):
    """把检索接口返回的 JSON 归纳为地点候选列表，缺少有效坐标的条目跳过。"""
    status = data.get('status')
    if status != 0:
        hint = STATUS_HINTS.get(status) or str(data.get('message') or '未知错误')
        raise ValueError(f'地点检索失败（{status}）：{hint}')
    places = []
    for item in data.get('results') or []:
        location = item.get('location') or {}
        try:
            lng, lat = float(location['lng']), float(location['lat'])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(item.get('name') or '').strip()
        if not name or not (math.isfinite(lng) and math.isfinite(lat)):
            continue
        # 部分结果的 address 已含省市区，只补地址中缺少的部分，避免重复。
        address = str(item.get('address') or '')
        region = ''.join(part for part in (str(item.get(k) or '') for k in ('province', 'city', 'area'))
                         if part and part not in address)
        places.append({'name': name,
                       'address': region + address,
                       'longitude': lng, 'latitude': lat})
    return places


async def search_places(keyword, region, ak):
    """按关键词在指定城市（留空为全国）检索地点。"""
    keyword, region, ak = keyword.strip(), region.strip(), ak.strip()
    if not ak:
        raise ValueError('请先填写百度地图 AK')
    if not keyword:
        raise ValueError('请输入要搜索的地点关键词')
    params = {'query': keyword, 'region': region or '全国', 'city_limit': 'true' if region else 'false',
              'scope': 1, 'page_size': PAGE_SIZE, 'output': 'json', 'ak': ak}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(PLACE_SEARCH_URL, params=params) as response:
            response.raise_for_status()
            return parse_place_results(json.loads(await response.text()))


# ================= 坐标换算（离线） =================

# 百度墨卡托（BD-09MC）→ 百度经纬度（BD-09）分段拟合系数。
_MC_BANDS = (12890594.86, 8362377.87, 5591021, 3481989.83, 1678043.12, 0)
_MC_TO_LL = (
    (1.410526172116255e-8, 0.00000898305509648872, -1.9939833816331, 200.9824383106796, -187.2403703815547,
     91.6087516669843, -23.38765649603339, 2.57121317296198, -0.03801003308653, 17337981.2),
    (-7.435856389565537e-9, 0.000008983055097726239, -0.78625201886289, 96.32687599759846, -1.85204757529826,
     -59.36935905485877, 47.40033549296737, -16.50741931063887, 2.28786674699375, 10260144.86),
    (-3.030883460898826e-8, 0.00000898305509983578, 0.30071316287616, 59.74293618442277, 7.357984074871,
     -25.38371002664745, 13.45380521110908, -3.29883767235584, 0.32710905363475, 6856817.37),
    (-1.981981304930552e-8, 0.000008983055099779535, 0.03278182852591, 40.31678527705744, 0.65659298677277,
     -4.44255534477492, 0.85341911805263, 0.12923347998204, -0.04625736007561, 4482777.06),
    (3.09191371068437e-9, 0.000008983055096812155, 0.00006995724062, 23.10934304144901, -0.00023663490511,
     -0.6321817810242, -0.00663494467273, 0.03430082397953, -0.00466043876332, 2555164.4),
    (2.890871144776878e-9, 0.000008983055095805407, -3.068298e-8, 7.47137025468032, -0.00000353937994,
     -0.02145144861037, -0.00001234426596, 0.00010322952773, -0.00000323890364, 826088.5),
)
_X_PI = math.pi * 3000.0 / 180.0
_GCJ_A = 6378245.0
_GCJ_EE = 0.00669342162296594323

COORD_SYSTEMS = {'bd09': '百度 BD-09', 'gcj02': '高德 / 腾讯 GCJ-02', 'wgs84': '手机 GPS WGS-84'}


def bd09mc_to_bd09(x, y):
    """百度墨卡托坐标 → 百度经纬度。"""
    c = next(band for limit, band in zip(_MC_BANDS, _MC_TO_LL) if abs(y) >= limit)
    lng = c[0] + c[1] * abs(x)
    t = abs(y) / c[9]
    lat = c[2] + c[3] * t + c[4] * t ** 2 + c[5] * t ** 3 + c[6] * t ** 4 + c[7] * t ** 5 + c[8] * t ** 6
    return math.copysign(lng, x), math.copysign(lat, y)


def gcj02_to_bd09(lng, lat):
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * _X_PI)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * _X_PI)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def wgs84_to_gcj02(lng, lat):
    x, y = lng - 105.0, lat - 35.0
    dlat = (-100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
            + (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
            + (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
            + (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0)
    dlng = (300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
            + (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
            + (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
            + (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0)
    rad = lat / 180.0 * math.pi
    magic = 1 - _GCJ_EE * math.sin(rad) ** 2
    dlat = (dlat * 180.0) / ((_GCJ_A * (1 - _GCJ_EE)) / (magic * math.sqrt(magic)) * math.pi)
    dlng = (dlng * 180.0) / (_GCJ_A / math.sqrt(magic) * math.cos(rad) * math.pi)
    return lng + dlng, lat + dlat


def parse_coordinate_text(text, system='bd09'):
    """识别粘贴的百度地图网址或「经度,纬度」，返回 ``(经度, 纬度, 说明)``（BD-09）。

    - 百度地图网页版网址：取地址栏 ``/@x,y,缩放z`` 中的地图中心点（百度墨卡托）；
    - 两个大于 180 的数：同样按百度墨卡托处理；
    - 普通经纬度：按 ``system`` 指定的坐标系换算；纬度在前时自动交换。
    """
    text = (text or '').strip()
    found = re.search(r'@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)', text)
    numbers = [float(found.group(1)), float(found.group(2))] if found else \
        [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', text)]
    if len(numbers) != 2:
        raise ValueError('没有识别到坐标：请粘贴百度地图网页的完整网址，或「经度,纬度」两个数字')
    a, b = numbers
    if found or (abs(a) > 180 and abs(b) > 180):
        lng, lat = bd09mc_to_bd09(a, b)
        note = '已从百度地图网址识别地图中心点'
    else:
        if abs(a) <= 90 < abs(b):
            a, b = b, a
        lng, lat = a, b
        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
            raise ValueError('经纬度超出范围，请检查粘贴内容')
        if system == 'wgs84':
            lng, lat = gcj02_to_bd09(*wgs84_to_gcj02(lng, lat))
        elif system == 'gcj02':
            lng, lat = gcj02_to_bd09(lng, lat)
        note = '已按' + COORD_SYSTEMS.get(system, COORD_SYSTEMS['bd09']) + '换算'
    return round(lng, 7), round(lat, 7), note
