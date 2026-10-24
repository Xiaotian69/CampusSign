"""弹窗定位：按内容尺寸放置，并限制在当前显示器的可用区域内。"""
import os
import tkinter as tk


def work_area(widget):
    """返回 widget 所在显示器的可用区域 (left, top, right, bottom)，不含任务栏。"""
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes

            class MonitorInfo(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                            ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]
            user32 = ctypes.windll.user32
            user32.MonitorFromPoint.restype = ctypes.c_void_p
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MonitorInfo)]
            top = widget.winfo_toplevel()
            point = wintypes.POINT(top.winfo_rootx() + top.winfo_width() // 2,
                                   top.winfo_rooty() + top.winfo_height() // 2)
            info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
            monitor = user32.MonitorFromPoint(point, 2)  # MONITOR_DEFAULTTONEAREST
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.rcWork
                if r.right > r.left and r.bottom > r.top:
                    return r.left, r.top, r.right, r.bottom
        except (OSError, AttributeError, tk.TclError):
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight() - 48


def place_in_work_area(parent, win, margin=24):
    """按内容需要的尺寸放置弹窗；空间不足时缩小并居中，底部按钮需先于正文 pack。"""
    win.update_idletasks()
    left, top, right, bottom = work_area(parent)
    width = min(win.winfo_reqwidth(), right - left - 2 * margin)
    # 标题栏不计入 geometry 高度，额外预留。
    height = min(win.winfo_reqheight(), bottom - top - 2 * margin - 40)
    x = left + max(0, (right - left - width) // 2)
    y = top + max(0, (bottom - top - height - 40) // 2)
    win.geometry(f'{width}x{height}+{x}+{y}')
    win.minsize(min(width, 360), min(height, 260))
