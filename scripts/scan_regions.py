#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
区域扫描工具 — 对截图全图匹配模板，生成 debug 标注图 + regions 配置

用途：
  给一张 1920x1080 的游戏截图 + 一组模板图片，
  全图搜索每个模板的最佳位置 -> 推算 region 参数 -> 输出 game.json 片段。

用法:
  python scripts/scan_regions.py ^
      --screenshot C:/screenshots/game.png ^
      --templates templates/*.png ^
      --output scan_result

  或指定单个模板文件夹:
  python scripts/scan_regions.py ^
      --screenshot screenshot.png ^
      --templates games/my_game/templates/ ^
      --output scan_result

输出:
  scan_result/
    ├── scan_debug.png         标注图：绿框=匹配位置，匹配率标签
    └── regions_snippet.json   可粘贴到 game.json 的 regions + templates 片段
"""

import os
import sys
import json
import glob
import argparse
import time

import cv2
import numpy as np

# 将项目根目录加入 sys.path，方便引用 detector 模块
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ── 颜色常量 ──
RED    = (0, 0, 255)
GREEN  = (0, 255, 0)
YELLOW = (0, 255, 255)
CYAN   = (255, 255, 0)
WHITE  = (255, 255, 255)

# ── 参考分辨率 ──
GAME_W = 1920
GAME_H = 1080


# =============================================================================
# 1. 全图匹配 — CCOEFF + CCORR 双通道，取峰度最优
# =============================================================================
def full_image_match(screenshot_bgr, template_path: str,
                     match_threshold: float = 0.6) -> dict:
    """在整张截图上做模板匹配。

       同时尝试两种方法，取峰度（peak σ）更高者：
         (a) TM_CCOEFF_NORMED — 适合高对比度模板（GTASA 深色底+亮图标）
             与程序运行时的匹配算法一致。
         (b) TM_CCORR_NORMED — 适合低方差 / 亮度特征模板（浅色半透明 UI 等）
             程序运行时不用此方法，扫描脚本额外提供以辅助定位。

       返回匹配信息 dict。若最佳匹配率低于 match_threshold，标记为低置信度。
    """
    from src.detector.matcher import create_feature_mask

    template, mask = create_feature_mask(template_path)
    th, tw = template.shape[:2]

    gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    scale = h / GAME_H

    scaled_tw = max(1, int(tw * scale))
    scaled_th = max(1, int(th * scale))
    scaled_template = cv2.resize(
        template, (scaled_tw, scaled_th), interpolation=cv2.INTER_AREA)
    scaled_mask = cv2.resize(
        mask, (scaled_tw, scaled_th), interpolation=cv2.INTER_NEAREST)

    candidates = []  # (peak, score, loc, method_name)

    # ── 方法 A: TM_CCOEFF_NORMED（与程序运行时一致）──
    try:
        r = cv2.matchTemplate(gray, scaled_template, cv2.TM_CCOEFF_NORMED)
        v, _, _, loc = cv2.minMaxLoc(r)
        m, s = cv2.meanStdDev(r)
        peak = float((v - m[0][0]) / s[0][0]) if s[0][0] > 0 else 0.0
        candidates.append((peak, float(v), loc, "CCOEFF"))
    except cv2.error:
        pass

    # ── 方法 B: TM_CCORR_NORMED（低方差模板，亮度特征）──
    try:
        r = cv2.matchTemplate(gray, scaled_template, cv2.TM_CCORR_NORMED)
        v, _, _, loc = cv2.minMaxLoc(r)
        m, s = cv2.meanStdDev(r)
        peak = float((v - m[0][0]) / s[0][0]) if s[0][0] > 0 else 0.0
        candidates.append((peak, float(v), loc, "CCORR"))
    except cv2.error:
        pass

    # ── 方法 C: TM_CCOEFF_NORMED with mask（与程序运行时一致，mask 过滤背景）──
    mask_active = float(np.count_nonzero(scaled_mask)) / (scaled_tw * scaled_th)
    if mask_active >= 0.05:
        try:
            r = cv2.matchTemplate(gray, scaled_template,
                                  cv2.TM_CCOEFF_NORMED, mask=scaled_mask)
            v, _, _, loc = cv2.minMaxLoc(r)
            m, s = cv2.meanStdDev(r)
            peak = float((v - m[0][0]) / s[0][0]) if s[0][0] > 0 else 0.0
            candidates.append((peak, float(v), loc, "MASK"))
        except cv2.error:
            pass

    # 按峰度排序取最优
    if not candidates:
        best_peak, best_val, best_loc, best_method = 0.0, 0.0, (0, 0), "none"
    else:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_peak, best_val, best_loc, best_method = candidates[0]

    x_px, y_px = best_loc
    x_ref = int(x_px / scale)
    y_ref = int(y_px / scale)

    # 标记：原始分低于阈值 或 方法既不是 CCOEFF 也不是 MASK
    return {
        "max_val": best_val,
        "loc_px": (x_px, y_px),
        "loc_ref": (x_ref, y_ref),
        "template_w": tw,
        "template_h": th,
        "scaled_w": scaled_tw,
        "scaled_h": scaled_th,
        "scale": scale,
        "match_method": best_method,
        "peak_sigma": best_peak,
        "is_low_confidence": (best_val < match_threshold
                              or best_method not in ("CCOEFF", "MASK")),
    }


# =============================================================================
# 2. 根据匹配位置推算 region 配置
# =============================================================================
def suggest_region(info: dict, slack: int = 20, expand: int = 16) -> dict:
    """根据模板的最佳匹配位置，推算合适的 region 定义。

       返回 {region_name: {method, margin_*, slack, search_expand, ...}}
    """
    x = info["loc_ref"][0]
    y = info["loc_ref"][1]
    tw = info["template_w"]
    th = info["template_h"]
    right_edge = x + tw
    bottom_edge = y + th

    # 判断区域类型
    if x > GAME_W * 0.5 and y > GAME_H * 0.5:
        method = "bottom_right"
        params = {
            "method": method,
            "margin_right": max(0, int(GAME_W - right_edge)),
            "margin_bottom": max(0, int(GAME_H - bottom_edge)),
        }
    elif x < GAME_W * 0.5 and y > GAME_H * 0.5:
        method = "bottom_left"
        params = {
            "method": method,
            "margin_left": max(0, int(x)),
            "margin_bottom": max(0, int(GAME_H - bottom_edge)),
        }
    elif x > GAME_W * 0.5 and y < GAME_H * 0.5:
        method = "top_right"
        params = {
            "method": method,
            "margin_right": max(0, int(GAME_W - right_edge)),
            "margin_top": max(0, int(y)),
        }
    elif x < GAME_W * 0.5 and y < GAME_H * 0.5:
        method = "top_left"
        params = {
            "method": method,
            "margin_left": max(0, int(x)),
            "margin_top": max(0, int(y)),
        }
    else:
        method = "center"
        params = {
            "method": method,
            "center_range_w": max(80, tw * 3),
            "center_range_h": max(80, th * 3),
        }

    params["slack"] = slack
    params["search_expand"] = expand
    return params


# =============================================================================
# 3. 合并相近的 regions（减少碎片化）
# =============================================================================
def _params_key(p: dict) -> str:
    """为 region 参数生成唯一键（用于判断是否可合并）。"""
    m = p.get("method", "")
    if m == "bottom_right":
        return f"br_{p.get('margin_right')}_{p.get('margin_bottom')}"
    elif m == "bottom_left":
        return f"bl_{p.get('margin_left')}_{p.get('margin_bottom')}"
    elif m == "top_right":
        return f"tr_{p.get('margin_right')}_{p.get('margin_top')}"
    elif m == "top_left":
        return f"tl_{p.get('margin_left')}_{p.get('margin_top')}"
    elif m == "center":
        return f"c_{p.get('center_range_w')}_{p.get('center_range_h')}"
    return "unknown"


def merge_regions(template_results: list,
                  slack: int = 20, expand: int = 16) -> tuple:
    """将位置/参数相近的模板合并到同一个 region。

       返回:
         regions:  {region_id: region_config}
         template_assignments: [{"path": str, "region": region_id}, ...]
    """
    # 为每个模板推算 region 参数
    items = []
    for t in template_results:
        params = suggest_region(t["info"], slack, expand)
        key = _params_key(params)
        items.append({
            "path": t["path"],
            "params": params,
            "group_key": key,
        })

    # 按 group_key 分组，自动生成 region_id
    groups = {}
    for item in items:
        key = item["group_key"]
        if key not in groups:
            groups[key] = {
                "params": item["params"],
                "templates": [],
            }
        groups[key]["templates"].append(item["path"])

    # 生成 regions dict
    regions = {}
    template_assignments = []
    for i, (key, grp) in enumerate(sorted(groups.items()), 1):
        rid = f"region_{i}" if len(groups) > 1 else "default"
        regions[rid] = grp["params"]
        for tpath in grp["templates"]:
            template_assignments.append({"path": tpath, "region": rid})

    return regions, template_assignments


# =============================================================================
# 4. 生成标注图
# =============================================================================
def draw_scan_debug(screenshot_bgr, template_results: list,
                    out_path: str):
    """绘制全图搜索的 debug 标注图。"""
    debug = screenshot_bgr.copy()
    h, w = debug.shape[:2]

    for i, t in enumerate(template_results):
        info = t["info"]
        name = os.path.splitext(os.path.basename(t["path"]))[0]
        x, y = info["loc_px"]
        sw, sh = info["scaled_w"], info["scaled_h"]
        val = info["max_val"]

        # 绿色实线框：匹配位置（低置信度用橙色）
        if info["is_low_confidence"]:
            color = (0, 200, 255)   # 橙色
            status = "LOW"
        else:
            color = GREEN
            status = "OK"

        cv2.rectangle(debug, (x, y), (x + sw, y + sh), color, 2)

        method = info.get("match_method", "?")
        label = f"#{i+1} {name} {val:.3f} [{status}][{method}]"
        text_y = y - 6 if y > 16 else y + sh + 18
        cv2.putText(debug, label, (x, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    # 左上角信息栏
    cv2.rectangle(debug, (0, 0), (w, 28), (0, 0, 0), -1)
    cv2.putText(debug, f"Scan result: {len(template_results)} templates, "
                f"{w}x{h} screenshot",
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, YELLOW, 1)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    cv2.imwrite(out_path, debug)
    return out_path


# =============================================================================
# 5. 生成 JSON 片段
# =============================================================================
def generate_snippet(regions: dict, template_assignments: list,
                     out_path: str):
    """生成 game.json 的 regions + templates 片段。"""
    snippet = {
        "_comment": "Copy this into your game.json",
        "regions": regions,
        "template_usages": [
            {"path": t["path"], "region": t["region"]}
            for t in template_assignments
        ],
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snippet, f, indent=2, ensure_ascii=False)
    return out_path


# =============================================================================
# 6. 主流程
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="区域扫描工具 — 全图模板匹配 + 推算 regions 配置")
    parser.add_argument("--screenshot", required=True,
                        help="游戏截图路径 (1920x1080 纯游戏画面)")
    parser.add_argument("--templates", required=True,
                        help="模板图片目录 或 glob 模式 (如 templates/*.png)")
    parser.add_argument("--output", default="scan_result",
                        help="输出目录 (默认 scan_result)")
    parser.add_argument("--slack", type=int, default=20,
                        help="区域浮动容忍像素 (默认 20)")
    parser.add_argument("--expand", type=int, default=16,
                        help="搜索窗口外扩像素 (默认 16)")
    parser.add_argument("--threshold", type=float, default=0.6,
                        help="匹配置信度阈值 (默认 0.6)，低于此值标记为低置信度")
    parser.add_argument("--no-group", action="store_true",
                        help="不合并相近 region (每个模板独立 region)")
    args = parser.parse_args()

    # 收集模板文件
    if os.path.isdir(args.templates):
        template_files = sorted(glob.glob(os.path.join(args.templates, "*.png")))
    else:
        template_files = sorted(glob.glob(args.templates))
    if not template_files:
        print(f"[错误] 未找到模板文件: {args.templates}")
        sys.exit(1)
    print(f"[扫描] 模板数: {len(template_files)}")

    # 读取截图
    screenshot = cv2.imread(args.screenshot)
    if screenshot is None:
        print(f"[错误] 无法读取截图: {args.screenshot}")
        sys.exit(1)
    h, w = screenshot.shape[:2]
    print(f"[扫描] 截图尺寸: {w}×{h}")

    # ── 逐个模板全图匹配 ──
    print(f"[扫描] 开始全图匹配 ({len(template_files)} 个模板)...")
    t0_total = time.perf_counter()

    template_results = []
    for i, tpath in enumerate(template_files):
        name = os.path.basename(tpath)
        t0 = time.perf_counter()
        info = full_image_match(screenshot, tpath, args.threshold)
        elapsed = (time.perf_counter() - t0) * 1000
        conf_tag = "LOW" if info["is_low_confidence"] else "OK"
        method = info.get("match_method", "?")
        peak = info.get("peak_sigma", 0.0)
        print(f"  [{i+1:>3d}] {elapsed:6.0f}ms [{conf_tag}][{method}] {name:30s} "
              f"score={info['max_val']:.4f}  peak={peak:.1f}σ  "
              f"loc=({info['loc_ref'][0]},{info['loc_ref'][1]})")
        template_results.append({"path": tpath, "info": info})

    total_elapsed = (time.perf_counter() - t0_total) * 1000
    low_count = sum(1 for t in template_results if t["info"]["is_low_confidence"])
    ccorr_count = sum(1 for t in template_results
                      if t["info"].get("match_method") == "CCORR"
                      and not t["info"]["is_low_confidence"])
    print(f"[扫描] 完成! 总耗时 {total_elapsed:.0f}ms, "
          f"平均 {total_elapsed/len(template_results):.0f}ms/模板")
    if low_count:
        print(f"[警告] {low_count}/{len(template_results)} 个模板匹配质量低，"
              f"可能位置不准确")
    if ccorr_count:
        print(f"[提示] {ccorr_count} 个模板由 CCORR 方法匹配到（程序运行时用 CCOEFF），"
              f"实际检测时效果可能有差异，建议优化模板")
    print()

    # ── 推算 regions ──
    if args.no_group:
        # 每个模板独立 region
        regions = {}
        template_assignments = []
        for i, t in enumerate(template_results, 1):
            rid = f"region_{i}"
            regions[rid] = suggest_region(t["info"], args.slack, args.expand)
            template_assignments.append({"path": t["path"], "region": rid})
    else:
        regions, template_assignments = merge_regions(
            template_results, args.slack, args.expand)

    print(f"[结果] 共 {len(regions)} 个 region(s):")
    for rid, cfg in regions.items():
        method = cfg.get("method", "?")
        if method in ("bottom_right", "bottom_left", "top_right", "top_left"):
            print(f"  {rid}: {method} "
                  f"(margin={ {k:v for k,v in cfg.items() if k.startswith('margin')} })")
        else:
            print(f"  {rid}: {method} ({cfg})")

    # ── 生成输出 ──
    out_dir = args.output
    debug_path = os.path.join(out_dir, "scan_debug.png")
    snippet_path = os.path.join(out_dir, "regions_snippet.json")

    draw_scan_debug(screenshot, template_results, debug_path)
    print(f"\n[输出] Debug 标注图: {debug_path}")

    generate_snippet(regions, template_assignments, snippet_path)
    print(f"[输出] Regions 片段: {snippet_path}")


if __name__ == "__main__":
    main()
