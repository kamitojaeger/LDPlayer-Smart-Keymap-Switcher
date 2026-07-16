#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ADB 截图 demo

功能：
  1. 确认存在且仅存在一个 LDPlayer 实例（dnplayer.exe）
  2. 运行 adb devices，确认存在且仅存在一个在线 adb 设备
  3. 每轮用 adb exec-out screencap -p 截图，保存到 testScreenShots/
  4. 输出每轮截图耗时（毫秒），便于与 dxcam 对比

用法：
  python adb_screenshot_demo.py
  python adb_screenshot_demo.py --count 5   # 只截 5 张

要求：
  本脚本使用项目根目录下的 adb.exe (D:/LD_DEV/LDPlayer_Auto_Input_Switcher/adb.exe)
"""

import os
import sys
import time
import ctypes
import subprocess
import argparse

# ---- 路径配置 --------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ADB = os.path.join(SCRIPT_DIR, "adb.exe")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "testScreenShots")

EMULATOR_PROCESS = "dnplayer.exe"

_KERNEL32 = ctypes.windll.kernel32


# ---------------------------------------------------------------------------
# 1. 通过 PID 取进程名（跨 32/64 位，使用 QueryFullProcessImageNameW）
# ---------------------------------------------------------------------------
def get_process_name(pid: int):
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    handle = _KERNEL32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_uint(1024)
        if _KERNEL32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return None
    finally:
        _KERNEL32.CloseHandle(handle)


# ---------------------------------------------------------------------------
# 2. 统计 dnplayer.exe 不同 PID 数量
# ---------------------------------------------------------------------------
def count_dnplayer_instances():
    try:
        import win32gui
        import win32process
    except ImportError as e:
        sys.exit(f"[缺少依赖] {e}，请安装 pywin32: pip install pywin32")

    target = EMULATOR_PROCESS.lower()
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
# 3. 执行 adb 命令并返回 (stdout, stderr, returncode)
# ---------------------------------------------------------------------------
def run_adb(args):
    if not os.path.exists(ADB):
        raise RuntimeError(f"adb.exe 未找到: {ADB}")
    cmd = [ADB] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=False,  # 保留二进制输出，screencap 返回 PNG 字节流
        timeout=15,
    )
    return result


# ---------------------------------------------------------------------------
# 4. 解析 adb devices，返回在线设备列表
# ---------------------------------------------------------------------------
def get_online_devices():
    """返回 [(device_id, status), ...]，status 为 'device' 表示在线。"""
    result = run_adb(["devices"])
    stdout_text = result.stdout.decode("utf-8", errors="ignore")

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"adb devices 失败: {stderr_text}")

    devices = []
    for line in stdout_text.strip().splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            device_id, status = parts[0], parts[1]
            if status == "device":
                devices.append((device_id, status))
    return devices


# ---------------------------------------------------------------------------
# 5. 用 adb 截图并保存为 PNG
# ---------------------------------------------------------------------------
def adb_screenshot(output_path: str):
    """通过 adb exec-out screencap -p 截图，返回耗时（秒）。"""
    t0 = time.perf_counter()

    # 使用 exec-out 直接输出 PNG 字节流，避免设备上写临时文件再 pull
    result = run_adb(["exec-out", "screencap", "-p"])

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"adb screencap 失败: {stderr_text}")
    if not result.stdout:
        raise RuntimeError("adb screencap 返回空数据")

    # 写入文件
    with open(output_path, "wb") as f:
        f.write(result.stdout)

    elapsed = time.perf_counter() - t0
    return elapsed


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="ADB 截图 demo")
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="指定截图轮数，默认无限循环 (Ctrl+C 停止)",
    )
    args = parser.parse_args()

    # ---- 1. LDPlayer 实例守卫 ----
    dn_count = count_dnplayer_instances()
    if dn_count == 0:
        raise RuntimeError(
            "未检测到 LDPlayer 在运行（找不到 dnplayer.exe 进程）。"
            "请先启动模拟器后再运行本 demo。"
        )
    if dn_count > 1:
        raise RuntimeError(
            f"检测到 {dn_count} 个 LDPlayer 实例，"
            "无法确定截图目标。请只保留一个模拟器实例。"
        )
    print(f"[实例守卫] 检测到 {dn_count} 个 dnplayer.exe 实例 ✓")

    # ---- 2. adb 设备检查 ----
    devices = get_online_devices()
    if len(devices) == 0:
        raise RuntimeError(
            "未检测到在线的 adb 设备。\n"
            "请确认 LDPlayer 已启用 adb 调试，或 adb 服务正在运行。"
        )
    if len(devices) > 1:
        raise RuntimeError(
            f"检测到 {len(devices)} 个在线 adb 设备，无法确定目标：\n"
            + "\n".join(f"  - {d[0]} {d[1]}" for d in devices)
        )
    device_id = devices[0][0]
    print(f"[adb 设备] 检测到 1 个在线设备: {device_id} ✓")

    # 准备输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"[开始] adb 截图，保存到 {OUTPUT_DIR}")
    print(f"        使用 adb: {ADB}")
    print("        按 Ctrl+C 停止\n")

    # ---- 3. 循环截图 ----
    i = 0
    try:
        while True:
            i += 1
            output_path = os.path.join(OUTPUT_DIR, "Ld9BoxHeadless.png")

            try:
                elapsed = adb_screenshot(output_path)
                elapsed_ms = elapsed * 1000
                size_kb = os.path.getsize(output_path) / 1024

                print(
                    f"[# {i:>3d}] 耗时 {elapsed_ms:6.1f} ms | "
                    f"文件大小 {size_kb:7.1f} KB"
                )
            except Exception as e:
                print(f"[# {i:>3d}] 截图失败: {e}")

            if args.count is not None and i >= args.count:
                break

            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n[停止] 共执行 {i} 轮 adb 截图。")


if __name__ == "__main__":
    main()
