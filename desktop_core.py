"""CxSign 位置签到核心。

本模块负责：登录、课程匹配、活动识别、地点匹配、位置签到提交与结果复核。
网络接口地址与协议固定字段统一从 ``protocol`` 导入，业务逻辑为本项目独立实现。
"""
import asyncio
import json
import math
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

from protocol import (
    LOGIN_URL, COURSE_LIST_URL, ACTIVITY_LIST_URL, PRESIGN_URL, ADDRESS_URL, SIGN_URL,
    MOBILE_HEADERS, SIGN_CLIENT_IP, SIGN_ADDRESS, SIGN_APP_TYPE, SIGN_SUBMIT,
    LOCATION_ACTIVITY_OTHER_ID,
)

ROOT = Path(__file__).resolve().parent

# 山西财经大学坞城校区预设地点（百度 BD-09，经度在前、纬度在后）。
# 立信楼已通过 100 米范围实测；修德楼为参考点，具体活动范围以学习通为准。
DEFAULT_LOCATIONS = [
    {'name': '山西省太原市小店区坞城南路696号 山西财经大学坞城校区-立信楼',
     'longitude': 112.5930636, 'latitude': 37.792118},
    {'name': '山西省太原市小店区坞城校区坞城路696号 山西财经大学(坞城校区)-南院',
     'longitude': 112.5928775533086, 'latitude': 37.7926179807907},
    {'name': '山西财经大学-北院修德楼',
     'aliases': [
         '山西财经大学-修德楼',
         '太原市-小店区-坞城路696号山西财经大学(南校区) 山西财经大学-修德楼',
         '山西省太原市小店区坞城路696号山西财经大学(南校区) 山西财经大学-修德楼',
     ],
     'longitude': 112.59333524899067, 'latitude': 37.799147323313136},
]


# ================= 本地 JSON 读写 =================

def read_json(name, default):
    """读取项目根目录下的 JSON 文件，缺失时回退默认值。"""
    path = ROOT / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(name, value):
    """原子写入 JSON：先写临时文件再替换，避免写坏原文件。"""
    path = ROOT / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


# ================= 选择与校验 =================

def choose_course(courses, name):
    """按完整课程名精确匹配唯一课程，歧义或缺失时报错。"""
    found = [c for c in courses if c['class_name'].strip() == name.strip()]
    if not found:
        raise ValueError('没有找到此课程，请核对完整课程名及是否已加入课程')
    if len(found) != 1:
        raise ValueError('找到多个同名课程或班级，请先区分课程名称')
    return found[0]


def validate_location(name, longitude, latitude):
    """校验地点名称与经纬度合法性，返回规范化地点。"""
    lng, lat = float(longitude), float(latitude)
    if not name.strip() or not math.isfinite(lng) or not math.isfinite(lat) or not (-180 <= lng <= 180 and -90 <= lat <= 90):
        raise ValueError('地点名称不能为空，经纬度必须有效')
    return {'name': name.strip(), 'longitude': lng, 'latitude': lat}


def choose_location(address, locations):
    """把活动指定的完整地点名称匹配到地点库中的唯一点位。

    允许「地址 地点」与「地点 地址」两种顺序，忽略空格与括号/横线样式差异，
    支持别名；只做完整匹配，不做模糊或子串匹配。
    """
    def normalize(value):
        return ''.join(value.split()).replace('—', '-').replace('–', '-').replace('（', '(').replace('）', ')')

    def known_forms(name):
        forms = {normalize(name)}
        parts = name.split()
        if len(parts) == 2:
            forms.add(normalize(parts[1] + parts[0]))
        forms.discard('')
        return forms

    target = normalize(address)
    matches = [p for p in locations
               if any(target in known_forms(name)
                      for name in [p['name'], *p.get('aliases', [])])]
    if len(matches) != 1:
        raise ValueError('指定地点未匹配或匹配不唯一，请在地点库添加完整地点及百度坐标：' + address)
    point = matches[0]
    return validate_location(point['name'], point['longitude'], point['latitude'])


def classify_result(response, verification):
    """把提交响应 + 复查结果归纳为面向用户的状态文案。"""
    if response.strip() == 'success':
        return '签到成功' if verification is True else '接口已接受，复查未确认；请在学习通核对'
    return '未成功：' + response.strip()[:180]


def verified_page(body, active_id):
    """解析复查页面，确认活动 ID 匹配且页面含「签到成功」状态。"""
    soup = BeautifulSoup(body, 'lxml')
    identity = soup.select_one('input#activeId')
    return bool(identity and identity.get('value') == str(active_id)
                and any(node.get_text(strip=True) == '签到成功' for node in soup.select('span.greenColor')))


# ================= 客户端 =================

