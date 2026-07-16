#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LDPlayer Auto Input Switcher — 检测引擎

模块职责：
    capture.py       — 截图：窗口枚举 + dxcam 截取
    matcher.py       — 模板匹配：OpenCV matchTemplate + feature mask
    state_machine.py — 状态机：去抖 + 变化检测
    overlay.py       — Toast 覆盖层
    monitor.py       — 监控主循环：串联上述模块

用法：
    from src.detector import MonitorConfig, run_monitor_loop
"""

from .capture import (
    EMULATOR_PROCESS,
    TARGET_PROCESS,
    get_process_name,
    count_processes,
    find_visible_windows,
    get_dnplayer_client_rect,
    get_dnplayer_render_rect,
    get_dnplayer_hwnd,
    resolve_capture_target,
    capture_region,
    save_png,
)
from .matcher import (
    DEFAULT_DETECTION,
    create_feature_mask,
    compute_search_rect,
    match_template,
    match_multi,
    format_match_line,
    print_match_results,
    draw_debug_overlay,
)
from .state_machine import StateMachine, STATE_NONE
from .monitor import (
    MonitorConfig,
    MonitorThread,
    run_monitor_loop,
)
from .overlay import (
    show_toast,
    update_toast,
    destroy_toast,
    extract_key_name,
)

__all__ = [
    # capture
    "EMULATOR_PROCESS", "TARGET_PROCESS",
    "get_process_name", "count_processes", "find_visible_windows",
    "get_dnplayer_client_rect", "get_dnplayer_render_rect", "get_dnplayer_hwnd",
    "resolve_capture_target", "capture_region", "save_png",
    # matcher
    "DEFAULT_DETECTION", "create_feature_mask", "compute_search_rect",
    "match_template", "match_multi",
    "format_match_line", "print_match_results", "draw_debug_overlay",
    # state_machine
    "StateMachine", "STATE_NONE",
    # monitor
    "MonitorConfig", "MonitorThread", "run_monitor_loop",
    # overlay
    "show_toast", "update_toast", "destroy_toast", "extract_key_name",
]
