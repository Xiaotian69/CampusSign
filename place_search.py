"""百度地图地点检索：按关键词搜索地点，返回百度 BD-09 坐标。

本模块只在用户主动点击「搜索」时联网，且只向百度地图开放平台发送
关键词、城市与用户自己填写的 AK；不接触学习通账号，也不参与签到流程。
AK 需在百度地图开放平台自行申请（服务端类型），仅保存在本机。
"""
import json
import math

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
