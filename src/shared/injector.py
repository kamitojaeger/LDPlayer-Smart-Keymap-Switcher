#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
注入器封装 — keymap_injector.exe 的 Python 接口

职责：
  - 封装子进程调用：init / switch / status
  - 解析 .kmp 中的 ClassMouseDrag key
  - 通过 keybd_event 发送虚拟键（绕过注入过滤）
"""

import os
import json
import ctypes
import subprocess
import sys
import threading
import time
from typing import Optional

# PyInstaller/Windows: 抑制 subprocess 弹出 CMD 窗口
_SUBPROCESS_KWARGS = {}
if sys.platform == "win32":
    _SUBPROCESS_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW


class Injector:
    """keymap_injector.exe 的 Python 封装。

    用法:
        inj = Injector("dist/keymap_injector.exe")
        if inj.init():
            inj.switch("games/gtasa/keymaps/drive_mode.kmp")
            inj.send_mouse_drag_key(17)  # Ctrl
    """

    def __init__(self, injector_path: str, dll_path: str = None):
        """
        参数：
            injector_path: keymap_injector.exe 路径
            dll_path:      keymap_hook.dll 路径（None 时自动推断同目录）
        """
        self._injector = injector_path
        if dll_path is None:
            dll_dir = os.path.dirname(os.path.abspath(injector_path))
            self._dll = os.path.join(dll_dir, "keymap_hook.dll")
        else:
            self._dll = dll_path

    @property
    def injector_path(self) -> str:
        return self._injector

    @property
    def dll_path(self) -> str:
        return self._dll

    def init(self) -> bool:
        """预初始化：keymap_injector.exe init。返回是否成功。"""
        if not os.path.exists(self._injector):
            print(f"[Injector] Not found: {self._injector}")
            return False
        try:
            result = subprocess.run(
                [self._injector, "init"],
                capture_output=True, text=True, timeout=10,
                **_SUBPROCESS_KWARGS,
            )
            if result.returncode != 0:
                stderr_tail = result.stderr.strip()[-200:] if result.stderr else ""
                print(f"[Injector] init exit code {result.returncode}")
                if stderr_tail:
                    print(f"           {stderr_tail}")
                return False
            print("[Injector] init completed")
            return True
        except subprocess.TimeoutExpired:
            print("[Injector] init timeout (>10s)")
            return False
        except FileNotFoundError:
            print(f"[Injector] File not found: {self._injector}")
            return False

    def switch(self, kmp_path: str) -> bool:
        """切换按键方案：keymap_injector.exe <kmp_path>。返回是否成功。"""
        if not os.path.exists(kmp_path):
            print(f"[Injector] .kmp not found: {kmp_path}")
            return False
        if not os.path.exists(self._injector):
            print(f"[Injector] Injector not found: {self._injector}")
            return False
        try:
            result = subprocess.run(
                [self._injector, kmp_path],
                capture_output=True, timeout=10,
                **_SUBPROCESS_KWARGS,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print(f"[Injector] switch timeout: {os.path.basename(kmp_path)}")
            return False
        except FileNotFoundError:
            print(f"[Injector] File not found: {self._injector}")
            return False

    def status(self) -> Optional[dict]:
        """获取诊断信息：keymap_injector.exe --status。"""
        if not os.path.exists(self._injector):
            return None
        try:
            result = subprocess.run(
                [self._injector, "--status"],
                capture_output=True, text=True, timeout=10,
                **_SUBPROCESS_KWARGS,
            )
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw": result.stdout}
        except Exception:
            return None

    @staticmethod
    def parse_kmp_disc_left_key(kmp_path: str) -> Optional[int]:
        """解析 .kmp 中 ClassKeyboardDisc 的 leftKey。

        ClassKeyboardDisc = LDPlayer 方向盘，只有含该 class 的 .kmp 切换时
        才可能触发方向键残留 bug。取其 leftKey 在切换后 tap 一次释放状态。
        返回虚拟键码，无 ClassKeyboardDisc 则返回 None。
        """
        try:
            with open(kmp_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return None

        for m in data.get('keyboardMappings', []):
            if m.get('class') == 'ClassKeyboardDisc':
                lk = m.get('data', {}).get('leftKey')
                if lk is not None:
                    return lk
        return None

    @staticmethod
    def parse_kmp_mouse_drag_key(kmp_path: str) -> Optional[int]:
        """解析 .kmp 文件中的 ClassMouseDrag key。

           返回虚拟键码（int），无则返回 None。
        """
        try:
            with open(kmp_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for mapping in data.get('keyboardMappings', []):
                if mapping.get('class') == 'ClassMouseDrag':
                    return mapping['data']['key']
        except Exception:
            pass
        return None

    @staticmethod
    def send_mouse_drag_key(vk_code: int):
        """通过 keybd_event 发送虚拟键（down + up），绕过 LDPlayer 注入过滤。

           keybd_event 不设置 LLKHF_INJECTED 标志，比 SendInput 更适合此场景。
        """
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)           # down
        user32.keybd_event(vk_code, 0, 2, 0)           # up (KEYEVENTF_KEYUP)

    @staticmethod
    def is_mouse_captured() -> bool:
        """检测鼠标是否被 LDPlayer 捕获（光标隐藏 = 射击视角中）。"""
        class _CI(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("flags", ctypes.c_uint),
                        ("hCursor", ctypes.c_void_p), ("ptScreenPos", ctypes.c_long * 2)]
        ci = _CI()
        ci.cbSize = ctypes.sizeof(_CI)
        ctypes.windll.user32.GetCursorInfo(ctypes.byref(ci))
        return ci.flags == 0  # 0 = hidden = captured

    @staticmethod
    def release_held_keys():
        """扫描并释放所有当前按下的按键（keybd_event KEYUP）。

        在键位方案切换前调用，防止切换后物理按住不放的按键残留。
        全量扫描 VK 0x01~0xFE，耗时 ~100μs，不影响切换延迟。
        """
        user32 = ctypes.windll.user32
        released = 0
        for vk in range(0x01, 0xFF):
            if user32.GetAsyncKeyState(vk) & 0x8000:
                user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
                released += 1
        return released


class KeyboardBlocker:
    """WH_KEYBOARD_LL 全局键盘拦截器。

    在上下文管理器中暂时阻断所有键盘输入，退出时自动恢复。

    用法:
        blocker = KeyboardBlocker(timeout_ms=300)
        with blocker:
            # 此处所有键盘输入被拦截
            injector.release_held_keys()
            injector.switch(kmp)
        # 退出 with 后键盘恢复正常

    安全机制: deactivate() 在 __exit__ 中保证被调用；额外有 timeout_ms 硬超时。
    """

    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_KEYUP   = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP   = 0x0105

    _HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int,
                                    ctypes.c_void_p, ctypes.c_void_p)

    def __init__(self, timeout_ms: int = 500):
        self._timeout_ms = timeout_ms
        self._hook_id = None
        self._stop = threading.Event()
        self._thread = None
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

        # 必须持有回调引用，否则被 GC 后 crash
        self._hook_cb = self._HOOKPROC(self._hook_proc)

    # ── public API ──────────────────────────────────────────────

    def __enter__(self):
        self.activate()
        return self

    def __exit__(self, *args):
        self.deactivate()
        return False

    def activate(self):
        """安装键盘钩子，启动消息循环线程。"""
        if self._hook_id is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._message_loop, daemon=True, name="KeyboardBlocker")
        self._thread.start()
        self._thread.join(timeout=1.0)  # 等钩子安装完成
        if self._hook_id is None:
            print("[KeyboardBlocker] WARNING: hook not installed after 1s — "
                  "keyboard NOT blocked")

    def deactivate(self):
        """卸载钩子，停止线程。幂等，可重复调用。"""
        if self._hook_id is None:
            return
        self._stop.set()
        # 向消息队列发送一条消息，唤醒 GetMessage 等待
        self._user32.PostThreadMessageW(
            self._thread.ident, 0x0400, 0, 0)  # WM_USER
        self._thread.join(timeout=2.0)
        self._hook_id = None

    @property
    def is_active(self) -> bool:
        return self._hook_id is not None

    # ── 内部 ────────────────────────────────────────────────────

    def _hook_proc(self, nCode, wParam, lParam):
        """钩子回调——在拦截线程上下文中执行。"""
        if nCode >= 0 and not self._stop.is_set():
            return 1  # 吃掉消息
        return self._user32.CallNextHookEx(
            None, nCode, wParam, lParam)

    def _message_loop(self):
        """独立线程中的消息循环（WH_KEYBOARD_LL 必需）。"""
        # hMod 必须为 NULL — Python 脚本的钩子过程在解释器内存中，不在 DLL
        self._hook_id = self._user32.SetWindowsHookExW(
            self.WH_KEYBOARD_LL, self._hook_cb, None, 0)

        if self._hook_id == 0:
            print("[KeyboardBlocker] SetWindowsHookExW failed")
            return

        # 硬超时：即使 _stop 未 set，也强制超时退出
        deadline = time.time() + (self._timeout_ms / 1000.0)

        class _MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_void_p), ("lParam", ctypes.c_void_p),
                ("time", ctypes.c_uint),
                ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long),
            ]

        msg = _MSG()
        while not self._stop.is_set() and time.time() < deadline:
            ret = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret in (0, -1):
                break
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

        self._user32.UnhookWindowsHookEx(self._hook_id)
        self._hook_id = None
