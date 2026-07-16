#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LDPlayer 安卓画面截图 + 右下角模板匹配 demo (dxcam + pywin32 + OpenCV)

功能：
  1. 实例守卫：统计 dnplayer.exe（模拟器主进程）数量
       - 0 个  -> 抛异常并停止（LDPlayer 未运行）
       - >1 个 -> 抛异常并停止（存在多个 LDPlayer 实例，无法确定目标）
  2. 仅截图 Ld9BoxHeadless.exe 对应的【安卓系统画面】，以进程名命名存 PNG 到 testScreenShots/
  3. 在截图右下角区域，对 driveSample.png / walkSample.png 做模板匹配并输出匹配率
  4. 调试模式：自动生成带红框(搜索区)+绿框(最佳匹配)标注的 debug PNG

模板匹配坐标系说明：
  参考截图分辨率 = 1980 × 1140（游戏区 1920×1080 + 上栏 60px + 右侧工具栏 60px）。
  sample 图是在 1920×1080 游戏区截图中截取的，图标距游戏区下边/右边各约 40px。
  在参考截图坐标系中：图标右下角 ≈ (1920-40, 60+1080-40) = (1880, 1100)，
  即距截图右边 ≈ 100px（40 游戏区右边距 + 60 工具栏），距截图下边 ≈ 40px。

用法：
  python screenshot_ldplayer.py            # 截一张图并做匹配
  python screenshot_ldplayer.py --list     # 只列出匹配到的窗口，不截图
  python screenshot_ldplayer.py --match <png>      # 对已有图片做匹配
  python screenshot_ldplayer.py --match <png> --no-debug  # 跳过 debug 图
