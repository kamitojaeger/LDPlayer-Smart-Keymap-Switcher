#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LDPlayer Android 原生分辨率截图模块

通过 LDPlayer 内置截图功能（Ctrl+0 热键）获取安卓系统原生分辨率截图。
截图始终为固定分辨率（如 1920x1080），不受 LDPlayer 窗口缩放/最大化/全屏影响。

方案说明：
  - 使用 PostMessage 发送 Ctrl+0 到 LDPlayer 窗口，触发内置截图
  - 截图保存到用户目录的 XuanZhi14/Pictures/Screenshots/
  - 文件名格式: Screenshot_YYYYMMDD-HHMMSS.png
  - 分辨率：始终为安卓系统原生分辨率（如 1920x1080）

已知限制：
  - 截图后安卓系统和 Windows 端会短暂显示截图提示（Toast）
  - Toast 抑制方案见 ld_screenshot_hook 模块（开发中）
"""

import os
import sys
import time
import ctypes
import glob
import subprocess
from ctypes import wintypes
from PIL import Image

# ---- Win32 API ----
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ---- 配置 ----
# LDPlayer 截图保存目录
SCREENSHOT_DIR = os.path.expandvars(
    r"%USERPROFILE%\Documents\XuanZhi14\Pictures\Screenshots"
)

# 安卓原生分辨率（从 LDPlayer 配置读取）
ANDROID_WIDTH = 1920
ANDROID_HEIGHT = 1080

# 截图等待超时（秒）
SCREENSHOT_TIMEOUT = 5.0

# ---- 全局状态 ----
_ld_hwnd = None
_screenshot_seq = 0


def find_ldplayer_window():
    """查找 LDPlayer 主窗口句柄。
    
    LDPlayer 主窗口使用 Qt 创建，类名可能为 "LDPlayerMainFrame" 或 "L"，
    窗  口标题为 "LDPlayer"。按以下优先级查找：
    1. 类名 "LDPlayerMainFrame"
    2. 标题 "LDPlayer"
    3. 进程名枚举 "dnplayer.exe"
    """
    global _ld_hwnd
    
    # 1) 尝试类名 "LDPlayerMainFrame" (LDPlayer14)
    hwnd = user32.FindWindowW("LDPlayerMainFrame", None)
    if hwnd:
        _ld_hwnd = hwnd
        return hwnd
    
    # 2) Fallback: 类名 "L" (旧版本)
    hwnd = user32.FindWindowW("L", None)
    if hwnd:
        _ld_hwnd = hwnd
        return hwnd
    
    # 3) Fallback: 标题查找
    hwnd = user32.FindWindowW(None, "LDPlayer")
    if hwnd:
        _ld_hwnd = hwnd
        return hwnd
    
    # 4) Fallback: 枚举窗口查找 dnplayer.exe
    def enum_callback(hwnd, lParam):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if hwnd and user32.IsWindowVisible(hwnd):
            h = kernel32.OpenProcess(0x0400 | 0x0010, False, process_id)
            if h:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value).lower()
                    if name == "dnplayer.exe":
                        kernel32.CloseHandle(h)
                        rect = wintypes.RECT()
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        area = (rect.right - rect.left) * (rect.bottom - rect.top)
                        if area > 10000:  # 最小面积过滤
                            _ld_hwnd = hwnd
                            ctypes.cast(lParam, ctypes.POINTER(wintypes.HWND))[0] = hwnd
                            return False  # 停止枚举
                kernel32.CloseHandle(h)
        return True
    
    result = wintypes.HWND(0)
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_callback), ctypes.byref(result))
    
    if result.value:
        _ld_hwnd = result.value
    return result.value or None


def trigger_screenshot(hwnd=None):
    """通过子进程发送 Ctrl+0 热键触发 LDPlayer 截图。
    
    参考 keymap_injector 的实现方式：用 subprocess 启动独立子进程，
    子进程通过 AllowSetForegroundWindow + SetForegroundWindow 获取焦点，
    然后用 keybd_event 发送 Ctrl+0。
    
    子进程方式解决了 CMD 控制台宿主前台锁定问题。
    """
    if hwnd is None:
        hwnd = find_ldplayer_window()
    if not hwnd:
        raise RuntimeError("未找到 LDPlayer 窗口")
    
    before_files = set()
    if os.path.isdir(SCREENSHOT_DIR):
        before_files = set(glob.glob(os.path.join(SCREENSHOT_DIR, "Screenshot_*.png")))
    
    # 使用子进程发送热键（绕过控制台前台锁定）
    helper_code = f'''
import ctypes, time, sys
user32 = ctypes.windll.user32

hwnd = {hwnd}
if not user32.IsWindow(hwnd):
    sys.exit(1)

if user32.IsIconic(hwnd):
    user32.ShowWindow(hwnd, 9)
    time.sleep(0.2)

user32.AllowSetForegroundWindow(0xFFFFFFFF)
user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001)
user32.SetForegroundWindow(hwnd)
time.sleep(0.25)
user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0002 | 0x0001)

user32.keybd_event(0x11, 0, 0, 0)
time.sleep(0.08)
user32.keybd_event(0x30, 0, 0, 0)
time.sleep(0.08)
user32.keybd_event(0x30, 0, 2, 0)
time.sleep(0.05)
user32.keybd_event(0x11, 0, 2, 0)
'''
    
    try:
        subprocess.run(
            [sys.executable, "-c", helper_code],
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    
    return before_files


def wait_for_screenshot(before_files, timeout=SCREENSHOT_TIMEOUT):
    """等待截图文件出现在目录中。
    
    Args:
        before_files: 截图前已有的文件集合
        timeout: 超时时间（秒）
    
    Returns:
        str: 新截图文件路径，超时返回 None
    """
    start = time.time()
    while time.time() - start < timeout:
        if os.path.isdir(SCREENSHOT_DIR):
            current = set(glob.glob(os.path.join(SCREENSHOT_DIR, "Screenshot_*.png")))
            new_files = current - before_files
            if new_files:
                # 按修改时间排序，取最新的
                new_list = sorted(new_files, key=os.path.getmtime, reverse=True)
                latest = new_list[0]
                # 等待文件完全写入（不再增长）
                time.sleep(0.1)
                return latest
        time.sleep(0.1)
    return None


def capture_screenshot(hwnd=None, timeout=SCREENSHOT_TIMEOUT):
    """触发并获取一张 LDPlayer 安卓原生分辨率截图。
    
    截图始终为安卓系统原生分辨率（如 1920x1080），
    不受 LDPlayer 窗口缩放、最大化、全屏等影响。
    
    Args:
        hwnd: LDPlayer 窗口句柄，None 则自动查找
        timeout: 等待截图文件的超时时间（秒）
    
    Returns:
        tuple: (PIL.Image, str) - 截图图像对象和文件路径
        失败返回 (None, None)
    """
    global _screenshot_seq
    _screenshot_seq += 1
    
    if hwnd is None:
        hwnd = find_ldplayer_window()
    if not hwnd:
        return None, None
    
    try:
        before_files = trigger_screenshot(hwnd)
        filepath = wait_for_screenshot(before_files, timeout)
        
        if filepath and os.path.exists(filepath):
            img = Image.open(filepath)
            return img, filepath
        
        return None, None
    
    except Exception as e:
        print(f"[截图] 错误: {e}")
        return None, None


def capture_to_numpy(hwnd=None, timeout=SCREENSHOT_TIMEOUT):
    """触发截图并返回 numpy 数组（BGR 格式，兼容 OpenCV）。
    
    Args:
        hwnd: LDPlayer 窗口句柄
        timeout: 超时时间
    
    Returns:
        numpy.ndarray or None: BGR 格式的截图数组
    """
    import numpy as np
    
    img, _ = capture_screenshot(hwnd, timeout)
    if img is None:
        return None
    
    # PIL Image (RGB) → numpy (BGR) for OpenCV
    return np.array(img)[:, :, ::-1].copy()


def get_screenshot_dir():
    """返回 LDPlayer 截图保存目录。"""
    return SCREENSHOT_DIR


def get_android_resolution():
    """返回安卓系统原生分辨率 (width, height)。"""
    return (ANDROID_WIDTH, ANDROID_HEIGHT)


# ---- 测试入口 ----
if __name__ == "__main__":
    print(f"截图目录: {SCREENSHOT_DIR}")
    print(f"安卓分辨率: {ANDROID_WIDTH}x{ANDROID_HEIGHT}")
    
    hwnd = find_ldplayer_window()
    if hwnd:
        print(f"LDPlayer 窗口: HWND=0x{hwnd:08X}")
        print("正在截图...")
        img, path = capture_screenshot(hwnd)
        if img:
            print(f"截图成功: {path}")
            print(f"分辨率: {img.size}")
            print(f"格式: {img.mode}")
        else:
            print("截图失败：超时或文件未找到")
    else:
        print("未找到 LDPlayer 窗口，请确保模拟器正在运行")
