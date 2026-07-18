#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
监控主循环 — 截图 → 匹配 → 状态机 → 注入 → Toast

协调各模块，每 500ms 执行一轮检测与自动切换。

用法:
    from src.detector.monitor import MonitorConfig, run_monitor_loop
    from src.shared.injector import Injector

    injector = Injector("dist/keymap_injector.exe")
    config = MonitorConfig(
        injector=injector,
        states_config={...},
    )
    run_monitor_loop(config)
"""

import os
import time

from .capture import (
    EMULATOR_PROCESS,
    TARGET_PROCESS,
    resolve_capture_target,
    capture_region,
    save_png,
)
from .matcher import (
    match_multi,
    format_match_line,
    draw_debug_overlay,
    DEFAULT_DETECTION,
)
from .state_machine import StateMachine, STATE_NONE
from .overlay import show_toast, extract_key_name, update_toast, destroy_toast

import ctypes


# ---- 默认输出目录 ----
def _get_default_output_dir():
    """返回截图默认输出目录。PyInstaller 打包后指向 exe 同目录，开发环境指向项目根。"""
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "runTimeScreenShots")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "runTimeScreenShots",
    )

DEFAULT_OUTPUT_DIR = _get_default_output_dir()


class MonitorConfig:
    """监控循环配置（schema v2）。"""

    def __init__(self,
                 injector=None,
                 injector_path: str = None,
                 states_config: dict = None,
                 regions_config: dict = None,
                 detection_config: dict = None,
                 output_dir: str = None,
                 initial_state: str = None,
                 none_state_config: dict = None,
                 none_state_frames: int = 20,
                 disc_reset_enabled: bool = False,
                 poll_interval_ms: int = 333,
                 debounce_count: int = 1,
                 match_threshold: float = 0.75,
                 priorities: dict = None):
        """
        参数：
            injector:        Injector 实例 (推荐)
            injector_path:   keymap_injector.exe 路径 (兼容旧接口)
            states_config:   状态定义 (v2 格式)，格式：
                             {state_id: {"templates": [{"path": ..., "region": ...}, ...],
                                         "match_logic": "any"|"all",
                                         "keymap": path,
                                         "mouse_drag_key": int|None}, ...}
            regions_config:  命名区域池 {region_id: region_config} (v2)
            detection_config: matcher 检测参数，None 使用默认值
            output_dir:       截图/调试输出目录
            initial_state:    初始状态 ID，None 取第一个状态
            poll_interval_ms: 检测间隔毫秒
            debounce_count:   去抖帧数
            match_threshold:  匹配成功阈值
            priorities:       状态优先级 {state_id: int}，越大越优先，默认 0
        """
        # Injector 实例（延迟导入避免循环依赖）
        if injector is not None:
            self.injector = injector
        elif injector_path is not None:
            from src.shared.injector import Injector
            self.injector = Injector(injector_path)
        else:
            # 自动推断路径
            from src.shared.injector import Injector
            proj_root = os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
            self.injector = Injector(os.path.join(proj_root, "dist",
                                                  "keymap_injector.exe"))

        self.states_config = states_config or {}
        self.regions_config = regions_config or {}
        self.detection_config = detection_config or DEFAULT_DETECTION
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        # 初始状态：None 表示"未知"，首次检测到任何状态即切换按键
        # 之后仅在不同状态之间切换才触发
        self.initial_state = initial_state
        self.none_state_config = none_state_config  # None=禁用, dict=启用
        self.none_state_frames = none_state_frames  # 进入 none 的去抖帧数
        self.disc_reset_enabled = disc_reset_enabled
        self.poll_interval_ms = poll_interval_ms
        self.debounce_count = debounce_count
        self.match_threshold = match_threshold
        self.priorities = priorities or {}


# ---------------------------------------------------------------------------
# 分片 sleep，保持 Toast 事件循环
# ---------------------------------------------------------------------------
def _sleep_with_toast(duration: float):
    """分片 sleep，每 50ms 调用一次 update_toast() 以保持 Toast 渲染。"""
    end = time.time() + duration
    while time.time() < end:
        remaining = end - time.time()
        sleep_ms = min(remaining, 0.05)
        if sleep_ms > 0:
            time.sleep(sleep_ms)
        update_toast()


# ---------------------------------------------------------------------------
# MonitorThread — QThread 版本的监控循环
# ---------------------------------------------------------------------------

# 仅在 PySide6 可用时定义 MonitorThread
try:
    from PySide6.QtCore import QThread, Signal

    class MonitorThread(QThread):
        """后台监控线程，500ms 周期。

        信号 (→ GUI):
            status_changed(str, str):  (old_state_id, new_state_id)
            match_score(float):        当前帧最佳匹配率
            log_message(str):          日志/调试信息
            error_occurred(str):       错误信息
        """

        status_changed = Signal(str, str)
        match_score = Signal(float)
        log_message = Signal(str)
        error_occurred = Signal(str)

        def __init__(self, config: "MonitorConfig",
                     parent_hwnd=None,
                     show_toast: bool = True,
                     save_debug_screenshot: bool = False,
                     none_state_enabled: bool = False):
            """
            参数：
                config:                MonitorConfig 实例
                parent_hwnd:           LDPlayer 主窗口句柄 (Toast 定位)
                show_toast:            是否显示 Toast 覆盖层
                save_debug_screenshot: 是否保存调试截图 (debugScreenShot.png)
                none_state_enabled:    无匹配时切到首个 state 的按键（释放鼠标）
            """
            super().__init__()
            self._config = config
            self._parent_hwnd = parent_hwnd
            self._show_toast = show_toast
            self._save_debug_screenshot = save_debug_screenshot
            self._none_state_enabled = none_state_enabled
            self._running = False

        def run(self):
            """监控主循环（在独立线程中执行）。"""
            import cv2

            config = self._config
            injector = config.injector

            # 构建 state_configs 供新版 match_multi() 使用
            state_configs = []
            for sid, cfg in config.states_config.items():
                sc = {
                    "id": sid,
                    "templates": cfg["templates"],
                    "match_logic": cfg.get("match_logic", "any"),
                }
                for extra in ("negative_templates", "negative_penalty",
                              "min_pass_ratio"):
                    if extra in cfg:
                        sc[extra] = cfg[extra]
                state_configs.append(sc)

            none_allowed = (
                self._none_state_enabled
                and config.none_state_config is not None
            )
            sm = StateMachine(
                states=list(config.states_config.keys()),
                threshold=config.match_threshold,
                debounce_count=config.debounce_count,
                none_state_allowed=none_allowed,
                none_state_debounce=config.none_state_frames,
                priorities=config.priorities,
            )
            sm.reset(STATE_NONE if none_allowed else config.initial_state)

            self.log_message.emit(
                f"Monitor started: initial={sm.current}, "
                f"{config.poll_interval_ms}ms/frame, debounce={config.debounce_count} frames"
            )

            i = 0
            last_rect_size = None
            last_source = None
            _last_loaded_kmp = None  # 追踪当前已加载的 .kmp，避免冗余切换
            self._running = True

            while self._running:
                i += 1
                t0 = time.perf_counter()

                # 每轮重新获取窗口区域
                rect, source, _wins = resolve_capture_target(TARGET_PROCESS)
                if rect is None:
                    self.log_message.emit(f"[#{i}] Cannot get capture region, skip")
                    self.msleep(config.poll_interval_ms)
                    continue

                # 检测窗口尺寸变化
                current_size = (rect[2] - rect[0], rect[3] - rect[1])
                if last_rect_size is not None and current_size != last_rect_size:
                    self.log_message.emit(
                        f"[Resize] {last_rect_size[0]}x{last_rect_size[1]} "
                        f"→ {current_size[0]}x{current_size[1]}"
                    )
                last_rect_size = current_size

                if last_source is None:
                    self.log_message.emit(f"[Capture] {source}")
                last_source = source

                # 截图
                frame = capture_region(rect)
                if frame is None:
                    self.log_message.emit(f"[#{i}] Capture returned empty frame, skip")
                    self.msleep(config.poll_interval_ms)
                    continue

                # 保存（覆盖最新）
                latest_path = save_png(frame, config.output_dir, TARGET_PROCESS)

                # 匹配
                screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                results = match_multi(
                    screenshot_bgr, state_configs, config.regions_config,
                    detection_config=config.detection_config,
                    capture_source=source,
                )

                elapsed_ms = (time.perf_counter() - t0) * 1000

                # 发送最佳匹配率
                best_val = max(
                    (info["val"] for info in results.values()), default=0.0
                )
                self.match_score.emit(best_val)

                line = format_match_line(results, config.match_threshold)
                self.log_message.emit(
                    f"[#{i:>4d}] {elapsed_ms:6.1f}ms | {line}"
                )

                # ---- 状态判断与按键切换 ----
                changed, old_state, new_state = sm.update(results)

                if changed:
                    # 解析目标状态
                    if new_state == STATE_NONE:
                        ns = config.none_state_config
                        kmp = ns["keymap"] if ns else None
                    else:
                        state_cfg = config.states_config[new_state]
                        kmp = state_cfg["keymap"]

                    # 键位去重：.kmp 相同则跳过 injector 调用
                    if kmp is not None and kmp == _last_loaded_kmp:
                        self.log_message.emit(
                            f"[Skip] keymap unchanged, already at {new_state}"
                        )
                        self.status_changed.emit(old_state, new_state)
                        self._sleep_with_toast(config.poll_interval_ms / 1000.0)
                        continue

                    if kmp is not None and os.path.exists(kmp):
                        self.log_message.emit(
                            f"[Switch] {old_state} → {new_state}"
                        )

                        # 方向盘左键（game.json detection.disc_reset_enabled 控制）
                        disc_left_key = None
                        if config.disc_reset_enabled:
                            old_kmp = _last_loaded_kmp
                            if old_kmp and os.path.exists(old_kmp):
                                disc_left_key = injector.parse_kmp_disc_left_key(old_kmp)

                        # 切换前释放所有按下的按键
                        injector.release_held_keys()

                        # 执行切换
                        if injector.switch(kmp):
                            _last_loaded_kmp = kmp
                            self.status_changed.emit(old_state, new_state)

                            if self._show_toast and self._parent_hwnd is not None:
                                key_name = extract_key_name(kmp)
                                show_toast(key_name, self._parent_hwnd)

                            if self._parent_hwnd is not None:
                                try:
                                    import win32gui as _w32g
                                    _w32g.SetForegroundWindow(self._parent_hwnd)
                                except Exception:
                                    pass

                            # 切换后再释放一次按键
                            injector.release_held_keys()

                            # Mouse drag key: 从切换后的 .kmp 读 ClassMouseDrag
                            mouse_key = injector.parse_kmp_mouse_drag_key(kmp)
                            if mouse_key is not None:
                                if injector.is_mouse_captured():
                                    self.log_message.emit(
                                        f"[MouseDrag] skipped — already captured"
                                    )
                                else:
                                    injector.send_mouse_drag_key(mouse_key)
                                    self.log_message.emit(
                                        f"[MouseDrag] sent VK={mouse_key}"
                                    )

                            # 方向盘左键 tap — 重置 LDPlayer 方向状态机
                            if disc_left_key is not None:
                                key_name = chr(disc_left_key) if 0x20 <= disc_left_key < 0x7F else "?"
                                user32 = ctypes.windll.user32
                                user32.keybd_event(disc_left_key, 0, 0, 0)
                                import time as _disc_time
                                _disc_time.sleep(0.005)
                                user32.keybd_event(disc_left_key, 0, 2, 0)
                                self.log_message.emit(
                                    f"[DiscReset] tapped left key '{key_name}' vk={disc_left_key}"
                                )
                        else:
                            self.log_message.emit(
                                f"[Failed] injector.switch() returned False, rolling back"
                            )
                            sm.reset(old_state)
                    else:
                        self.log_message.emit(
                            f"[Skip] .kmp not found: {os.path.basename(kmp)}"
                        )
                        sm.reset(old_state)  # .kmp 缺失也回滚

                # 调试标注图
                if self._save_debug_screenshot:
                    debug_path = os.path.join(config.output_dir,
                                              "debugScreenShot.png")
                    draw_debug_overlay(
                        screenshot_bgr, results, debug_path,
                        config.detection_config.get("ref_capture_h", 1140)
                    )

                # 分片 sleep（QThread 安全）
                self._sleep_with_toast(config.poll_interval_ms / 1000.0)

            # 清理
            if self._show_toast:
                destroy_toast()
            self.log_message.emit(
                f"Monitor stopped, {i} rounds executed. Final state: {sm.current}"
            )

        def stop(self):
            """请求停止监控循环。"""
            self._running = False

        def _sleep_with_toast(self, duration: float):
            """分片 sleep，支持 Toast 更新（QThread 安全）。"""
            end = time.time() + duration
            while self._running and time.time() < end:
                remaining = end - time.time()
                sleep_ms = min(remaining, 0.05)
                if sleep_ms > 0:
                    self.msleep(int(sleep_ms * 1000))
                if self._show_toast:
                    update_toast()

        def is_running(self) -> bool:
            return self._running

except ImportError:
    # PySide6 不可用时，MonitorThread 不可用
    MonitorThread = None


# ---------------------------------------------------------------------------
# 监控主循环 (CLI 模式，单线程)
# ---------------------------------------------------------------------------
def run_monitor_loop(config: MonitorConfig,
                     no_debug: bool = False,
                     parent_hwnd=None):
    """持续截图+匹配+自动切换按键方案，直到 Ctrl+C。"""

    injector = config.injector

    # 构建 state_configs 供新版 match_multi() 使用
    state_configs = []
    for sid, cfg in config.states_config.items():
        sc = {
            "id": sid,
            "templates": cfg["templates"],
            "match_logic": cfg.get("match_logic", "any"),
        }
        for extra in ("negative_templates", "negative_penalty",
                      "min_pass_ratio"):
            if extra in cfg:
                sc[extra] = cfg[extra]
        state_configs.append(sc)

    # 初始化状态机
    sm = StateMachine(
        states=list(config.states_config.keys()),
        threshold=config.match_threshold,
        debounce_count=config.debounce_count,
        none_state_allowed=False,  # CLI 模式暂不支持
        priorities=config.priorities,
    )
    sm.reset(config.initial_state)
    print(f"[Monitor] Starting loop (initial: {sm.current}, {config.poll_interval_ms}ms/frame, "
          f"debounce={config.debounce_count} frames, Ctrl+C to stop)\n")

    i = 0
    last_rect_size = None
    last_source = None
    last_loaded_kmp = None  # 追踪当前已加载的 .kmp，避免冗余切换

    try:
        while True:
            i += 1
            t0 = time.perf_counter()

            # 每轮重新获取窗口区域
            rect, source, _wins = resolve_capture_target(TARGET_PROCESS)
            if rect is None:
                print(f"[#{i}] Cannot get capture region, skip")
                time.sleep(0.5)
                continue

            # 检测窗口尺寸变化
            current_size = (rect[2] - rect[0], rect[3] - rect[1])
            if last_rect_size is not None and current_size != last_rect_size:
                print(f"  [Resize] {last_rect_size[0]}x{last_rect_size[1]} "
                      f"→ {current_size[0]}x{current_size[1]}")
            last_rect_size = current_size

            # 检测截图来源变化
            if source != last_source and last_source is not None:
                print(f"  [Source change] \"{last_source}\" → \"{source}\"")
            elif last_source is None:
                print(f"  [Capture] {source}")
            last_source = source

            # 截图
            frame = capture_region(rect)
            if frame is None:
                print(f"[#{i}] Capture returned empty frame, skip")
                time.sleep(0.5)
                continue

            # 保存（覆盖最新）
            latest_path = save_png(frame, config.output_dir, TARGET_PROCESS)

            # 匹配
            import cv2
            screenshot_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            results = match_multi(
                screenshot_bgr, state_configs, config.regions_config,
                detection_config=config.detection_config,
                capture_source=source,
            )

            elapsed_ms = (time.perf_counter() - t0) * 1000

            # 一行输出
            line = format_match_line(results, config.match_threshold)
            prefix = f"[#{i:>4d}] {elapsed_ms:6.1f}ms |"

            # ---- 状态判断与按键切换 ----
            changed, old_state, new_state = sm.update(results)

            switch_info = ""
            if changed:
                state_cfg = config.states_config[new_state]
                kmp = state_cfg["keymap"]

                # 键位去重：目标 .kmp 与当前已加载的相同则跳过
                if kmp and kmp == last_loaded_kmp:
                    switch_info = f" [Skip] keymap unchanged, already at {new_state}"
                elif os.path.exists(kmp):
                    # 切换前释放所有按下的按键
                    injector.release_held_keys()
                    # 使用 Injector 执行切换
                    if injector.switch(kmp):
                        last_loaded_kmp = kmp  # 记录已加载的 .kmp
                        switch_info = f" [Switch] {old_state} → {new_state}"

                        # Toast first, then re-focus and send mouse_drag_key
                        key_name = extract_key_name(kmp)
                        print(f"[Switch] Showing Toast: kmp={os.path.basename(kmp)} "
                              f"→ key_name={key_name!r}", flush=True)
                        show_toast(key_name, parent_hwnd)

                        # Re-focus LDPlayer after toast (tk.Tk() may have stolen focus)
                        if parent_hwnd is not None:
                            try:
                                import win32gui as _w32g2
                                _w32g2.SetForegroundWindow(parent_hwnd)
                            except Exception:
                                pass

                        # 切换后再释放一次（某些 UI 场景下 keybd_event 在切换后更有效）
                        injector.release_held_keys()

                        # 发送 mouse drag key
                        mouse_key = state_cfg.get("mouse_drag_key")
                        if mouse_key is None:
                            mouse_key = injector.parse_kmp_mouse_drag_key(kmp)
                        if mouse_key is not None:
                            injector.send_mouse_drag_key(mouse_key)
                            switch_info += f" [MouseDrag] sent VK={mouse_key}"
                    else:
                        switch_info = " [Failed] injector.switch() returned False, rolling back"
                        sm.reset(old_state)
                else:
                    switch_info = (f" [Skip] .kmp not found: "
                                   f"{os.path.basename(kmp)}")
                    sm.reset(old_state)

            print(f"{prefix} {line}{switch_info}")

            # 调试标注图
            if not no_debug:
                stem = os.path.splitext(os.path.basename(latest_path))[0]
                debug_path = os.path.join(config.output_dir,
                                          f"{stem}_latest_debug.png")
                draw_debug_overlay(screenshot_bgr, results, debug_path,
                                   config.detection_config.get("ref_capture_h", 1140))

            # 分片 sleep，期间处理 Toast 事件循环
            _sleep_with_toast(config.poll_interval_ms / 1000.0)

    except KeyboardInterrupt:
        destroy_toast()
        print(f"\n[Monitor] Stopped, {i} rounds executed. Final state: {sm.current}")