"""

import os
import sys
import time
import json
import ctypes
import argparse
import subprocess

# ---- DPI 感知：必须在 import dxcam 之前设置，使其返回物理像素 ----
try:
    # PROCESS_PER_MONITOR_DPI_AWARE = 2
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ---- 外部依赖（缺失时给出明确安装提示，而非裸 ModuleNotFoundError）----
try:
    import win32gui
    import win32process
    import win32api
    import dxcam
    import cv2
    import numpy as np
    from PIL import Image
except ImportError as e:
    sys.exit(
        f"[缺少依赖] {e}\n"
        f"请使用当前 Python 解释器安装所需依赖：\n"
        f"    {sys.executable} -m pip install -r requirements.txt\n"
        f"（依赖含 dxcam / pywin32 / pillow / numpy / opencv-python-headless）"
    )

# ---- 模拟器主进程（用于实例守卫）------------------------------------------
EMULATOR_PROCESS = "dnplayer.exe"
# ---- 要截图的进程（安卓系统画面）------------------------------------------
TARGET_PROCESS = "Ld9BoxHeadless.exe"

# ---- 输出目录（与脚本同级的 testScreenShots）------------------------------
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testScreenShots")

# ---- keymap_injector 路径 ---------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INJECTOR = os.path.join(SCRIPT_DIR, "hook_demo", "keymap_injector.exe")

# ---- 按键方案 .kmp 文件路径 ------------------------------------------------
DRIVE_KMP = r"F:\LDPlayer\LDPlayer14\vms\customizeConfigs\com.rockstargames.gtasa_1920x1080(Drive mode).kmp"
WALK_KMP  = r"F:\LDPlayer\LDPlayer14\vms\customizeConfigs\com.rockstargames.gtasa_1920x1080(walk mode).kmp"

# ---- 模板匹配参考配置 ----------------------------------------------------
# 参考截图尺寸（游戏区 1920x1080 + 上栏 60 + 右侧工具栏 60）
REF_CAPTURE_W = 1920 + 60              # = 1980
REF_CAPTURE_H = 1080 + 60              # = 1140
REF_GAME_W = 1920
REF_GAME_H = 1080
REF_TITLEBAR_H = 60                    # 参考截图中上方窗口标题栏高度
REF_TOOLBAR_W = 60                     # 参考截图中右侧工具栏宽度
REF_MARGIN_BOTTOM = 40                 # sample 离游戏区下边的距离
REF_MARGIN_RIGHT = 40                  # sample 离游戏区右边的距离
SEARCH_SLACK = 20                      # 搜索区域额外余量（参考像素）
MATCH_THRESHOLD = 0.75                 # 认为匹配成功的阈值

# 图标在参考截图中的位置：
#   距截图右边 ≈ REF_MARGIN_RIGHT (工具栏宽度需实测微调)
#   距截图下边 ≈ REF_MARGIN_BOTTOM
REF_ICON_RIGHT_PAD = REF_MARGIN_RIGHT + REF_TOOLBAR_W  # 100 (参考值，实际由 REF_RIGHT_TRIM 微调)
REF_ICON_BOTTOM_PAD = REF_MARGIN_BOTTOM                 # 40

# ---- 微调参数（根据实际截图调试红框位置）----------------------------------
REF_BOTTOM_EXTRA = 13      # 红框需上移的像素数（参考像素，约 10~16）
REF_RIGHT_TRIM = 60        # 红框右边缩短的像素数（参考像素）

# ---- 模板 mask 生成参数 ---------------------------------------------------
# sample 图标由深色圆形底 + 白色图案 + 灰色背景构成。
# 灰色背景在非纯色游戏画面上会大幅拉低匹配率，因此只对 icon 特征区做匹配。
MASK_DARK_PERCENTILE = 22    # 低于此百分位的像素视为深色图标区域
MASK_BRIGHT_PERCENTILE = 82  # 高于此百分位的像素视为白色图标区域

DRIVE_SAMPLE = os.path.join(OUTPUT_DIR, "driveSample.png")
WALK_SAMPLE = os.path.join(OUTPUT_DIR, "walkSample.png")

# ---- sample mask 缓存（避免每次匹配都重新生成）-----------------------------
_SAMPLE_MASK_CACHE = {}

_KERNEL32 = ctypes.windll.kernel32


# ---------------------------------------------------------------------------
# 0. 为 sample 生成 feature mask（排除灰色背景，仅保留图标特征区）
# ---------------------------------------------------------------------------
def _get_sample_mask(sample_path: str):
    """返回 sample 的灰度图 + mask（uint8, 255=有效匹配区, 0=忽略）。
       首次调用时计算并缓存。"""
    if sample_path in _SAMPLE_MASK_CACHE:
        return _SAMPLE_MASK_CACHE[sample_path]

    gray = cv2.imread(sample_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"无法读取 sample: {sample_path}")

    # 用百分位阈值找出「深色圆形底」和「白色图标」区域
    flat = gray.ravel()
    dark_thresh = np.percentile(flat, MASK_DARK_PERCENTILE)
    bright_thresh = np.percentile(flat, MASK_BRIGHT_PERCENTILE)

    mask = np.zeros_like(gray, dtype=np.uint8)
    mask[gray <= dark_thresh] = 255
    mask[gray >= bright_thresh] = 255

    # 轻微膨胀，让 mask 覆盖边缘过渡像素
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.dilate(mask, kernel, iterations=1)

    _SAMPLE_MASK_CACHE[sample_path] = (gray, mask)
    return gray, mask


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
# 2. 统计某进程名的"不同 PID"数量（实例守卫用）
# ---------------------------------------------------------------------------
def count_processes(process_name: str):
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
# 3. 枚举窗口：按进程名找到所有"可见且有尺寸"的窗口，返回 (hwnd, rect, area)
# ---------------------------------------------------------------------------
def find_visible_windows(process_name: str):
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
            return  # 跳过零尺寸窗口
        found.append((hwnd, (left, top, right, bottom), width * height))

    win32gui.EnumWindows(_enum_cb, None)
    # 面积最大的窗口通常就是主窗口/渲染窗口
    found.sort(key=lambda x: x[2], reverse=True)
    return found


# ---------------------------------------------------------------------------
# 4. 取 dnplayer 主窗口的"客户端区域"屏幕坐标（去掉标题栏/边框，即安卓画面区）
# ---------------------------------------------------------------------------
def get_dnplayer_client_rect():
    dn = find_visible_windows(EMULATOR_PROCESS)
    if not dn:
        return None
    hwnd = dn[0][0]
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    # GetClientRect 返回相对客户区的 (0,0,w,h)
    sx, sy = win32gui.ClientToScreen(hwnd, (left, top))
    return (sx, sy, sx + right, sy + bottom)


# ---------------------------------------------------------------------------
# 5. 计算截图目标区域 + 来源说明
# ---------------------------------------------------------------------------
def resolve_capture_target(process_name: str):
    wins = find_visible_windows(process_name)
    if wins:
        hwnd, rect, _ = wins[0]
        return rect, "进程可见窗口", wins

    # 无可见窗口 -> 针对 headless 渲染进程回退到 dnplayer 客户端区域
    if process_name.lower() == "ld9boxheadless.exe":
        client = get_dnplayer_client_rect()
        if client:
            return (
                client,
                "dnplayer 客户端区域(回退: Ld9BoxHeadless 无可见窗口, 安卓画面已合成进 dnplayer)",
                [],
            )
    return None, "未找到可见窗口", wins


# ---------------------------------------------------------------------------
# 6. 用 dxcam 截取指定屏幕区域
# ---------------------------------------------------------------------------
def capture_region(rect, output_color="RGB"):
    left, top, right, bottom = rect
    # 裁剪到屏幕边界，避免 region 越界导致 dxcam 报错
    screen_w = win32api.GetSystemMetrics(0)  # SM_CXSCREEN
    screen_h = win32api.GetSystemMetrics(1)  # SM_CYSCREEN
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
            "dxcam.create() 失败：当前环境可能不支持 Desktop Duplication"
            "（无显示器/GPU，或被远程桌面/会话占用）"
        )
    frame = camera.grab(region=(left, top, right, bottom))
    return frame


# ---------------------------------------------------------------------------
# 7. 保存 PNG
# ---------------------------------------------------------------------------
def save_png(frame, process_name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stem = os.path.splitext(process_name)[0]  # Ld9BoxHeadless.exe -> Ld9BoxHeadless
    out_path = os.path.join(OUTPUT_DIR, f"{stem}.png")
    Image.fromarray(frame).save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# 8. OpenCV 模板匹配：在截图右下角区域匹配单个 sample
# ---------------------------------------------------------------------------
def match_sample_in_corner(screenshot_bgr, sample_path: str, scale: float):
    """
    在 screenshot_bgr 的右下角区域搜索 sample_path 对应的图标。

    参数：
        screenshot_bgr: numpy 数组，BGR 格式
        sample_path: sample 图片路径
        scale: 实际截图高度 / REF_CAPTURE_H（参考截图总高度 1140）

    返回：
        (max_val, global_loc, region_info, scaled_size)
        max_val:       最大匹配率（0.0 ~ 1.0）
        global_loc:    匹配位置在 screenshot_bgr 中的 (x, y)
        region_info:   搜索区域 (left, top, right)（right 可能 < 截图宽度）
        scaled_size:   缩放后 sample 的 (w, h)
    """
    # 加载 sample（灰度图 + 预生成 mask，缓存加速）
    template, template_mask = _get_sample_mask(sample_path)
    th, tw = template.shape[:2]

    # 按实际截图比例缩放 sample 和 mask
    scaled_tw = max(1, int(tw * scale))
    scaled_th = max(1, int(th * scale))
    scaled_template = cv2.resize(
        template, (scaled_tw, scaled_th), interpolation=cv2.INTER_AREA
    )
    scaled_mask = cv2.resize(
        template_mask, (scaled_tw, scaled_th), interpolation=cv2.INTER_NEAREST
    )

    # 截图转灰度
    gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    # 定义右下角搜索区域：
    #   右边空白 = 图标距截图右边参考距离 + sample 宽度 + 余量，按 scale 缩放
    #   下边空白 = 图标距截图下边参考距离 + sample 高度 + 余量 + 手动上移修正
    #   右边缩进 = 手动缩短宽度修正（工具栏实际较窄）
    right_pad = REF_ICON_RIGHT_PAD + SEARCH_SLACK
    bottom_pad = REF_ICON_BOTTOM_PAD + SEARCH_SLACK + REF_BOTTOM_EXTRA
    right_trim = int(REF_RIGHT_TRIM * scale)

    region_x = max(0, w - int((right_pad + tw) * scale))
    region_y = max(0, h - int((bottom_pad + th) * scale))
    region_r = w - right_trim  # 右边缩短
    region = gray[region_y:h, region_x:region_r]

    if region.shape[0] < scaled_th or region.shape[1] < scaled_tw:
        raise RuntimeError(
            f"搜索区域过小，无法容纳缩放后的 sample "
            f"(region={region.shape[1]}x{region.shape[0]}, sample={scaled_tw}x{scaled_th})"
        )

    # 带 mask 的模板匹配（mask=255 的区域参与匹配，mask=0 的区域忽略）
    # TM_CCOEFF_NORMED + mask：对图标形状匹配，灰色背景不参与计算
    try:
        result = cv2.matchTemplate(
            region, scaled_template,
            cv2.TM_CCOEFF_NORMED, mask=scaled_mask
        )
    except cv2.error:
        # 如果 OpenCV 版本不支持 TM_CCOEFF_NORMED + mask，回退到无 mask
        result = cv2.matchTemplate(
            region, scaled_template, cv2.TM_CCOEFF_NORMED
        )
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    # 将位置转换回全图坐标
    global_loc = (region_x + max_loc[0], region_y + max_loc[1])
    region_info = (region_x, region_y, region_r)
    return max_val, global_loc, region_info, (scaled_tw, scaled_th)


# ---------------------------------------------------------------------------
# 9. 同时匹配 drive / walk 两个 sample
# ---------------------------------------------------------------------------
def match_drive_walk(screenshot_bgr, quiet=False):
    """
    分别匹配 driveSample.png 和 walkSample.png，返回字典。

    返回：
        {
            "drive": {"val": float, "loc": (x,y), "region_info": (x,y,r), "size": (w,h)},
            "walk":  {...},
        }
    """
    h, w = screenshot_bgr.shape[:2]
    # 基于参考截图总高度 REF_CAPTURE_H(1140) 计算 scale
    scale = h / REF_CAPTURE_H
    if not quiet:
        print(f"[比例] 截图 {w}x{h}，参考截图 {REF_CAPTURE_W}x{REF_CAPTURE_H}，scale={scale:.4f}")
        print(f"       (参考游戏区 {REF_GAME_W}x{REF_GAME_H}，上栏 {REF_TITLEBAR_H}px + 右工具栏 {REF_TOOLBAR_W}px)")

    results = {}
    for name, path in (("drive", DRIVE_SAMPLE), ("walk", WALK_SAMPLE)):
        if not os.path.exists(path):
            print(f"[跳过] 未找到 sample: {path}")
            results[name] = {"val": 0.0, "loc": (0, 0), "region_info": (0, 0, 0), "size": (0, 0)}
            continue
        val, loc, region_info, size = match_sample_in_corner(
            screenshot_bgr, path, scale
        )
        results[name] = {"val": val, "loc": loc, "region_info": region_info, "size": size}
    return results


# ---------------------------------------------------------------------------
# 10. 打印匹配结果
# ---------------------------------------------------------------------------
def print_match_results(results: dict):
    print("[模板匹配] 结果：")
    best_name = None
    best_val = -1.0
    for name, info in results.items():
        val = info["val"]
        loc = info["loc"]
        status = "✓" if val >= MATCH_THRESHOLD else " "
        print(f"  {status} {name:5s}: 匹配率={val:.4f}, 位置={loc}")
        if val > best_val:
            best_val = val
            best_name = name

    if best_val >= MATCH_THRESHOLD:
        print(f"[状态] 最可能状态: {best_name} (匹配率 {best_val:.4f})")
    else:
        print("[状态] 未识别到明确的 drive/walk 状态")


# ---------------------------------------------------------------------------
# 10b. 紧凑版匹配结果（循环用，一行输出）
# ---------------------------------------------------------------------------
def format_match_results_line(results: dict) -> str:
    """返回一行匹配结果，用于循环监控输出。"""
    parts = []
    for name, info in sorted(results.items()):
        val = info["val"]
        status = "✓" if val >= MATCH_THRESHOLD else " "
        parts.append(f"{name}:{val:.4f}{status}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# 11. 生成调试标注图：红框=搜索区域，绿框=最佳匹配位置
# ---------------------------------------------------------------------------
def draw_debug_overlay(screenshot_bgr, results: dict, out_path: str):
    """
    在截图上绘制：
      - 红色虚线框：搜索区域
      - 绿色实线框：最佳匹配位置
      保存到 out_path。
    """
    if not results:
        return

    # 颜色 BGR
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

        # 红色框：搜索区域
        cv2.rectangle(debug, (rx, ry), (rx + rw - 1, ry + rh - 1), RED, 2)

        # 在搜索区域左上角标名称
        label = f"{name}_region"
        cv2.putText(debug, label, (rx + 4, ry + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, RED, 1)

        # 绿色框：最佳匹配位置
        lx, ly = loc
        cv2.rectangle(debug, (lx, ly), (lx + stw, ly + sth), GREEN, 2)

        # 在匹配框上方标匹配率
        score_label = f"{name}:{val:.3f}"
        label_y = ly - 4 if ly > 15 else ly + sth + 16
        cv2.putText(debug, score_label, (lx, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, GREEN, 1)

    # 在全图左上角标注缩放信息
    cv2.putText(debug, f"scale={h / REF_CAPTURE_H:.4f}  (ref {REF_CAPTURE_W}x{REF_CAPTURE_H})",
                (6, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, YELLOW, 1)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, debug)
    return out_path


# ---------------------------------------------------------------------------
# 11b. 解析 .kmp 中的 ClassMouseDrag key
# ---------------------------------------------------------------------------
def parse_kmp_mouse_drag_key(kmp_path: str):
    """解析 .kmp 文件，返回 ClassMouseDrag 绑定的虚拟键码 (int)，无则返回 None。"""
    try:
        with open(kmp_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for mapping in data.get('keyboardMappings', []):
            if mapping.get('class') == 'ClassMouseDrag':
                return mapping['data']['key']
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 11c. 通过 SendInput 发送虚拟键 (down + up)
# ---------------------------------------------------------------------------
def send_key_vk(vk_code: int):
    """模拟一次按键 (按下 + 释放)，使用 keybd_event API 绕过注入过滤。"""
    user32 = ctypes.windll.user32
    user32.keybd_event(vk_code, 0, 0, 0)           # down
    user32.keybd_event(vk_code, 0, 2, 0)           # up (KEYEVENTF_KEYUP)


# ---------------------------------------------------------------------------
# 12. 循环监控：每 0.5 秒截图 + 识别 + 自动切换按键方案
# ---------------------------------------------------------------------------
def run_monitor_loop(no_debug=False):
    """持续截图+匹配+自动切换按键方案，直到 Ctrl+C。"""
    i = 0
    current_mode = "walk"  # 初始状态
    last_rect_size = None  # 用于检测窗口尺寸变化

    print("[监控] 开始循环监控 (初始状态: walk, Ctrl+C 停止)\n")
    try:
        while True:
            i += 1
            t0 = time.perf_counter()

            # 每轮重新获取窗口区域（用户可能调整了模拟器大小）
            rect, _source, _wins = resolve_capture_target(TARGET_PROCESS)
            if rect is None:
                print(f"[#{i}] 无法获取截图区域，跳过")
                time.sleep(0.5)
                continue

            # 检测窗口尺寸变化
            current_size = (rect[2] - rect[0], rect[3] - rect[1])
            if last_rect_size is not None and current_size != last_rect_size:
                print(f"  [尺寸变化] {last_rect_size[0]}x{last_rect_size[1]} → {current_size[0]}x{current_size[1]}")
            last_rect_size = current_size

            # 截图
            frame = capture_region(rect)
            if frame is None:
                print(f"[#{i}] 截图返回空帧，跳过")
                time.sleep(0.5)
                continue

            # 保存（覆盖最新）
            latest_path = save_png(frame, TARGET_PROCESS)

            # 匹配
            screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            results = match_drive_walk(screenshot_bgr, quiet=True)

            elapsed_ms = (time.perf_counter() - t0) * 1000

            # 一行输出：序号 + 耗时 + 匹配结果
            line = format_match_results_line(results)
            prefix = f"[#{i:>4d}] {elapsed_ms:6.1f}ms |"

            # ---- 状态判断与按键切换 ----
            # 找出高于阈值的最佳匹配（仅当两个样本区分度足够时）
            best_name = None
            best_val = -1.0
            for name in ("drive", "walk"):
                val = results[name]["val"]
                if val >= MATCH_THRESHOLD and val > best_val:
                    best_val = val
                    best_name = name

            switch_info = ""
            if best_name is None:
                # 两个匹配率都很低 → 状态模糊，不切换
                pass
            elif best_name != current_mode:
                # 状态发生变化 → 执行切换
                kmp = DRIVE_KMP if best_name == "drive" else WALK_KMP
                if os.path.exists(kmp):
                    switch_info = f" [切换] {current_mode} → {best_name}"
                    try:
                        subprocess.run(
                            [INJECTOR, kmp],
                            capture_output=True, timeout=10,
                        )
                        current_mode = best_name
                        # 新按键方案含 ClassMouseDrag → 发送其绑定的 key 进入射击视角
                        mouse_key = parse_kmp_mouse_drag_key(kmp)
                        if mouse_key is not None:
                            send_key_vk(mouse_key)
                            switch_info += f" [MouseDrag] sent VK={mouse_key}"
                    except FileNotFoundError:
                        switch_info += " (未找到 keymap_injector.exe)"
                else:
                    switch_info = f" [跳过] .kmp 不存在: {os.path.basename(kmp)}"

            print(f"{prefix} {line}{switch_info}")

            # 调试标注图（覆盖）
            if not no_debug:
                stem = os.path.splitext(os.path.basename(latest_path))[0]
                debug_path = os.path.join(OUTPUT_DIR, f"{stem}_latest_debug.png")
                draw_debug_overlay(screenshot_bgr, results, debug_path)

            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n[监控] 已停止，共执行 {i} 轮。最终状态: {current_mode}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="LDPlayer 截图 + 右下角模板匹配 demo",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="只列出匹配到的窗口，不截图/不匹配",
    )
    parser.add_argument(
        "--match",
        metavar="PATH",
        help="对已有的 PNG 图片进行 drive/walk 模板匹配，而不是重新截图",
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="不生成带红框/绿框标注的调试图片",
    )
    args = parser.parse_args()

    # ---- 对已有图片进行匹配 ------------------------------------------------
    if args.match:
        screenshot = cv2.imread(args.match, cv2.IMREAD_COLOR)
        if screenshot is None:
            raise RuntimeError(f"无法读取图片: {args.match}")
        print(f"[匹配] 对已有图片进行模板匹配: {args.match}")
        results = match_drive_walk(screenshot)
        print_match_results(results)

        if not args.no_debug:
            base, ext = os.path.splitext(args.match)
            debug_path = f"{base}_debug{ext}"
            draw_debug_overlay(screenshot, results, debug_path)
            print(f"[调试] 标注图已保存: {debug_path}")
        return

    # ---- 实例守卫：统计 dnplayer.exe 数量 ----
    dn_count = count_processes(EMULATOR_PROCESS)
    if dn_count == 0:
        raise RuntimeError(
            "未检测到 LDPlayer 在运行（找不到 dnplayer.exe 进程）。"
            "请先启动模拟器后再运行本 demo。"
        )
    if dn_count > 1:
        raise RuntimeError(
            f"检测到 {dn_count} 个 LDPlayer 实例（多个 dnplayer.exe 进程在运行），"
            "无法确定截图目标，已停止。请只保留一个模拟器实例后再运行本 demo。"
        )

    # ---- 仅截图 Ld9BoxHeadless.exe（安卓系统画面）----
    proc = TARGET_PROCESS
    rect, source, wins = resolve_capture_target(proc)

    # 打印匹配到的候选窗口，便于排查
    if wins:
        print(f"[找到] {proc} 共有 {len(wins)} 个可见窗口，选择面积最大的一个：")
        for i, (hwnd, wrect, area) in enumerate(wins):
            title = win32gui.GetWindowText(hwnd)
            print(f"    #{i}  hwnd={hwnd} rect={wrect} '{title}'")
    else:
        print(f"[提示] {proc}: 无可见窗口。来源 = {source}")

    if rect is None:
        raise RuntimeError(f"{proc}: 无法确定截图区域，已停止。")

    print(f"      截图区域 = {rect}  ({source})")

    if args.list:
        print("[--list] 仅列出窗口，未截图。")
        return

    # ---- keymap_injector.exe init（预注入 DLL）------------------------------
    if os.path.exists(INJECTOR):
        print(f"[初始化] 执行 keymap_injector.exe init...")
        try:
            result = subprocess.run(
                [INJECTOR, "init"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                stderr_tail = result.stderr.strip()[-200:] if result.stderr else ""
                print(f"[警告] init 返回码 {result.returncode}")
                if stderr_tail:
                    print(f"       {stderr_tail}")
            else:
                print("[初始化] init 完成")
        except subprocess.TimeoutExpired:
            print("[警告] init 超时（>10s），跳过，切换命令可能较慢。")
        except FileNotFoundError:
            print(f"[警告] 未找到 {INJECTOR}，跳过 init。")
    else:
        print(f"[警告] 未找到 keymap_injector.exe ({INJECTOR})，跳过 init。")

    # ---- 进入循环监控 ----
    run_monitor_loop(no_debug=args.no_debug)


if __name__ == "__main__":
    main()
