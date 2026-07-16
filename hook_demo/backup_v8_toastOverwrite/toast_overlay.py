#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Toast 覆盖层 —— 在 LDPlayer 窗口上显示按键切换提示

解决 README 中"提示不一致"缺陷：
  安卓系统弹出切换提示与实际键位不符。
  本模块在 keymap 切换后，在 LDPlayer 窗口中上位置显示自定义 Toast，
  文案为 "Switch to <按键名称>"，1 秒后自动消失。

用法:
    from toast_overlay import show_toast, extract_key_name

    key_name = extract_key_name("com.xxx(Drive mode).kmp")  # → "Drive mode"
    show_toast(key_name, parent_hwnd)
"""

import os
import re
import sys
import time
import ctypes
from ctypes import wintypes
import tkinter as tk
import tkinter.font as tkfont

# ---------------------------------------------------------------------------
# Win32 API 常量 & 绑定
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


# ---------------------------------------------------------------------------
# 提取按键名称
# ---------------------------------------------------------------------------
def extract_key_name(kmp_path: str) -> str:
    """从 .kmp 文件名提取括号内的描述文本。"""
    basename = os.path.basename(kmp_path)
    match = re.search(r'\(([^)]+)\)', basename)
    if match:
        return match.group(1)
    return os.path.splitext(basename)[0]


# ---------------------------------------------------------------------------
# ToastOverlay 类
# ---------------------------------------------------------------------------
class ToastOverlay:
    """在指定窗口上显示半透明 Toast 弹窗。"""

    FONT_FAMILY = "Microsoft YaHei"
    FONT_SIZE = 24
    FONT_WEIGHT = "bold"
    BG_COLOR = "#2D2D2D"
    FG_COLOR = "#FFFFFF"
    ALPHA = 0.92
    DURATION = 3.0
    Y_OFFSET = 80
    PAD_X = 35
    PAD_Y = 18

    def __init__(self):
        self._win = None
        self._label = None

    # ------------------------------------------------------------------
    def show(self, key_name: str, parent_hwnd: int):
        """在 parent_hwnd 窗口中上位置创建并显示 Toast。"""
        self.destroy()

        print(f"[Toast] show() 被调用 | key_name={key_name!r} | parent_hwnd={parent_hwnd}",
              flush=True)

        # -- 获取父窗口位置 & 尺寸 --
        rect = wintypes.RECT()
        if parent_hwnd and user32.IsWindow(parent_hwnd):
            user32.GetWindowRect(parent_hwnd, ctypes.byref(rect))
            print(f"[Toast] 父窗口: left={rect.left} top={rect.top} "
                  f"right={rect.right} bottom={rect.bottom}", flush=True)
        else:
            rect.left = 0
            rect.top = 0
            rect.right = user32.GetSystemMetrics(0)
            rect.bottom = user32.GetSystemMetrics(1)
            print(f"[Toast] 无有效父窗口，回退到屏幕: {rect.right}x{rect.bottom}",
                  flush=True)
        parent_x, parent_y = rect.left, rect.top
        parent_w = rect.right - rect.left

        # -- 创建无边框 Tk 窗口 --
        self._win = tk.Tk()
        self._win.overrideredirect(True)
        self._win.attributes('-alpha', self.ALPHA)
        self._win.attributes('-topmost', True)
        self._win.configure(bg=self.BG_COLOR)

        # -- 获取 HWND（使用 winfo_id，比 frame() 更可靠）--
        # winfo_id() 返回整数 HWND
        self._win.update_idletasks()  # 确保 HWND 已分配
        hwnd = self._win.winfo_id()
        print(f"[Toast] Tk 窗口 HWND = {hwnd} (0x{hwnd:08X})", flush=True)

        # -- 设置 Win32 扩展样式（不加 WS_EX_LAYERED，交由 tkinter alpha 管理）--
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style |= (WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

        # -- 构造文本 --
        text = f"Switch to {key_name}"

        # -- 创建标签 --
        self._label = tk.Label(
            self._win,
            text=text,
            font=(self.FONT_FAMILY, self.FONT_SIZE, self.FONT_WEIGHT),
            fg=self.FG_COLOR,
            bg=self.BG_COLOR,
            padx=self.PAD_X,
            pady=self.PAD_Y,
            anchor='center',
        )
        self._label.pack()

        # -- 测量文本尺寸 --
        self._win.update_idletasks()
        label_w = self._label.winfo_reqwidth()
        label_h = self._label.winfo_reqheight()

        # -- 计算位置 --
        toast_w = min(label_w, parent_w)
        toast_h = label_h
        toast_x = parent_x + max((parent_w - toast_w) // 2, 0)
        toast_y = parent_y + self.Y_OFFSET

        # -- 溢出截断 --
        if label_w > parent_w:
            f = tkfont.Font(family=self.FONT_FAMILY, size=self.FONT_SIZE,
                           weight=self.FONT_WEIGHT)
            max_text_w = parent_w - self.PAD_X * 2
            truncated = text
            while (f.measure(truncated + "...") > max_text_w
                   and len(truncated) > 5):
                truncated = truncated[:-1]
            self._label.configure(text=truncated + "...")

        # -- 设定窗口位置 & 尺寸 --
        self._win.geometry(f"{toast_w}x{toast_h}+{toast_x}+{toast_y}")
        print(f"[Toast] 窗口 geo: {toast_w}x{toast_h}+{toast_x}+{toast_y}",
              flush=True)

        # -- 强制置顶（多种方式）--
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST,
            toast_x, toast_y, toast_w, toast_h,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        # 保险：BringWindowToTop
        user32.BringWindowToTop(hwnd)

        # -- 1 秒后自毁 --
        self._win.after(int(self.DURATION * 1000), self._on_timeout)

        # -- 立即渲染 --
        self._win.update()
        print(f"[Toast] 窗口已创建并渲染，将在 {self.DURATION}s 后消失", flush=True)

    # ------------------------------------------------------------------
    def _on_timeout(self):
        """定时器回调：销毁窗口。"""
        print("[Toast] 定时器触发 → 销毁窗口", flush=True)
        self.destroy()

    # ------------------------------------------------------------------
    def update(self):
        """处理挂起的 tkinter 事件，并保持窗口置顶。"""
        win = self._win  # 保存局部引用，防止 after 回调中途置 None
        if win:
            try:
                win.update()
                # 每次 update 时重新强制置顶
                hwnd = win.winfo_id()
                user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                )
            except tk.TclError:
                self._win = None
                self._label = None

    # ------------------------------------------------------------------
    def destroy(self):
        """销毁 Toast 窗口。"""
        if self._win is not None:
            try:
                self._win.destroy()
            except tk.TclError:
                pass
            self._win = None
            self._label = None

    # ------------------------------------------------------------------
    @property
    def alive(self) -> bool:
        return self._win is not None


# ---------------------------------------------------------------------------
# 模块级便利函数
# ---------------------------------------------------------------------------
_toast: ToastOverlay | None = None


def show_toast(key_name: str, parent_hwnd: int):
    """显示 Toast 覆盖层。"""
    global _toast
    print(f"[Toast] show_toast() 入口 | key_name={key_name!r} | hwnd={parent_hwnd}",
          flush=True)
    if _toast is None:
        _toast = ToastOverlay()
    _toast.show(key_name, parent_hwnd)


def update_toast():
    """更新 Toast 事件循环。"""
    global _toast
    if _toast is not None:
        _toast.update()


def destroy_toast():
    """销毁当前 Toast。"""
    global _toast
    if _toast is not None:
        _toast.destroy()
        _toast = None
