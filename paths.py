"""路径定位：区分「打包资源目录」与「用户数据目录」。

- 资源目录：profiles 等只读资源；源码运行时即项目根目录，打包后为
  PyInstaller 解压目录（``sys._MEIPASS``）。
- 数据目录：config.json / user.json 等可读写数据；源码运行时即项目根
  目录，打包后为可执行文件所在目录。
"""
import sys
from pathlib import Path


def _source_root():
    return Path(__file__).resolve().parent


def resource_root():
    """只读资源目录（profiles 等）。"""
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', _source_root()))
    return _source_root()


def data_root():
    """可读写数据目录（config.json / user.json 等）。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return _source_root()
