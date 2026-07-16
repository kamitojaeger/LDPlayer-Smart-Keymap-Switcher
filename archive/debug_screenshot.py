#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LDPlayer 截图诊断工具 —— 逐步检测截图失败原因
用法: python debug_screenshot.py
"""

import ctypes
import time
import os
import glob

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

print("=" * 60)
print("LDPlayer 截图诊断")
print("=" * 60)

# 1. 查找窗口
hwnd = user32.FindWindowW("LDPlayerMainFrame", None)
if not hwnd:
    hwnd = user32.FindWindowW(None, "LDPlayer")
print(f"\n[检测1] LDPlayer 窗口: 0x{hwnd:08X}")
if not hwnd:
    print("  ❌ 未找到窗口，终止")
    exit(1)

# 2. 检查窗口状态
import ctypes.wintypes as w
r = w.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(r))
wnd_w, wnd_h = r.right - r.left, r.bottom - r.top
iconic = user32.IsIconic(hwnd)
visible = user32.IsWindowVisible(hwnd)
print(f"\n[检测2] 窗口状态:")
print(f"  可见: {visible}")
print(f"  最小化: {iconic}")
print(f"  尺寸: {wnd_w}x{wnd_h}")
print(f"  位置: ({r.left},{r.top})-({r.right},{r.bottom})")

# 3. 获取前景窗口
fg_before = user32.GetForegroundWindow()
print(f"\n[检测3] 当前前台窗口: 0x{fg_before:08X}")

# 4. 尝试获取前台
print(f"\n[检测4] 尝试切换前台...")
user32.AllowSetForegroundWindow(0xFFFFFFFF)
time.sleep(0.05)

if user32.IsIconic(hwnd):
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    time.sleep(0.2)
    print(f"  已恢复最小化窗口")

user32.BringWindowToTop(hwnd)
time.sleep(0.05)
sfw_result = user32.SetForegroundWindow(hwnd)
time.sleep(0.3)

fg_after = user32.GetForegroundWindow()
print(f"  SetForegroundWindow 返回值: {sfw_result}")
print(f"  切换后前台窗口: 0x{fg_after:08X}")
print(f"  匹配: {'✅' if fg_after == hwnd else '❌'}")

# 5. AttachThreadInput fallback
if fg_after != hwnd:
    print(f"\n[检测5] 前台切换失败，尝试 AttachThreadInput...")
    our_tid = kernel32.GetCurrentThreadId()
    their_tid = user32.GetWindowThreadProcessId(hwnd, None)
    print(f"  本线程ID: {our_tid}")
    print(f"  目标线程ID: {their_tid}")
    
    attached = user32.AttachThreadInput(our_tid, their_tid, True)
    print(f"  AttachThreadInput: {attached}")
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)
    time.sleep(0.2)
    user32.AttachThreadInput(our_tid, their_tid, False)
    
    fg_after2 = user32.GetForegroundWindow()
    print(f"  最终前台窗口: 0x{fg_after2:08X}")
    print(f"  匹配: {'✅' if fg_after2 == hwnd else '❌ (keybd_event 可能无效)'}")

# 6. 读取 LDPlayer 配置确认热键
print(f"\n[检测6] 读取 LDPlayer 配置...")
config_paths = [
    r"F:\LDPlayer\LDPlayer14\vms\config\leidian0.config",
    r"F:\LDPlayer\LDPlayer14\vms\config\leidian1.config",
]
for cp in config_paths:
    if os.path.exists(cp):
        import json
        with open(cp, 'r') as f:
            cfg = json.load(f)
        sc = cfg.get("hotkeySettings.screenCutKey", {})
        print(f"  {os.path.basename(cp)}:")
        key_val = sc.get('key', 0)
        key_name = chr(key_val) if 32 <= key_val < 127 else '?'
        print(f"    screenCutKey: mod={sc.get('modifiers')}, key={key_val} (VK name: {key_name})")

# 7. 检查截图目录
pic_dir = os.path.expandvars(r"%USERPROFILE%\Documents\XuanZhi14\Pictures\Screenshots")
print(f"\n[检测7] 截图目录: {pic_dir}")
print(f"  存在: {os.path.isdir(pic_dir)}")
if os.path.isdir(pic_dir):
    before = set(glob.glob(os.path.join(pic_dir, "Screenshot_*.png")))
    print(f"  现有截图: {len(before)} 个")
else:
    before = set()

# 8. 发送 Ctrl+0
print(f"\n[检测8] 发送 Ctrl+0 热键...")
VK_CONTROL = 0x11
VK_0 = 0x30
KEYUP = 0x0002

# 方法 A: keybd_event (标准)
user32.keybd_event(VK_CONTROL, 0, 0, 0)
time.sleep(0.05)
user32.keybd_event(VK_0, 0, 0, 0)
time.sleep(0.05)
user32.keybd_event(VK_0, 0, KEYUP, 0)
time.sleep(0.05)
user32.keybd_event(VK_CONTROL, 0, KEYUP, 0)
print(f"  keybd_event 已发送")

time.sleep(0.5)

# 检查是否立即生效
current1 = set(glob.glob(os.path.join(pic_dir, "Screenshot_*.png")))
new1 = current1 - before
if new1:
    print(f"  ✅ 方法A成功: {list(new1)[0]}")
else:
    print(f"  ❌ 方法A未产生截图，尝试方法B...")
    
    # 方法 B: 使用 SendInput 发送扫描码
    import ctypes.wintypes as w
    
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", w.WORD),
            ("wScan", w.WORD),
            ("dwFlags", w.DWORD),
            ("time", w.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]
    
    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [
                ("ki", KEYBDINPUT),
            ]
        _anonymous_ = ("_input",)
        _fields_ = [
            ("type", w.DWORD),
            ("_input", _INPUT),
        ]
    
    # Ctrl 扫描码 = 0x1D, 0 扫描码 = 0x0B
    KEYEVENTF_SCANCODE = 0x0008
    
    inputs = (INPUT * 6)()
    
    # Ctrl down
    inputs[0].type = 1
    inputs[0].ki.wVk = VK_CONTROL
    inputs[0].ki.wScan = 0x1D
    inputs[0].ki.dwFlags = KEYEVENTF_SCANCODE
    
    # 0 down
    inputs[1].type = 1
    inputs[1].ki.wVk = VK_0
    inputs[1].ki.wScan = 0x0B
    inputs[1].ki.dwFlags = KEYEVENTF_SCANCODE
    
    # 0 up
    inputs[2].type = 1
    inputs[2].ki.wVk = VK_0
    inputs[2].ki.wScan = 0x0B
    inputs[2].ki.dwFlags = KEYEVENTF_SCANCODE | KEYUP
    
    # Ctrl up
    inputs[3].type = 1
    inputs[3].ki.wVk = VK_CONTROL
    inputs[3].ki.wScan = 0x1D
    inputs[3].ki.dwFlags = KEYEVENTF_SCANCODE | KEYUP
    
    ctypes.windll.user32.SendInput(4, inputs, ctypes.sizeof(INPUT))
    print(f"  SendInput(scan code) 已发送")
    
    time.sleep(2.0)
    
    current2 = set(glob.glob(os.path.join(pic_dir, "Screenshot_*.png")))
    new2 = current2 - before
    if new2:
        print(f"  ✅ 方法B成功: {list(new2)[0]}")
    else:
        print(f"  ❌ 方法B也未产生截图")
        
        # 列出目录中最新的文件
        print(f"\n  截图目录内容:")
        all_files = sorted(glob.glob(os.path.join(pic_dir, "*")), 
                          key=os.path.getmtime, reverse=True)
        for f in all_files[:5]:
            print(f"    {os.path.basename(f)} — {time.ctime(os.path.getmtime(f))}")

print(f"\n{'=' * 60}")
print("诊断完成")
print(f"{'=' * 60}")
