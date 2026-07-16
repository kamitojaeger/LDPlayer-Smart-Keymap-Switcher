#!/usr/bin/env python3
"""
LDPlayer 截图 — dxcam 窗口捕获方案。
直接从 Windows 桌面合成捕获 LDPlayer 的渲染窗口，完全绕过安卓截屏服务。
无闪光灯、无安卓通知、无 Windows 通知。
"""

import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

import os, time
import win32gui, win32process, win32api
import dxcam
import numpy as np
from PIL import Image

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testScreenShots")
os.makedirs(OUTPUT_DIR, exist_ok=True)
_kernel32 = ctypes.windll.kernel32


def _process_name(pid):
    h = _kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
    if not h: return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.c_uint(1024)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
    finally:
        _kernel32.CloseHandle(h)
    return None


def find_ldplayer_window():
    """找到 dnplayer.exe 的主可见窗口 + 渲染子窗口区域。"""
    target = "dnplayer.exe"
    candidates = []
    
    def enum_cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        # Allow main exe or Ld9BoxHeadless
        pn = _process_name(pid)
        if pn != target:
            return
        
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        w, h = r - l, b - t
        if w <= 0 or h <= 0:
            return
        
        # Try to find the render child window ("TheRender" class)
        render_rect = None
        
        def find_render(child_hwnd, _inner):
            nonlocal render_rect
            cls = win32gui.GetClassName(child_hwnd)
            # LDPlayer's render window class
            if cls in ("TheRender", "subWin", "RenderWindow"):
                cl, ct, cr, cb = win32gui.GetWindowRect(child_hwnd)
                cw, ch = cr - cl, cb - ct
                if cw >= 100 and ch >= 100:
                    render_rect = (cl, ct, cr, cb)
            return True
        
        win32gui.EnumChildWindows(hwnd, find_render, None)
        
        # Use render rect if found, otherwise use client area
        if render_rect:
            cap_rect = render_rect
        else:
            cl, ct, cr, cb = win32gui.GetClientRect(hwnd)
            # Convert client to screen coords
            pt = win32gui.ClientToScreen(hwnd, (cl, ct))
            cap_rect = (pt[0], pt[1], pt[0] + (cr - cl), pt[1] + (cb - ct))
        
        candidates.append((hwnd, cap_rect, w * h))
    
    win32gui.EnumWindows(enum_cb, None)
    
    if not candidates:
        return None
    
    # Pick largest window
    candidates.sort(key=lambda x: x[2], reverse=True)
    _, rect, _ = candidates[0]
    return rect


def capture(timeout=1.0):
    """截图 LDPlayer 屏幕，返回 BGR numpy 数组。
    
    完全通过 Windows Desktop Duplication API，不触发任何安卓操作。
    无闪光灯、无通知。
    """
    rect = find_ldplayer_window()
    if not rect:
        print("[screenshot] LDPlayer window not found")
        return None
    
    l, t, r, b = rect
    w, h = r - l, b - t
    
    # dxcam captures in PHYSICAL screen pixels
    cam = None
    for output_idx in range(4):
        try:
            cam = dxcam.create(output_idx=output_idx, output_color="BGR")
            break
        except Exception:
            continue
    
    if cam is None:
        print("[screenshot] dxcam: no output device found")
        return None
    
    try:
        # Clamp to screen bounds
        sw = win32api.GetSystemMetrics(0)
        sh = win32api.GetSystemMetrics(1)
        l = max(0, l); t = max(0, t)
        r = min(sw, r); b = min(sh, b)
        if r <= l or b <= t:
            return None
        
        frame = cam.grab(region=(l, t, r, b))
        if frame is not None:
            return frame  # numpy ndarray HxWx3 BGR
        
        # dxcam sometimes returns None on first call; retry
        time.sleep(0.05)
        frame = cam.grab(region=(l, t, r, b))
        return frame
    finally:
        del cam


def capture_and_save(path=None):
    """截图并保存为 PNG。"""
    img = capture()
    if img is None:
        print("[screenshot] FAILED")
        return None
    if path is None:
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(OUTPUT_DIR, f"screenshot_{ts}.png")
    # BGR -> RGB for PIL
    rgb = img[:, :, ::-1].copy()
    Image.fromarray(rgb).save(path)
    print(f"[screenshot] Saved: {path} ({img.shape[1]}x{img.shape[0]})")
    return path


if __name__ == "__main__":
    print("[screenshot] Finding LDPlayer window...")
    rect = find_ldplayer_window()
    if rect:
        l, t, r, b = rect
        print(f"[screenshot] Window: ({l},{t})-({r},{b}) = {r-l}x{b-t}")
    capture_and_save()