class Client:
    """围绕单个会话的学习通接口封装。"""

    def __init__(self, session):
        self.session = session
        self.uid = ''

    async def get(self, url, params=None):
        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.text()

    async def login(self, account):
        data = json.loads(await self.get(
            LOGIN_URL, {'name': account['username'], 'pwd': account['password'],
                        'schoolid': account.get('schoolid', ''), 'verify': 0}))
        if not data.get('result'):
            raise ValueError('登录失败，请核对账号密码或在学习通完成验证')
        self.uid = str(data.get('uid', ''))

    async def course(self, name):
        async with self.session.post(COURSE_LIST_URL,
                                     data={'courseType': '1', 'courseFolderId': '0', 'courseFolderSize': '0'}) as r:
            r.raise_for_status()
            soup = BeautifulSoup(await r.text(), 'lxml')
        courses = []
        for node in soup.select('li.course'):
            title = node.select_one('.course-name')
            if title and node.get('clazzid') not in (None, '0'):
                courses.append({'class_name': title.get_text(strip=True),
                                'class_id': node.get('clazzid'),
                                'course_id': node.get('courseid')})
        return choose_course(courses, name)

    async def activities(self, course):
        data = json.loads(await self.get(
            ACTIVITY_LIST_URL, {'fid': 0, 'courseId': course['course_id'],
                                'classId': course['class_id'], 'showNotStartedActive': 0}))
        if data.get('result') != 1:
            raise ValueError('活动列表读取失败')
        return [x for x in data.get('data', {}).get('activeList', [])
                if x.get('status') == 1 and x.get('type') == 2]

    async def verification(self, course, active_id):
        body = await self.get(PRESIGN_URL,
                              {'courseId': course['course_id'], 'classId': course['class_id'],
                               'activeId': active_id})
        return verified_page(body, active_id)

    async def address(self, course, active_id):
        body = await self.get(ADDRESS_URL,
                              {'courseId': course['course_id'], 'classId': course['class_id'],
                               'activePrimaryId': active_id, 'general': 1, 'sys': 1, 'ls': 1,
                               'appType': 15, 'uid': self.uid, 'ut': 's'})
        node = BeautifulSoup(body, 'lxml').select_one('#locationText')
        if not node or not node.get('value', '').strip():
            raise ValueError('未读到指定地点，需在学习通核对')
        return node['value']

    async def sign(self, active_id, location, address):
        return await self.get(
            SIGN_URL, {'name': '', 'activeId': active_id, 'address': SIGN_ADDRESS,
                       'uid': '', 'clientip': SIGN_CLIENT_IP,
                       'latitude': str(location['latitude']), 'longitude': str(location['longitude']),
                       'fid': '', 'appType': SIGN_APP_TYPE, 'ifTiJiao': SIGN_SUBMIT})


# ================= 批量执行 =================

async def run_account(account, course_name, locations, execute, emit, *, fixed_location=None):
    """处理单个账号的签到流程，逐活动上报结果。"""
    username = account['username']

    def report(activity, address, status):
        emit((username, course_name, str(activity), address, status))

    try:
        if fixed_location is not None:
            fixed_location = validate_location(fixed_location['name'], fixed_location['longitude'], fixed_location['latitude'])
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25),
                                         headers=MOBILE_HEADERS) as session:
            client = Client(session)
            await client.login(account)
            course = await client.course(course_name)
            activities = await client.activities(course)
            if not activities:
                report('', '', '没有进行中的签到')
            for activity in activities:
                aid = activity['id']
                if str(activity.get('otherId')) != LOCATION_ACTIVITY_OTHER_ID:
                    report(aid, '', '暂不支持此签到类型：' + activity.get('nameOne', '未知'))
                    continue
                address = ''
                try:
                    if await client.verification(course, aid):
                        report(aid, '', '已签到，跳过')
                        continue
                    if fixed_location is not None:
                        location = dict(fixed_location)
                        address = location['name']
                    else:
                        address = await client.address(course, aid)
                        location = choose_location(address, locations)
                    if not execute:
                        report(aid, address, '待提交 · 固定位置（尚未验证范围）' if fixed_location is not None else '可签到 · 已匹配地点')
                        continue
                    response = await client.sign(aid, location, address)
                    verification = await client.verification(course, aid) if response.strip() == 'success' else ''
                    report(aid, address, classify_result(response, verification))
                except ValueError as exc:
                    report(aid, address, str(exc))
                except Exception as exc:
                    report(aid, address, f'请求异常（{type(exc).__name__}），如已提交请先在学习通核对')
    except ValueError as exc:
        report('', '', str(exc))
    except Exception as exc:
        # 异常对象完整字符串可能携带凭据，仅输出类型名。
        report('', '', f'读取失败（{type(exc).__name__}），请检查网络或稍后重试')


async def run_batch(accounts, course_name, locations, execute, emit, *, fixed_location=None):
    """并发处理多个账号（最多 2 个并发），彼此隔离。"""
    semaphore = asyncio.Semaphore(2)

    async def task(account):
        async with semaphore:
            await run_account(account, course_name, locations, execute, emit, fixed_location=fixed_location)

    await asyncio.gather(*(task(account) for account in accounts))
