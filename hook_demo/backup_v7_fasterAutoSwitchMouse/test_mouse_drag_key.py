#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：对雷电模拟器窗口发送各种 key，验证哪个能触发射击视角切换。

依次尝试：
  1. SendInput 发送 VK_SPACE  (switch-mouse 宏 绑定的 key)
  2. SendInput 发送 VK_CONTROL (ClassMouseDrag 绑定的 key)
  3. SendInput 短按 VK_SPACE
  4. PostMessage 发送 VK_SPACE 到 LDPlayer 窗口

每次按键间隔 2 秒，观察模拟器是否进入/退出射击视角。
"""

import time
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

# ── 虚拟键码 ──
VK_SPACE = 0x20
VK_CONTROL = 0x11

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", INPUT_UNION)]


# ── SendInput 按键 ──
def press_key(vk: int):
    """SendInput: 按下"""
    inp = INPUT(INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(vk, 0, 0, 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def release_key(vk: int):
    """SendInput: 释放"""
    inp = INPUT(INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def tap_key(vk: int, hold_ms: int = 80):
    """SendInput: 按下 → 等 hold_ms → 释放"""
    press_key(vk)
    time.sleep(hold_ms / 1000.0)
    release_key(vk)


def find_ldplayer_hwnd():
    """找到雷电模拟器主窗口句柄。"""
    target = None

    def enum_cb(hwnd, _):
        nonlocal target
        if not user32.IsWindowVisible(hwnd):
            return 1
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        name = buf.value.lower()
        if "ldplayer" in name or "雷电" in name:
            target = hwnd
            return 0  # stop
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int)
    cb = WNDENUMPROC(enum_cb)
    user32.EnumWindows(cb, 0)
    return target


def focus_window(hwnd):
    """尝试将窗口放到前台。"""
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    if fg_thread != target_thread:
        user32.AttachThreadInput(target_thread, fg_thread, True)
    user32.SetForegroundWindow(hwnd)
    if fg_thread != target_thread:
        user32.AttachThreadInput(target_thread, fg_thread, False)
    time.sleep(0.3)


def post_key(hwnd, vk: int):
    """PostMessage 发送 key down + key up 到指定窗口。"""
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0x00000001)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, 0xC0000001)


def post_ctrl_f(hwnd):
    """PostMessage 发送 Ctrl+F。"""
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    VK_CONTROL = 0x11
    VK_F = 0x46
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_CONTROL, 0x001D0001)
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_F, 0x00210001)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_F, 0xC0210001)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_CONTROL, 0xC01D0001)


# ── 主流程 ──
def main():
    hwnd = find_ldplayer_hwnd()
    if not hwnd:
        print("未找到雷电模拟器窗口！请先启动模拟器。")
        return
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    print(f"找到窗口: hwnd={hwnd:#x}  title='{buf.value}'")
    focus_window(hwnd)

    tests = [
        ("SendInput 点击 Space (switch-mouse 宏)", lambda: tap_key(VK_SPACE)),
        ("SendInput 点击 Ctrl (ClassMouseDrag key)", lambda: tap_key(VK_CONTROL)),
        ("SendInput 长按 Space 500ms", lambda: (press_key(VK_SPACE), time.sleep(0.5), release_key(VK_SPACE))),
        ("SendInput 长按 Ctrl 500ms", lambda: (press_key(VK_CONTROL), time.sleep(0.5), release_key(VK_CONTROL))),
        ("PostMessage Space → LDPlayer 窗口", lambda: post_key(hwnd, VK_SPACE)),
        ("PostMessage Ctrl+F (模拟切换按键方案)", lambda: post_ctrl_f(hwnd)),
    ]

    for desc, fn in tests:
        print(f"\n{'='*60}")
        print(f"→ {desc}")
        fn()
        print("  已发送，等待 2 秒观察模拟器反应...")
        time.sleep(2)


if __name__ == "__main__":
    main()
