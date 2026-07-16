#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
templateDebugger.py — multi-template match debugger.

Usage:
  python scripts/templateDebugger.py
      --screenshot <path> --template <path> [<path> ...] [--output <name>]

  --screenshot:  screenshot PNG (1920x1080 reference)
  --template:    one or more template .png paths
  --output:      output basename [default: screenshot basename + '_debug']
  --game:        game config folder [default: CODM]

For each template, reads its region from game.json, runs match_template,
and draws all results onto a single debug overlay.
"""

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.detector.matcher import (
    create_feature_mask,
    compute_search_rect,
    match_template,
    _sample_mask_cache,
)


def find_template_config(game_config, template_path):
    tpl_basename = os.path.basename(template_path)
    for state in game_config.get("states", []):
        for t in state.get("templates", []):
            if os.path.basename(t["path"]) == tpl_basename:
                rid = t["region"]
                return state["id"], t, game_config.get("regions", {}).get(rid, {})
    return None


def main():
    parser = argparse.ArgumentParser(description="Multi-template match debugger")
    parser.add_argument("--screenshot", required=True, help="Screenshot PNG path")
    parser.add_argument("--template", required=True, nargs="+", help="One or more template PNG paths")
    parser.add_argument("--output", default=None, help="Output basename [default: auto from screenshot]")
    parser.add_argument("--game", default="CODM", help="Game config folder [default: CODM]")
    args = parser.parse_args()

    screenshot = cv2.imread(args.screenshot, cv2.IMREAD_COLOR)
    if screenshot is None:
        print(f"ERROR: cannot read screenshot: {args.screenshot}")
        return 1
    sh, sw = screenshot.shape[:2]
    print(f"Screenshot: {sw}x{sh}")

    game_json = os.path.join("games", args.game, "game.json")
    if not os.path.isfile(game_json):
        print(f"ERROR: game.json not found: {game_json}")
        return 1
    with open(game_json, "r", encoding="utf-8") as f:
        gc = json.load(f)

    det = gc.get("detection", {})
    ref_game_w = det.get("ref_game_w", gc.get("resolution", {}).get("width", 1920))
    ref_game_h = det.get("ref_game_h", gc.get("resolution", {}).get("height", 1080))
    ref_titlebar_h = det.get("ref_titlebar_h", 60)
    threshold = det.get("match_threshold", gc.get("detection", {}).get("threshold", 0.75))
    # Scale: mirror match_multi — detect game-area-only vs titlebar-included
    if abs(sh - ref_game_h) < 10:  # height ≈ 1080 → pure game area (RenderWindow)
        scale = sh / ref_game_h
        titlebar_px = 0
        ref_info = f"{ref_game_w}x{ref_game_h} (pure game area)"
    else:
        ref_capture_h = ref_game_h + ref_titlebar_h
        scale = sh / ref_capture_h
        titlebar_px = int(ref_titlebar_h * scale)
        ref_info = f"{ref_game_w}x{ref_game_h} (+{ref_titlebar_h}px titlebar)"
    print(f"Ref: {ref_info}  scale={scale:.4f}  threshold={threshold}\n")

    overlay = screenshot.copy()
    colors = [
        (0, 255, 0), (255, 0, 0), (0, 255, 255), (255, 255, 0),
        (255, 0, 255), (128, 255, 0), (0, 128, 255), (255, 128, 0),
    ]
    y_label = 25

    for idx, tpl_path in enumerate(args.template):
        color = colors[idx % len(colors)]
        tpl_name = os.path.basename(tpl_path)

        _sample_mask_cache.clear()

        info = find_template_config(gc, tpl_path)
        if info is None:
            print(f"[{idx}] {tpl_name}  WARNING: not in game.json, skipping")
            continue
        state_id, tpl_entry, region_cfg = info
        rid = tpl_entry["region"]
        matching_mode = tpl_entry.get("matching_mode", "pixel")

        t_gray = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
        if t_gray is None:
            print(f"[{idx}] {tpl_name}  ERROR: cannot read")
            continue
        th, tw = t_gray.shape[:2]

        game_rect = compute_search_rect(region_cfg, tw, th, ref_game_w, ref_game_h)
        sl = max(0, int(game_rect[0] * scale))
        st = max(0, int(game_rect[1] * scale) + titlebar_px)
        sr = min(sw, int(game_rect[2] * scale))
        sb = min(sh, int(game_rect[3] * scale) + titlebar_px)

        # Scale search area dimensions
        search_w = sr - sl
        search_h = sb - st
        scaled_tw = max(1, int(tw * scale))
        scaled_th = max(1, int(th * scale))

        # Check if template fits — MUST mirror match_template's check
        fits = (search_w >= scaled_tw and search_h >= scaled_th)
        fit_warn = ""
        if not fits:
            max_x = int(ref_game_w - tw - region_cfg.get('search_expand', 8))
            max_y = int(ref_game_h - th - region_cfg.get('search_expand', 8))
            fit_warn = (f"  ** TPL TOO LARGE: search={search_w}x{search_h} "
                        f"tpl={scaled_tw}x{scaled_th} — x must be <= {max_x}, y <= {max_y}")

        t0 = time.perf_counter()
        val, loc, _, size = match_template(
            screenshot, tpl_path, scale,
            sl, st, sr, sb, matching_mode=matching_mode)
        elapsed = (time.perf_counter() - t0) * 1000

        mx, my = loc
        mw, mh = size
        status = "OK" if val >= threshold else "--"

        print(f"[{idx}] {tpl_name:40s}  {state_id:20s}  "
              f"val={val:+.4f} [{status}]  loc=({mx},{my})  "
              f"search={search_w}x{search_h}{fit_warn}  {elapsed:.1f}ms")

        if not fits:
            # Don't draw if template doesn't fit (match always returns 0,0)
            cv2.putText(overlay, f"SKIP {tpl_name}: search={search_w}x{search_h} < tpl={scaled_tw}x{scaled_th}",
                       (10, y_label), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)
            y_label += 20
            continue

        # Draw search region
        cv2.rectangle(overlay, (sl, st), (sr, sb), color, 1)
        # Draw match box
        box_color = (0, 255, 0) if val >= threshold else (0, 255, 255) if val >= 0.3 else (128, 128, 128)
        cv2.rectangle(overlay, (mx, my), (mx + mw, my + mh), box_color, 2)
        # Label
        lbl = f"[{idx}] {state_id} | {tpl_name} | val={val:.3f} {status}"
        cv2.putText(overlay, lbl, (10, y_label), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        y_label += 20

    out = args.output or os.path.splitext(os.path.basename(args.screenshot))[0] + "_debug"
    out_path = out + ".png" if not out.endswith(".png") else out
    cv2.imwrite(out_path, overlay)
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
