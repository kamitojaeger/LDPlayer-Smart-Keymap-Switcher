#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LDPlayer 安卓原生分辨率截图 + 模板匹配 + 自动按键切换 (v9)

相比 v8 的主要变化：
  - 截图方案从 dxcam（Windows 端截图）改为 LDPlayer 内置截图
  - 截图始终为安卓原生分辨率 1920×1080，不受窗口缩放影响
  - 移除了 dxcam / pywin32 窗口坐标计算依赖

功能：
  1. 使用 LDPlayer 内置截图（Ctrl+0 热键）获取安卓原生分辨率画面
  2. 在截图右下角区域，对 driveSample.png / walkSample.png 做模板匹配
  3. 自动切换按键方案
  4. Toast 覆盖层提示

用法：
  python screenshot_ldplayer.py            # 循环监控模式
  python screenshot_ldplayer.py --once     # 单次截图 + 匹配
  python screenshot_ldplayer.py --match <png>  # 对已有图片做匹配
"""

import os
import sys
import time
import json
import ctypes
import argparse
import subprocess

# -- LDPlayer 原生截图模块 ---------------------------------------------------
from ld_screenshot import (
    find_ldplayer_window,
    capture_to_numpy,
    get_android_resolution,
    get_screenshot_dir,
)

# -- Toast 覆盖层 ------------------------------------------------------------
from toast_overlay import show_toast, extract_key_name, update_toast, destroy_toast

# ---- 外部依赖 --------------------------------------------------------------
try:
    import cv2
    import numpy as np
    from PIL import Image
except ImportError as e:
    sys.exit(
        f"[缺少依赖] {e}\n"
        f"请使用当前 Python 解释器安装所需依赖：\n"
        f"    {sys.executable} -m pip install -r requirements.txt\n"
        f"（依赖含 pillow / numpy / opencv-python-headless）"
    )

# ---- 输出目录 ---------------------------------------------------------------
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testScreenShots")

# ---- keymap_injector 路径 ---------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INJECTOR = os.path.join(SCRIPT_DIR, "hook_demo", "keymap_injector.exe")

# ---- 按键方案 .kmp 文件路径 ------------------------------------------------
DRIVE_KMP = r"F:\LDPlayer\LDPlayer14\vms\customizeConfigs\com.rockstargames.gtasa_1920x1080(Drive mode).kmp"
WALK_KMP  = r"F:\LDPlayer\LDPlayer14\vms\customizeConfigs\com.rockstargames.gtasa_1920x1080(walk mode).kmp"

# ---- 模板匹配配置 -----------------------------------------------------------
# 截图固定为安卓原生分辨率 1920×1080
ANDROID_W, ANDROID_H = 1920, 1080

# 图标在游戏画面中的参考位置（右下角区域）
# sample 图标距游戏区下边/右边各约 40px
ICON_MARGIN_BOTTOM = 40
ICON_MARGIN_RIGHT = 40
SEARCH_SLACK = 20                      # 搜索区域额外余量

DRIVE_SAMPLE = os.path.join(OUTPUT_DIR, "driveSample.png")
WALK_SAMPLE = os.path.join(OUTPUT_DIR, "walkSample.png")
MATCH_THRESHOLD = 0.75

# ---- 模板 mask 生成参数 ---------------------------------------------------
MASK_DARK_PERCENTILE = 22
MASK_BRIGHT_PERCENTILE = 82

_SAMPLE_MASK_CACHE = {}


# ---------------------------------------------------------------------------
def _get_sample_mask(sample_path: str):
    """返回 sample 的灰度图 + mask（uint8, 255=有效匹配区, 0=忽略）。"""
    if sample_path in _SAMPLE_MASK_CACHE:
        return _SAMPLE_MASK_CACHE[sample_path]

    gray = cv2.imread(sample_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"无法读取 sample: {sample_path}")

    flat = gray.ravel()
    dark_thresh = np.percentile(flat, MASK_DARK_PERCENTILE)
    bright_thresh = np.percentile(flat, MASK_BRIGHT_PERCENTILE)

    mask = np.zeros_like(gray, dtype=np.uint8)
    mask[gray <= dark_thresh] = 255
    mask[gray >= bright_thresh] = 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.dilate(mask, kernel, iterations=1)

    _SAMPLE_MASK_CACHE[sample_path] = (gray, mask)
    return gray, mask


# ---------------------------------------------------------------------------
def match_sample_in_corner(screenshot_bgr, sample_path: str):
    """
    在 screenshot_bgr 的右下角区域搜索 sample_path 对应的图标。
    截图分辨率为固定 1920×1080，无需缩放。

    返回:
        (max_val, global_loc, region_info, sample_size)
    """
    template, template_mask = _get_sample_mask(sample_path)
    th, tw = template.shape[:2]

    # 截图转灰度
    gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    # 右下角搜索区域
    right_pad = ICON_MARGIN_RIGHT + SEARCH_SLACK
    bottom_pad = ICON_MARGIN_BOTTOM + SEARCH_SLACK

    region_x = max(0, w - right_pad - tw)
    region_y = max(0, h - bottom_pad - th)
    region = gray[region_y:h, region_x:w]

    if region.shape[0] < th or region.shape[1] < tw:
        raise RuntimeError(
            f"搜索区域过小 region={region.shape[1]}x{region.shape[0]}, "
            f"sample={tw}x{th}"
        )

    try:
        result = cv2.matchTemplate(
            region, template,
            cv2.TM_CCOEFF_NORMED, mask=template_mask
        )
    except cv2.error:
        result = cv2.matchTemplate(
            region, template, cv2.TM_CCOEFF_NORMED
        )

    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    global_loc = (region_x + max_loc[0], region_y + max_loc[1])
    region_info = (region_x, region_y, w)
    return max_val, global_loc, region_info, (tw, th)


# ---------------------------------------------------------------------------
def match_drive_walk(screenshot_bgr):
    """同时匹配 drive 和 walk 两个 sample。"""
    results = {}
    for name, path in (("drive", DRIVE_SAMPLE), ("walk", WALK_SAMPLE)):
        if not os.path.exists(path):
            results[name] = {"val": 0.0, "loc": (0, 0),
                             "region_info": (0, 0, 0), "size": (0, 0)}
            continue
        val, loc, region_info, size = match_sample_in_corner(screenshot_bgr, path)
        results[name] = {"val": val, "loc": loc,
                         "region_info": region_info, "size": size}
    return results


# ---------------------------------------------------------------------------
def format_match_results_line(results: dict) -> str:
    """返回一行匹配结果文本。"""
    parts = []
    for name, info in sorted(results.items()):
        val = info["val"]
        status = "✓" if val >= MATCH_THRESHOLD else " "
        parts.append(f"{name}:{val:.4f}{status}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
def draw_debug_overlay(screenshot_bgr, results: dict, out_path: str):
    """绘制调试标注图：红框=搜索区域，绿框=最佳匹配位置。"""
    RED = (0, 0, 255)
    GREEN = (0, 255, 0)
    YELLOW = (0, 255, 255)

    debug = screenshot_bgr.copy()
    h, w = debug.shape[:2]

    for name, info in sorted(results.items()):
        region_info = info.get("region_info", (0, 0, 0))
        loc = info.get("loc", (0, 0))
        size = info.get("size", (0, 0))
        val = info.get("val", 0.0)

        if region_info == (0, 0, 0) or size == (0, 0):
            continue

        rx, ry, rr = region_info
        rh = h - ry
        rw = rr - rx
        stw, sth = size

        cv2.rectangle(debug, (rx, ry), (rx + rw - 1, ry + rh - 1), RED, 2)
        label = f"{name}_region"
        cv2.putText(debug, label, (rx + 4, ry + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, RED, 1)

        lx, ly = loc
        cv2.rectangle(debug, (lx, ly), (lx + stw, ly + sth), GREEN, 2)

        score_label = f"{name}:{val:.3f}"
        label_y = ly - 4 if ly > 15 else ly + sth + 16
        cv2.putText(debug, score_label, (lx, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, GREEN, 1)

    cv2.putText(debug, f"{w}x{h} (native Android)",
                (6, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, YELLOW, 1)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, debug)
    return out_path


# ---------------------------------------------------------------------------
def parse_kmp_mouse_drag_key(kmp_path: str):
    """解析 .kmp 文件，返回 ClassMouseDrag 绑定的虚拟键码。"""
    try:
        with open(kmp_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for mapping in data.get('keyboardMappings', []):
            if mapping.get('class') == 'ClassMouseDrag':
                return mapping['data']['key']
    except Exception:
        pass
    return None


def send_key_vk(vk_code: int):
    """模拟一次按键（keybd_event）。"""
    user32 = ctypes.windll.user32
    user32.keybd_event(vk_code, 0, 0, 0)
    user32.keybd_event(vk_code, 0, 2, 0)


def _sleep_with_toast(duration: float):
    """分片 sleep，处理 Toast 事件循环。"""
    end = time.time() + duration
    while time.time() < end:
        remaining = end - time.time()
        sleep_ms = min(remaining, 0.05)
        if sleep_ms > 0:
            time.sleep(sleep_ms)
        update_toast()


# ---------------------------------------------------------------------------
def run_monitor_loop(no_debug=False, parent_hwnd=None):
    """持续截图+匹配+自动切换按键方案，直到 Ctrl+C。"""
    i = 0
    current_mode = "walk"
    # 截图间隔（秒），内置截图较慢，需要更长的间隔
    CAPTURE_INTERVAL = 0.8

    print(f"[监控] 开始循环监控 (初始状态: {current_mode}, "
          f"间隔: {CAPTURE_INTERVAL}s, Ctrl+C 停止)")
    print(f"[监控] 截图方案: LDPlayer 内置截图, 分辨率: {ANDROID_W}x{ANDROID_H}")
    print()

    try:
        while True:
            i += 1
            t0 = time.perf_counter()

            # 使用 LDPlayer 内置截图（始终 1920×1080）
            screenshot_bgr = capture_to_numpy(parent_hwnd)
            if screenshot_bgr is None:
                print(f"[#{i}] 截图失败，跳过")
                _sleep_with_toast(CAPTURE_INTERVAL)
                continue

            h, w = screenshot_bgr.shape[:2]

            # 保存最新截图
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            latest_path = os.path.join(OUTPUT_DIR, "latest.png")
            cv2.imwrite(latest_path, screenshot_bgr)

            # 模板匹配
            results = match_drive_walk(screenshot_bgr)

            elapsed_ms = (time.perf_counter() - t0) * 1000
            line = format_match_results_line(results)
            prefix = f"[#{i:>4d}] {elapsed_ms:6.1f}ms |"

            # 状态判断
            best_name = None
            best_val = -1.0
            for name in ("drive", "walk"):
                val = results[name]["val"]
                if val >= MATCH_THRESHOLD and val > best_val:
                    best_val = val
                    best_name = name

            switch_info = ""
            if best_name is not None and best_name != current_mode:
                kmp = DRIVE_KMP if best_name == "drive" else WALK_KMP
                if os.path.exists(kmp):
                    switch_info = f" [切换] {current_mode} -> {best_name}"
                    key_name = extract_key_name(kmp)
                    print(f"[切换] Toast: {key_name!r}", flush=True)
                    show_toast(key_name, parent_hwnd)
                    try:
                        subprocess.run(
                            [INJECTOR, kmp],
                            capture_output=True, timeout=10,
                        )
                        current_mode = best_name
                        mouse_key = parse_kmp_mouse_drag_key(kmp)
                        if mouse_key is not None:
                            send_key_vk(mouse_key)
                            switch_info += f" [MouseDrag] VK={mouse_key}"
                    except FileNotFoundError:
                        switch_info += " (未找到 keymap_injector.exe)"
                else:
                    switch_info = f" [跳过] .kmp 不存在"

            print(f"{prefix} {line} {switch_info}")

            # 调试标注图
            if not no_debug:
                debug_path = os.path.join(OUTPUT_DIR, "latest_debug.png")
                draw_debug_overlay(screenshot_bgr, results, debug_path)

            # 等待下次截图（考虑截图耗时）
            remaining = CAPTURE_INTERVAL - elapsed_ms / 1000
            if remaining > 0:
                _sleep_with_toast(remaining)

    except KeyboardInterrupt:
        destroy_toast()
        print(f"\n[监控] 已停止，共 {i} 轮。最终状态: {current_mode}")


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="LDPlayer 安卓原生截图 + 模板匹配 + 自动按键切换"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="单次截图 + 匹配，不进入循环"
    )
    parser.add_argument(
        "--match", metavar="PATH",
        help="对已有 PNG 图片进行模板匹配"
    )
    parser.add_argument(
        "--no-debug", action="store_true",
        help="不生成调试标注图"
    )
    args = parser.parse_args()

    # 对已有图片匹配
    if args.match:
        screenshot = cv2.imread(args.match, cv2.IMREAD_COLOR)
        if screenshot is None:
            raise RuntimeError(f"无法读取图片: {args.match}")
        h, w = screenshot.shape[:2]
        print(f"[匹配] 图片: {args.match} ({w}x{h})")
        results = match_drive_walk(screenshot)
        print(f"[匹配] {format_match_results_line(results)}")

        if not args.no_debug:
            base, ext = os.path.splitext(args.match)
            debug_path = f"{base}_debug{ext}"
            draw_debug_overlay(screenshot, results, debug_path)
            print(f"[调试] 标注图: {debug_path}")
        return

    # 查找 LDPlayer 窗口
    hwnd = find_ldplayer_window()
    if not hwnd:
        raise RuntimeError(
            "未找到 LDPlayer 窗口。请确保模拟器正在运行。"
        )
    print(f"[窗口] LDPlayer HWND = 0x{hwnd:08X}")

    # keymap_injector 初始化
    if os.path.exists(INJECTOR):
        print("[初始化] keymap_injector.exe init...")
        try:
            result = subprocess.run(
                [INJECTOR, "init"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                print(f"[警告] init 返回码 {result.returncode}")
            else:
                print("[初始化] init 完成")
        except subprocess.TimeoutExpired:
            print("[警告] init 超时")
        except FileNotFoundError:
            print(f"[警告] 未找到 {INJECTOR}")
    else:
        print(f"[警告] 未找到 keymap_injector.exe")

    if args.once:
        # 单次截图
        print("[截图] 正在获取安卓原生分辨率截图...")
        screenshot_bgr = capture_to_numpy(hwnd)
        if screenshot_bgr is None:
            raise RuntimeError("截图失败")
        h, w = screenshot_bgr.shape[:2]
        print(f"[截图] 分辨率: {w}x{h}")

        latest_path = os.path.join(OUTPUT_DIR, "latest.png")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        cv2.imwrite(latest_path, screenshot_bgr)
        print(f"[截图] 已保存: {latest_path}")

        results = match_drive_walk(screenshot_bgr)
        print(f"[匹配] {format_match_results_line(results)}")

        if not args.no_debug:
            debug_path = os.path.join(OUTPUT_DIR, "latest_debug.png")
            draw_debug_overlay(screenshot_bgr, results, debug_path)
            print(f"[调试] 标注图: {debug_path}")
    else:
        # 循环监控
        run_monitor_loop(no_debug=args.no_debug, parent_hwnd=hwnd)


if __name__ == "__main__":
    main()
