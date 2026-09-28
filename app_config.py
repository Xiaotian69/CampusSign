"""应用级配置：品牌信息、Edition 档案与本地配置读取。

本模块只负责「读配置」，不参与任何签到网络逻辑；签到核心独立于
``desktop_core.py``，二者互不依赖。
"""
import json
from pathlib import Path

from paths import resource_root, data_root

# ===== 品牌信息 =====
APP_NAME = 'CxSign'
APP_VERSION = '1.0.0'
REPO_URL = 'https://github.com/Xiaotian69/CampusSign'
ISSUES_URL = REPO_URL + '/issues'
EXAM_REPO_URL = 'https://github.com/Xiaotian69/shanxi-caijing-exams'

# ===== Edition =====
SUPPORTED_EDITIONS = ('scufe', 'generic')
DEFAULT_EDITION = 'scufe'

# 本地 config.json（不进入公开仓库）可覆盖 edition / dev_mode。
DEFAULT_CONFIG = {'edition': DEFAULT_EDITION, 'dev_mode': False}


def load_json_file(path, default):
    """读取指定路径的 JSON 文件，缺失或损坏时回退到默认值。"""
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return default


def load_config():
    """读取本地运行配置（edition、dev_mode），缺省时使用安全默认值。"""
    config = dict(DEFAULT_CONFIG)
    config.update(load_json_file(data_root() / 'config.json', {}))
    if config.get('edition') not in SUPPORTED_EDITIONS:
        config['edition'] = DEFAULT_EDITION
    return config


def load_profile(edition):
    """读取指定 Edition 的档案，返回其预设地点与显示名。"""
    if edition not in SUPPORTED_EDITIONS:
        edition = DEFAULT_EDITION
    profile = load_json_file(resource_root() / 'profiles' / f'{edition}.json', {})
    profile.setdefault('key', edition)
    profile.setdefault('display_name', edition)
    profile.setdefault('display_name_zh', edition)
    profile.setdefault('preset_locations', [])
    return profile
