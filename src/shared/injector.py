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
