#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Template matching module - feature mask + multi-region matching (schema v2).
"""

import os
import cv2
import numpy as np

DEFAULT_DETECTION = {
    "ref_game_w": 1920,
    "ref_game_h": 1080,
    "ref_titlebar_h": 60,
    "match_threshold": 0.75,
    "feature_mask": {"enabled": True, "dark_percentile": 22, "bright_percentile": 82},
}

_sample_mask_cache = {}


# ===========================================================================
# 1. Feature mask generation
# ===========================================================================
def create_feature_mask(template_path, dark_percentile=22, bright_percentile=82):
    """Return sample grayscale + mask (uint8, 255=match area, 0=ignore). Cached."""
    if template_path in _sample_mask_cache:
        return _sample_mask_cache[template_path]

    gray = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"Cannot read template: {template_path}")

    flat = gray.ravel()
    dark_thresh = np.percentile(flat, dark_percentile)
    bright_thresh = np.percentile(flat, bright_percentile)

    mask = np.zeros_like(gray, dtype=np.uint8)
    mask[gray <= dark_thresh] = 255
    mask[gray >= bright_thresh] = 255

    if np.count_nonzero(mask) == 0:
        mask[:] = 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.dilate(mask, kernel, iterations=1)

    _sample_mask_cache[template_path] = (gray, mask)
    return gray, mask


# ===========================================================================
# 2. Search rect calculation from region config
# ===========================================================================
def compute_search_rect(region_cfg, tpl_w, tpl_h, game_w, game_h):
    """Calculate search rectangle in game reference coordinates (1920x1080).

    Two formats supported:
      xywh (preferred):  x, y, width, height, search_expand
      margin (legacy):   method + margin_left/right/top/bottom + slack + search_expand
    """
    # ── xywh format (exact pixel coordinates in 1920x1080 ref) ──
    if "x" in region_cfg:
        x = region_cfg.get("x", 0)
        y = region_cfg.get("y", 0)
        rw = region_cfg.get("width", tpl_w) or tpl_w
        rh = region_cfg.get("height", tpl_h) or tpl_h
        expand = region_cfg.get("search_expand", 8)
        # Ensure search rect can at least hold the template (right/bottom may exceed game bounds)
        right = max(x + tpl_w + expand, x + rw + expand)
        bottom = max(y + tpl_h + expand, y + rh + expand)
        return (max(0, x - expand),
                max(0, y - expand),
                right,
                bottom)

    # ── Legacy margin-based format ──
    method = region_cfg.get("method", "bottom_right")
    slack = region_cfg.get("slack", 20)
    expand = region_cfg.get("search_expand", 16)
    extra = tpl_w + slack + expand
    extra_h = tpl_h + slack + expand

    if method == "bottom_right":
        mr = region_cfg.get("margin_right", 40)
        mb = region_cfg.get("margin_bottom", 40)
        left = max(0, game_w - mr - extra)
        top = max(0, game_h - mb - extra_h)
        right = game_w
        bottom = game_h
    elif method == "bottom_left":
        ml = region_cfg.get("margin_left", 40)
        mb = region_cfg.get("margin_bottom", 40)
        left = 0
        top = max(0, game_h - mb - extra_h)
        right = min(game_w, ml + extra)
        bottom = game_h
    elif method == "top_right":
        mr = region_cfg.get("margin_right", 40)
        mt = region_cfg.get("margin_top", 40)
        left = max(0, game_w - mr - extra)
        top = 0
        right = game_w
        bottom = min(game_h, mt + extra_h)
    elif method == "top_left":
        ml = region_cfg.get("margin_left", 40)
        mt = region_cfg.get("margin_top", 40)
        left = 0
        top = 0
        right = min(game_w, ml + extra)
        bottom = min(game_h, mt + extra_h)
    else:  # center
        cw = region_cfg.get("center_range_w", 160)
        ch = region_cfg.get("center_range_h", 160)
        left = max(0, (game_w - extra) // 2 - cw // 2)
        top = max(0, (game_h - extra_h) // 2 - ch // 2)
        right = min(game_w, left + extra + cw)
        bottom = min(game_h, top + extra_h + ch)

    return int(left), int(top), int(right), int(bottom)


# ===========================================================================
# 3. Single template match
# ===========================================================================
def match_template(screenshot_bgr, template_path, scale,
                   search_left, search_top, search_right, search_bottom,
                   matching_mode="pixel"):
    """Search template within specified rectangle.

    matching_mode: "pixel" = TM_CCOEFF_NORMED on raw pixels (default)
                   "edge"  = Canny edges + TM_CCORR_NORMED (shape-based)

    Returns: (max_val, global_loc, region_info, scaled_size)
    """
    template, template_mask = create_feature_mask(template_path)
    th, tw = template.shape[:2]

    scaled_tw = max(1, int(tw * scale))
    scaled_th = max(1, int(th * scale))
    scaled_template = cv2.resize(template, (scaled_tw, scaled_th), interpolation=cv2.INTER_AREA)
    scaled_mask = cv2.resize(template_mask, (scaled_tw, scaled_th), interpolation=cv2.INTER_NEAREST)

    gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    sl = max(0, search_left)
    st = max(0, search_top)
    sr = min(w, search_right)
    sb = min(h, search_bottom)

    if sb - st < scaled_th or sr - sl < scaled_tw:
        return 0.0, (0, 0), (sl, st, sr), (scaled_tw, scaled_th)

    region = gray[st:sb, sl:sr]

    if matching_mode == "hog":
        # ── HOG-inspired: Sobel gradient magnitude matching ──
        # Compute edge-strength maps (brightness-invariant, continuous)
        tpl_gx = cv2.Sobel(scaled_template.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
        tpl_gy = cv2.Sobel(scaled_template.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
        tpl_mag = np.sqrt(tpl_gx**2 + tpl_gy**2)
        tpl_mag = cv2.normalize(tpl_mag, None, 0, 1.0, cv2.NORM_MINMAX)

        reg_f32 = region.astype(np.float32)
        reg_gx = cv2.Sobel(reg_f32, cv2.CV_32F, 1, 0, ksize=3)
        reg_gy = cv2.Sobel(reg_f32, cv2.CV_32F, 0, 1, ksize=3)
        reg_mag = np.sqrt(reg_gx**2 + reg_gy**2)
        reg_mag = cv2.normalize(reg_mag, None, 0, 1.0, cv2.NORM_MINMAX)

        try:
            result = cv2.matchTemplate(reg_mag, tpl_mag, cv2.TM_CCOEFF_NORMED)  # match edge-strength patterns
        except cv2.error:
            result = np.zeros((1, 1), dtype=np.float32)
    elif matching_mode == "edge":
        # ── Edge-based matching: match shapes, not colors ──
        tpl_edges = cv2.Canny(scaled_template, 40, 120)
        reg_edges = cv2.Canny(region, 40, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        tpl_edges = cv2.dilate(tpl_edges, kernel)
        reg_edges = cv2.dilate(reg_edges, kernel)
        tpl_edges_f = tpl_edges.astype(np.float32)
        reg_edges_f = reg_edges.astype(np.float32)
        try:
            result = cv2.matchTemplate(reg_edges_f, tpl_edges_f, cv2.TM_CCORR_NORMED)
        except cv2.error:
            result = np.zeros((1, 1), dtype=np.float32)
    else:
        # ── Pixel-based matching (default) ──
        try:
            result = cv2.matchTemplate(region, scaled_template, cv2.TM_CCOEFF_NORMED, mask=scaled_mask)
        except cv2.error:
            result = cv2.matchTemplate(region, scaled_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    # Clamp: TM_CCOEFF_NORMED can produce NaN/inf for zero-variance templates
    if not (np.isfinite(max_val)):
        max_val = 0.0
    max_val = float(np.clip(max_val, -1.0, 1.0))

    global_loc = (sl + max_loc[0], st + max_loc[1])
    region_info = (sl, st, sr)
    return max_val, global_loc, region_info, (scaled_tw, scaled_th)


# ===========================================================================
# 4. Multi-state, multi-region template matching (schema v2)
# ===========================================================================
def match_multi(screenshot_bgr, state_configs, regions,
                detection_config=None, capture_source=""):
    """Match all states. Returns {state_id: {val, loc, region_info, size}}."""
    if detection_config is None:
        detection_config = DEFAULT_DETECTION

    h, w = screenshot_bgr.shape[:2]
    is_game_area_only = "RenderWindow" in capture_source

    cfg = detection_config
    ref_game_w = cfg["ref_game_w"]
    ref_game_h = cfg["ref_game_h"]
    ref_titlebar_h = cfg.get("ref_titlebar_h", 60)

    if is_game_area_only:
        scale = h / ref_game_h
        titlebar_px = 0
    else:
        ref_capture_h = ref_game_h + ref_titlebar_h
        scale = h / ref_capture_h
        titlebar_px = int(ref_titlebar_h * scale)

    results = {}

    for state in state_configs:
        sid = state["id"]
        templates = state.get("templates", [])
        match_logic = state.get("match_logic", "any")
        global_threshold = cfg.get("match_threshold", 0.75)
        min_pass_ratio = state.get("min_pass_ratio", None)  # e.g. 0.75 → 3/4 must pass

        if not templates:
            results[sid] = {"val": 0.0, "loc": (0, 0),
                            "region_info": (0, 0, 0), "size": (0, 0)}
            continue

        template_vals = []
        template_details = []

        for tmpl in templates:
            tpath = tmpl["path"]
            region_id = tmpl.get("region", "default")
            region_cfg = regions.get(region_id, {})

            if not os.path.exists(tpath):
                template_vals.append(0.0)
                template_details.append({
                    "val": 0.0, "loc": (0, 0),
                    "region_info": (0, 0, 0), "size": (0, 0),
                })
                continue

            t_gray = cv2.imread(tpath, cv2.IMREAD_GRAYSCALE)
            if t_gray is None:
                template_vals.append(0.0)
                template_details.append({
                    "val": 0.0, "loc": (0, 0),
                    "region_info": (0, 0, 0), "size": (0, 0),
                })
                continue
            t_ref_h, t_ref_w = t_gray.shape[:2]

            game_rect = compute_search_rect(
                region_cfg, t_ref_w, t_ref_h, ref_game_w, ref_game_h)

            search_left = int(game_rect[0] * scale)
            search_top = int(game_rect[1] * scale) + titlebar_px
            search_right = int(game_rect[2] * scale)
            search_bottom = int(game_rect[3] * scale) + titlebar_px

            val, loc, region_info, size = match_template(
                screenshot_bgr, tpath, scale,
                search_left, search_top, search_right, search_bottom,
                matching_mode=tmpl.get("matching_mode", "pixel"))

            template_vals.append(val)
            template_details.append({
                "val": val, "loc": loc,
                "region_info": region_info, "size": size,
            })

        if match_logic == "all":
            if min_pass_ratio and min_pass_ratio < 1.0:
                # Relaxed all: at least N templates must pass threshold
                min_pass = max(1, int(len(template_vals) * min_pass_ratio + 0.5))
                passed = [(v, d) for v, d in zip(template_vals, template_details)
                          if d["val"] >= global_threshold]
                if len(passed) >= min_pass:
                    combined_val = min(p[0] for p in passed)  # score = weakest pass
                    best_detail = min(passed, key=lambda p: p[0])[1]
                else:
                    combined_val = min(template_vals)
                    best_detail = template_details[template_vals.index(combined_val)]
            else:
                combined_val = min(template_vals) if template_vals else 0.0
                worst_idx = template_vals.index(combined_val) if template_vals else 0
                best_detail = template_details[worst_idx]
        else:
            combined_val = max(template_vals) if template_vals else 0.0
            best_idx = template_vals.index(combined_val) if template_vals else 0
            best_detail = template_details[best_idx]

        # ── Negative templates: if any anti-template matches, penalize score ──
        negative_templates = state.get("negative_templates", [])
        if negative_templates and combined_val > 0:
            negative_penalty = state.get("negative_penalty", 0.50)
            best_neg = 0.0
            for nt in negative_templates:
                nt_path = nt["path"]
                nrid = nt.get("region", "default")
                nrcfg = regions.get(nrid, {})
                if not os.path.exists(nt_path):
                    continue
                ng = cv2.imread(nt_path, cv2.IMREAD_GRAYSCALE)
                if ng is None:
                    continue
                nrh, nrw = ng.shape[:2]
                ng_rect = compute_search_rect(nrcfg, nrw, nrh, ref_game_w, ref_game_h)
                nsl = max(0, int(ng_rect[0] * scale))
                nst = max(0, int(ng_rect[1] * scale) + titlebar_px)
                nsr = min(w, int(ng_rect[2] * scale))
                nsb = min(h, int(ng_rect[3] * scale) + titlebar_px)
                nval, _, _, _ = match_template(
                    screenshot_bgr, nt_path, scale, nsl, nst, nsr, nsb,
                    matching_mode=nt.get("matching_mode", "pixel"))
                if nval > best_neg:
                    best_neg = nval
            if best_neg >= 0.35:  # significant anti-template match
                factor = 1.0 - negative_penalty * min(1.0, best_neg / 0.75)
                combined_val *= factor

        # ── Per-template details for debug overlay ──
        tpl_boxes = []
        for tinfo, d in zip(templates, template_details):
            tpl_boxes.append({
                "name": os.path.basename(tinfo["path"]),
                "val": d["val"],
                "loc": d["loc"],
                "size": d["size"],
            })

        results[sid] = {
            "val": combined_val,
            "loc": best_detail["loc"],
            "region_info": best_detail["region_info"],
            "size": best_detail["size"],
            "templates": tpl_boxes,
        }

    return results


# ===========================================================================
# 5. Compact match result line / print helpers
# ===========================================================================
def format_match_line(results, threshold=0.75):
    """Format all state match results as a single compact line."""
    parts = []
    for sid, info in sorted(results.items()):
        status = "OK" if info["val"] >= threshold else "--"
        parts.append(f"{sid}={info['val']:.3f}[{status}]")
    return " | ".join(parts)


def print_match_results(results, threshold=0.75):
    """Print detailed match results to stdout."""
    for sid, info in sorted(results.items()):
        status = "OK" if info["val"] >= threshold else "--"
        x, y = info.get("loc", (0, 0))
        print(f"  {sid:25s} {info['val']:.4f} [{status}]  loc=({x},{y})")


# ===========================================================================
# 6. Debug overlay
# ===========================================================================
def draw_debug_overlay(screenshot_bgr, results, output_path, ref_capture_h=1140):
    """Draw per-template match boxes on screenshot and save."""
    green = (0, 255, 0)
    yellow = (0, 255, 255)
    red = (0, 0, 255)
    img = screenshot_bgr.copy()
    y_label = 25

    for sid, info in sorted(results.items()):
        val = info.get("val", 0)
        # Per-template boxes
        for tbox in info.get("templates", []):
            tv = tbox.get("val", 0)
            tl = tbox.get("loc", (0, 0))
            ts = tbox.get("size", (0, 0))
            color = green if tv >= 0.6 else yellow if tv >= 0.3 else red
            tx, ty = tl
            tw, th = ts
            if tw > 0 and th > 0:
                cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), color, 1)
                name = tbox.get("name", "?")
                label = f"{sid}/{name} {tv:.3f}"
                cv2.putText(img, label, (10, y_label), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                y_label += 16

        # State combined score in bold
        cv2.putText(img, f"{sid} combined={val:.3f}",
                    (10, y_label), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        y_label += 22

    cv2.imwrite(output_path, img)
    return img
