#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LDPlayer 版本检测 — 自动发现安装路径 + 匹配版本偏移

职责：
  - 从注册表 / 常见路径 / 运行进程发现 LDPlayer 安装目录
  - 读取 ldplayer_versions.json 匹配 dnplycore.dll 到已知版本
  - 提供 LDPlayerInfo 供 injector 使用
"""

import os
import json
import ctypes
from typing import Optional

# ---- LDPlayer 常见安装路径与注册表键 ----
_COMMON_PATHS = [
    r"C:\LDPlayer\LDPlayer9",
    r"C:\LDPlayer\LDPlayer14",
    r"C:\Program Files\ldplayer9box",
    r"C:\Program Files (x86)\ldplayer9box",
    r"D:\LDPlayer\LDPlayer9",
    r"D:\LDPlayer\LDPlayer14",
]

_REG_PATHS = [
    (0x80000001, r"Software\XuanZhi\LDPlayer"),           # HKCU
    (0x80000002, r"SOFTWARE\XuanZhi\LDPlayer"),           # HKLM
    (0x80000001, r"Software\ldplayer9box"),                # HKCU (alt)
    (0x80000002, r"SOFTWARE\ldplayer9box"),                # HKLM (alt)
    (0x80000001, r"Software\XuanZhi\LDPlayer9"),           # HKCU LD9
    (0x80000002, r"SOFTWARE\XuanZhi\LDPlayer9"),           # HKLM LD9
]

_REG_VALUE_NAMES = ["InstallDir", "InstallPath", "Path", ""]


class LDPlayerInfo:
    """LDPlayer 安装信息。"""

    def __init__(self, install_path: str, version_id: str,
                 version_name: str, offsets: dict):
        self.install_path = install_path
        self.version_id = version_id
        self.version_name = version_name
        self.offsets = offsets          # {hook_rva, func_rva, return_rva}
        self.dll_path = os.path.join(install_path, "dnplycore.dll")

    def __repr__(self):
        return (f"LDPlayerInfo({self.version_id}, {self.install_path}, "
                f"offsets={self.offsets})")


# ---------------------------------------------------------------------------
# 1. 从注册表查找 LDPlayer 安装路径
# ---------------------------------------------------------------------------
def _read_reg_string(hkey_root: int, subkey: str, value_name: str) -> Optional[str]:
    """读取注册表字符串值，失败返回 None。"""
    import winreg
    try:
        with winreg.OpenKey(hkey_root, subkey) as key:
            value, _ = winreg.QueryValueEx(key, value_name if value_name else None)
            if isinstance(value, str) and os.path.isdir(value):
                return value
    except (OSError, FileNotFoundError):
        pass
    return None


def find_install_from_registry() -> Optional[str]:
    """从注册表搜索 LDPlayer 安装路径。"""
    for hkey_root, subkey in _REG_PATHS:
        for val_name in _REG_VALUE_NAMES:
            path = _read_reg_string(hkey_root, subkey, val_name)
            if path and os.path.isdir(path):
                return path
    return None


# ---------------------------------------------------------------------------
# 2. 从常见路径查找
# ---------------------------------------------------------------------------
def find_install_from_common_paths() -> Optional[str]:
    """检查常见安装路径。"""
    for path in _COMMON_PATHS:
        if os.path.isdir(path):
            # 验证：目录下应有 dnplayer.exe
            if os.path.isfile(os.path.join(path, "dnplayer.exe")):
                return path
    return None


# ---------------------------------------------------------------------------
# 3. 从运行中的 dnplayer.exe 进程查找
# ---------------------------------------------------------------------------
def find_install_from_running_process() -> Optional[str]:
    """通过运行中的 dnplayer.exe 进程获取安装路径。"""
    import ctypes.wintypes

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    # 枚举所有窗口找 dnplayer.exe
    result = [None]

    def enum_cb(hwnd, _):
        try:
            import win32process
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
            )
            if not handle:
                return True
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_uint(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                name = os.path.basename(buf.value).lower()
                if name == "dnplayer.exe":
                    result[0] = os.path.dirname(buf.value)
                    return False  # 找到即停
            kernel32.CloseHandle(handle)
        except Exception:
            pass
        return True

    try:
        import win32gui
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int)
        cb = WNDENUMPROC(enum_cb)
        user32.EnumWindows(cb, 0)
    except ImportError:
        pass

    return result[0]


# ---------------------------------------------------------------------------
# 4. 自动发现 LDPlayer 安装路径（综合策略）
# ---------------------------------------------------------------------------
def detect_install_path() -> Optional[str]:
    """自动发现 LDPlayer 安装路径。

       优先级: 运行进程 > 注册表 > 常见路径
    """
    # 1) 运行中的进程（最可靠）
    path = find_install_from_running_process()
    if path:
        return path

    # 2) 注册表
    path = find_install_from_registry()
    if path:
        return path

    # 3) 常见路径
    path = find_install_from_common_paths()
    if path:
        return path

    return None


# ---------------------------------------------------------------------------
# 5. 匹配 dnplycore.dll 到已知版本
# ---------------------------------------------------------------------------
def _match_version(dll_path: str, versions: list,
                   install_path: str = None) -> Optional[dict]:
    """根据 dnplycore.dll 的文件特征匹配已知版本。

       当前策略：
         - 若版本条目定义了 dll_size，检查文件大小
         - 若版本条目定义了 signature，在 DLL 中搜索特征字节
         - 两者都匹配才返回，至少一个匹配且另一个为 null 也返回
         - 多个版本签名相同时，优先选择编号匹配安装路径的版本（如路径含"14"→ld14）

       返回匹配的版本条目 dict，未匹配返回 None。
    """
    if not os.path.isfile(dll_path):
        return None

    file_size = os.path.getsize(dll_path)

    candidates = []
    for ver in versions:
        detection = ver.get("detection", {})
        expected_size = detection.get("dll_size")
        signature_hex = detection.get("signature")

        # 检查文件大小
        if expected_size is not None and file_size != expected_size:
            continue

        # 检查特征字节
        if signature_hex:
            sig_bytes = bytes.fromhex(signature_hex.replace(" ", ""))
            try:
                with open(dll_path, "rb") as f:
                    data = f.read()
                if sig_bytes not in data:
                    continue
            except Exception:
                continue

        candidates.append(ver)

    if not candidates:
        return None

    # 多个候选时，优先选择版本编号匹配安装路径的
    if len(candidates) > 1 and install_path:
        path_lower = install_path.lower()
        for ver in candidates:
            ver_num = ''.join(c for c in ver['id'] if c.isdigit())
            if ver_num:
                for hint in (f"ldplayer{ver_num}", f"ldplayer {ver_num}",
                             f"ld{ver_num}", ver_num):
                    if hint in path_lower:
                        return ver

    return candidates[0]


def detect_version(install_path: str,
                   versions_json_path: str = None) -> Optional[LDPlayerInfo]:
    """检测 LDPlayer 版本并返回 LDPlayerInfo。

    参数：
        install_path:      LDPlayer 安装目录
        versions_json_path: ldplayer_versions.json 路径，None 使用默认路径

    返回：
        LDPlayerInfo，未找到匹配版本返回 None
    """
    if versions_json_path is None:
        # 兼容 PyInstaller 打包：frozen 时用 exe 所在目录，开发环境用项目根
        import sys as _sys
        if getattr(_sys, 'frozen', False):
            base = os.path.dirname(_sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))
        versions_json_path = os.path.join(base, "config",
                                          "ldplayer_versions.json")

    if not os.path.isfile(versions_json_path):
        return None

    with open(versions_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    versions = data.get("supported_versions", [])
    dll_path = os.path.join(install_path, "dnplycore.dll")

    matched = _match_version(dll_path, versions, install_path)
    if matched:
        return LDPlayerInfo(
            install_path=install_path,
            version_id=matched["id"],
            version_name=matched["name"],
            offsets=matched["offsets"],
        )

    return None


# ---------------------------------------------------------------------------
# 6. 一键检测（安装路径 + 版本）
# ---------------------------------------------------------------------------
def auto_detect(versions_json_path: str = None) -> Optional[LDPlayerInfo]:
    """自动发现 LDPlayer 安装路径并检测版本。

       返回 LDPlayerInfo，失败返回 None。
    """
    path = detect_install_path()
    if not path:
        return None
    return detect_version(path, versions_json_path)
