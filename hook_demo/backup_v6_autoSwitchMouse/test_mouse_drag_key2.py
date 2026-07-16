#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
第二轮测试：尝试绕过 LDPlayer 的低级键盘钩子过滤。

SendInput 会被 LLKHF_INJECTED 标志暴露，LDPlayer 的 WH_KEYBOARD_LL 钩子会过滤掉。
此脚本尝试其他方式。

依次测试：
  1. keybd_event (deprecated API, 可能不设 INJECTED 标志)
  2. PostMessage WM_KEYDOWN/UP with scancode lParam (更真实的模拟)
  3. PostMessage to Render 子窗口 (R class)
  4. SendInput with KEYEVENTF_SCANCODE (扫描码方式)
"""

import time
import os
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

VK_SPACE = 0x20
VK_CONTROL = 0x11

# ═══════════════════════════════════════════════════════════
# 找到窗口
# ═══════════════════════════════════════════════════════════
def find_ldplayer_windows():
    """返回 (main_hwnd, render_hwnd) — 用进程名 dnplayer.exe 精确匹配"""
    kernel32 = ctypes.windll.kernel32
    main = None
    render = None
    max_area = [0]  # mutable for closure

    def get_pname(pid):
        h = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            sz = ctypes.c_uint(260)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h)
        return ""

    def enum_cb(hwnd, _):
        nonlocal main, render
        if not user32.IsWindowVisible(hwnd):
            return 1
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if get_pname(pid.value) != "dnplayer.exe":
            return 1
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        if r.right <= r.left or r.bottom <= r.top:
            return 1
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > max_area[0]:
            max_area[0] = area
            main = hwnd
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == 'R':
            render = hwnd
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return main, render


def focus(hwnd):
    user32.ShowWindow(hwnd, 9)
    fg = user32.GetForegroundWindow()
    ft = user32.GetWindowThreadProcessId(fg, None)
    tt = user32.GetWindowThreadProcessId(hwnd, None)
    if ft != tt:
        user32.AttachThreadInput(tt, ft, True)
    user32.SetForegroundWindow(hwnd)
    if ft != tt:
        user32.AttachThreadInput(tt, ft, False)
    time.sleep(0.3)


# ═══════════════════════════════════════════════════════════
# 方法 1: keybd_event (deprecated, 可能无 INJECTED 标志)
# ═══════════════════════════════════════════════════════════
def test_keybd_event():
    print("→ keybd_event VK_SPACE (down+up)")
    user32.keybd_event(VK_SPACE, 0, 0, 0)
    time.sleep(0.08)
    user32.keybd_event(VK_SPACE, 0, 2, 0)  # KEYEVENTF_KEYUP


# ═══════════════════════════════════════════════════════════
# 方法 2: PostMessage with scan code
# ═══════════════════════════════════════════════════════════
def test_postmessage_scancode(hwnd):
    """PostMessage with scan-code lParam (bit 16-23 = scan code, bit 24 = extended)"""
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    # Space scan code = 0x39
    # lParam: bits 0-15=repeat count, 16-23=scan code, 24=extended, 29=context, 30=prev state, 31=transition
    scan_code = 0x39
    lparam_down = (scan_code << 16) | 1  # scan code in bits 16-23, repeat=1
    lparam_up = (scan_code << 16) | (1 << 31) | (1 << 30) | 1  # transition=1, prev_state=1
    
    print(f"→ PostMessage WM_KEYDOWN/UP (Space) to hwnd={hwnd:#x}")
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_SPACE, lparam_down)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_SPACE, lparam_up)


# ═══════════════════════════════════════════════════════════
# 方法 3: SendInput with SCANCODE flag
# ═══════════════════════════════════════════════════════════
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]
class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", INPUT_UNION)]

def test_sendinput_scancode():
    """SendInput with KEYEVENTF_SCANCODE - uses hardware scan codes instead of VK"""
    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_KEYUP = 0x0002
    SCAN_SPACE = 0x39
    
    print("→ SendInput SCANCODE Space (down+up)")
    down = INPUT(1)  # INPUT_KEYBOARD
    down.u.ki = KEYBDINPUT(SCAN_SPACE, SCAN_SPACE, KEYEVENTF_SCANCODE, 0, 0)
    up = INPUT(1)
    up.u.ki = KEYBDINPUT(SCAN_SPACE, SCAN_SPACE, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0)
    
    inputs = (INPUT * 2)(down, up)
    ctypes.windll.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))


# ═══════════════════════════════════════════════════════════
# 方法 4: SendMessage (not Post) to Render window
# ═══════════════════════════════════════════════════════════
def test_sendmessage_render(render_hwnd):
    """SendMessage (同步) to Render 子窗口 - 某些应用只处理 SendMessage"""
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    scan_code = 0x39
    lparam_down = (scan_code << 16) | 1
    lparam_up = (scan_code << 16) | (1 << 31) | (1 << 30) | 1
    
    print(f"→ SendMessage WM_KEYDOWN/UP (Space) to Render hwnd={render_hwnd:#x}")
    user32.SendMessageW(render_hwnd, WM_KEYDOWN, VK_SPACE, lparam_down)
    time.sleep(0.05)
    user32.SendMessageW(render_hwnd, WM_KEYUP, VK_SPACE, lparam_up)


# ═══════════════════════════════════════════════════════════
# 方法 5: SendInput with custom dwExtraInfo
# ═══════════════════════════════════════════════════════════
def test_sendinput_customextra():
    """SendInput with non-zero dwExtraInfo - some hooks only filter zero"""
    print("→ SendInput VK_SPACE with dwExtraInfo=0xDEADBEEF")
    down = INPUT(1)
    down.u.ki = KEYBDINPUT(VK_SPACE, 0, 0, 0, ctypes.c_void_p(0xDEADBEEF))
    up = INPUT(1)
    up.u.ki = KEYBDINPUT(VK_SPACE, 0, 2, 0, ctypes.c_void_p(0xDEADBEEF))
    inputs = (INPUT * 2)(down, up)
    ctypes.windll.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))


# ═══════════════════════════════════════════════════════════
# 方法 6: 组合键 - Post Ctrl+F 切换，再用 keybd_event Space
# ═══════════════════════════════════════════════════════════
def test_ctrlf_then_space(hwnd):
    """先 Post Ctrl+F (确认窗口能接收 PostMessage), 再用 keybd_event Space"""
    print("→ Post Ctrl+F (验证 PostMessage 通路)")
    user32.PostMessageW(hwnd, 0x0100, 0x11, 0x001D0001)  # Ctrl down
    user32.PostMessageW(hwnd, 0x0100, 0x46, 0x00210001)   # F down
    time.sleep(0.05)
    user32.PostMessageW(hwnd, 0x0101, 0x46, 0xC0210001)   # F up
    user32.PostMessageW(hwnd, 0x0101, 0x11, 0xC01D0001)   # Ctrl up
    time.sleep(1.0)  # 等切换完成
    print("  → 然后 keybd_event Space")
    user32.keybd_event(VK_SPACE, 0, 0, 0)
    time.sleep(0.08)
    user32.keybd_event(VK_SPACE, 0, 2, 0)


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════
def main():
    main_hwnd, render_hwnd = find_ldplayer_windows()
    if not main_hwnd:
        print("未找到雷电模拟器窗口！")
        return
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(main_hwnd, buf, 256)
    print(f"Main: hwnd={main_hwnd:#x} title='{buf.value}'")
    print(f"Render: hwnd={render_hwnd:#x}" if render_hwnd else "Render: NOT FOUND")
    focus(main_hwnd)

    tests = [
        ("keybd_event Space", test_keybd_event),
        ("SendInput SCANCODE Space", test_sendinput_scancode),
        ("SendInput Space (custom dwExtraInfo)", test_sendinput_customextra),
    ]

    if main_hwnd:
        tests.append(("PostMessage Space (scan lParam)", lambda: test_postmessage_scancode(main_hwnd)))
    if render_hwnd:
        tests.append(("SendMessage Space → Render", lambda: test_sendmessage_render(render_hwnd)))
    if main_hwnd:
        tests.append(("Ctrl+F 切换 + keybd_event Space", lambda: test_ctrlf_then_space(main_hwnd)))

    for desc, fn in tests:
        print(f"\n{'='*60}")
        print(f"→ {desc}")
        fn()
        print("  已发送，等待 2 秒观察...")
        time.sleep(2)


if __name__ == "__main__":
    main()
