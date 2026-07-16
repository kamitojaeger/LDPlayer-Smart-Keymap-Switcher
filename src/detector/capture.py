#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
截图模块 — LDPlayer 安卓画面截取

功能：
  1. 实例守卫：统计 dnplayer.exe（模拟器主进程）数量
  2. 枚举 LDPlayer 窗口获取截图区域
  3. dxcam 截图 + 保存 PNG

截图策略（由 resolve_capture_target 实现）：
  - 优先 RenderWindow 子窗口（纯安卓画面，无上边栏/工具栏）
  - 回退 dnplayer 客户端区域（GetClientRect）
"""

import os
import ctypes
import ctypes.wintypes

# ---- DPI 感知：必须在 import dxcam 之前设置，使其返回物理像素 ----
try:
    # PROCESS_PER_MONITOR_DPI_AWARE = 2
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ---- 外部依赖 ----
import win32gui
import win32process
import win32api
import dxcam
from PIL import Image

# ---- 常量 ----
EMULATOR_PROCESS = "dnplayer.exe"
TARGET_PROCESS = "Ld9BoxHeadless.exe"

_kernel32 = ctypes.windll.kernel32


# ---------------------------------------------------------------------------
# 1. 通过 PID 取进程名（跨 32/64 位，使用 QueryFullProcessImageNameW）
# ---------------------------------------------------------------------------
def get_process_name(pid: int):
    """返回指定 PID 的进程名（小写），失败返回 None。"""
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    handle = _kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_uint(1024)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return None
    finally:
        _kernel32.CloseHandle(handle)


# ---------------------------------------------------------------------------
# 2. 统计某进程名的"不同 PID"数量（实例守卫用）
# ---------------------------------------------------------------------------
def count_processes(process_name: str):
    """返回指定进程名的不同 PID 数量。"""
    target = process_name.lower()
    pids = set()

    def _enum_cb(hwnd, _):
        if not win32gui.IsWindow(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if get_process_name(pid) == target:
            pids.add(pid)

    win32gui.EnumWindows(_enum_cb, None)
    return len(pids)


# ---------------------------------------------------------------------------
# 3. 枚举窗口：按进程名找到所有"可见且有尺寸"的窗口
# ---------------------------------------------------------------------------
def find_visible_windows(process_name: str):
    """返回按面积降序排列的 (hwnd, rect, area) 列表。"""
    target = process_name.lower()
    found = []

    def _enum_cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if get_process_name(pid) != target:
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return
        found.append((hwnd, (left, top, right, bottom), width * height))

    win32gui.EnumWindows(_enum_cb, None)
    found.sort(key=lambda x: x[2], reverse=True)
    return found


# ---------------------------------------------------------------------------
# 4. 取 dnplayer 主窗口的"客户端区域"屏幕坐标
# ---------------------------------------------------------------------------
def get_dnplayer_client_rect():
    """返回 dnplayer 客户端区域的屏幕坐标 (left, top, right, bottom)，失败返回 None。"""
    dn = find_visible_windows(EMULATOR_PROCESS)
    if not dn:
        return None
    hwnd = dn[0][0]
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    sx, sy = win32gui.ClientToScreen(hwnd, (left, top))
    return (sx, sy, sx + right, sy + bottom)


# ---------------------------------------------------------------------------
# 5. 获取 dnplayer 内部 RenderWindow 子窗口屏幕坐标（纯安卓画面）
# ---------------------------------------------------------------------------
def get_dnplayer_render_rect():
    """返回 dnplayer 内 RenderWindow 子窗口的屏幕坐标 (left, top, right, bottom)。
       该窗口仅包含安卓渲染画面，不包含上边栏和右侧工具栏。
       无 RenderWindow 时返回 None。"""
    dn = find_visible_windows(EMULATOR_PROCESS)
    if not dn:
        return None
    hwnd = dn[0][0]

    render_hwnd = [None]

    def child_cb(chwnd, _):
        cls = win32gui.GetClassName(chwnd)
        if cls == "RenderWindow" and win32gui.IsWindowVisible(chwnd):
            rect = win32gui.GetWindowRect(chwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w > 100 and h > 100:
                render_hwnd[0] = chwnd
                return False  # 找到即停

    win32gui.EnumChildWindows(hwnd, child_cb, None)
    if render_hwnd[0]:
        return win32gui.GetWindowRect(render_hwnd[0])
    return None


# ---------------------------------------------------------------------------
# 6. 获取 dnplayer.exe 主窗口句柄
# ---------------------------------------------------------------------------
def get_dnplayer_hwnd():
    """返回 dnplayer.exe 面积最大可见窗口的 HWND，无则返回 None。"""
    dn = find_visible_windows(EMULATOR_PROCESS)
    return dn[0][0] if dn else None


# ---------------------------------------------------------------------------
# 7. 计算截图目标区域 + 来源说明
# ---------------------------------------------------------------------------
def resolve_capture_target(process_name: str):
    """返回 (rect, source_description, visible_windows_list)。

       process_name 如 "Ld9BoxHeadless.exe" 时，优先取 RenderWindow，
       回退到 dnplayer 客户端区域。
    """
    wins = find_visible_windows(process_name)
    if wins:
        hwnd, rect, _ = wins[0]
        return rect, "process visible window", wins

    # 无可见窗口 → 针对 headless 渲染进程
    if process_name.lower() == "ld9boxheadless.exe":
        render_rect = get_dnplayer_render_rect()
        if render_rect:
            return render_rect, "dnplayer RenderWindow (Android-only)", []

        client = get_dnplayer_client_rect()
        if client:
            return (
                client,
                "dnplayer client area (fallback: Ld9BoxHeadless no visible window, Android composited into dnplayer)",
                [],
            )
    return None, "no visible window found", wins


# ---------------------------------------------------------------------------
# 8. 用 dxcam 截取指定屏幕区域
# ---------------------------------------------------------------------------
def capture_region(rect, output_color="RGB"):
    """截取指定屏幕区域，返回 numpy 数组（RGB 或 BGR），失败返回 None。"""
    left, top, right, bottom = rect
    # 裁剪到屏幕边界
    screen_w = win32api.GetSystemMetrics(0)
    screen_h = win32api.GetSystemMetrics(1)
    left = max(0, min(left, screen_w))
    top = max(0, min(top, screen_h))
    right = max(left, min(right, screen_w))
    bottom = max(top, min(bottom, screen_h))
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None

    camera = dxcam.create(output_idx=0, output_color=output_color)
    if camera is None:
        raise RuntimeError(
            "dxcam.create() failed: Desktop Duplication may not be supported"
            " (no display/GPU, or remote desktop/session in use)"
        )
    frame = camera.grab(region=(left, top, right, bottom))
    return frame


# ---------------------------------------------------------------------------
# 9. 保存 PNG
# ---------------------------------------------------------------------------
def save_png(frame, output_dir: str, process_name: str):
    """保存 numpy 数组为 PNG，返回输出路径。"""
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(process_name)[0]
    out_path = os.path.join(output_dir, f"{stem}.png")
    Image.fromarray(frame).save(out_path)
    return out_path
