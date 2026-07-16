#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LDPlayer Auto Input Switcher — 主入口 (GUI + CLI 双模式)

用法：
  python main.py                 # GUI 模式 (默认)
  python main.py --cli           # CLI 模式 (监控循环)
  python main.py --cli --game gtasa  # CLI + 指定游戏
  python main.py --cli --list-games  # CLI 列出游戏
  python main.py --match <png>       # CLI 对已有图片匹配
"""

import os
import sys
import json
import glob
import argparse
import shutil
import win32gui

# ---- 资源路径：PyInstaller 打包后数据目录在 exe 同路径，开发环境在脚本目录 ----
def _get_base_dir():
    """返回项目资源根目录。PyInstaller 打包后指向 exe 所在目录，开发环境指向脚本目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

_project_root = _get_base_dir()

# ---- 确保项目根在 sys.path ----
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def run_cli(args):
    """CLI 模式入口（兼容旧版行为）。"""
    import subprocess

    try:
        import cv2
    except ImportError as e:
        sys.exit(f"[Missing dependency] {e}\nInstall: pip install -r requirements.txt")

    from src.shared.config import GameConfig, AppSettings
    from src.shared.injector import Injector
    from src.shared.ldplayer import auto_detect
    from src.detector import (
        EMULATOR_PROCESS, TARGET_PROCESS,
        count_processes, get_dnplayer_hwnd, resolve_capture_target,
        match_multi, print_match_results, draw_debug_overlay,
        MonitorConfig, run_monitor_loop,
    )

    CONFIG_DIR = os.path.join(_project_root, "config")
    GAMES_DIR = os.path.join(_project_root, "games")
    SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
    VERSIONS_PATH = os.path.join(CONFIG_DIR, "ldplayer_versions.json")

    settings = AppSettings.load(SETTINGS_PATH)

    # 游戏列表
    games = GameConfig.scan_games(GAMES_DIR)
    if args.list_games:
        if not games:
            print("[Tip] No game configs found in games/")
        else:
            print(f"[Available games] {len(games)} total:")
            for g in games:
                print(f"  {os.path.basename(g.game_dir):15s} → {g.name} ({len(g.states)} states)")
        return

    # 选择游戏
    if args.game:
        game = next((g for g in games
                     if os.path.basename(g.game_dir) == args.game), None)
        if game is None:
            dirs = [os.path.basename(g.game_dir) for g in games]
            sys.exit(f"[Error] Game not found '{args.game}'. Available: {dirs or '(none)'}")
    elif games:
        game = games[0]
        print(f"[Auto-select] {game.name}")
    else:
        sys.exit("[Error] No game configs found in games/")

    # --match
    if args.match:
        screenshot = cv2.imread(args.match, cv2.IMREAD_COLOR)
        if screenshot is None:
            raise RuntimeError(f"Cannot read image: {args.match}")
        matcher_cfg = game.to_matcher_config()
        results = match_multi(
            screenshot, game.state_configs_for_matcher(), game.regions,
            detection_config=matcher_cfg, capture_source="",
        )
        print_match_results(results, matcher_cfg.get("match_threshold", 0.75))
        if not args.no_debug:
            base, ext = os.path.splitext(args.match)
            draw_debug_overlay(screenshot, results, f"{base}_debug{ext}",
                               matcher_cfg.get("ref_capture_h", 1140))
        return

    # 实例守卫
    dn_count = count_processes(EMULATOR_PROCESS)
    if dn_count == 0:
        raise RuntimeError("LDPlayer not running. Please start the emulator first.")
    if dn_count > 1:
        raise RuntimeError(f"Detected {dn_count} LDPlayer instances. Please keep only one.")

    # LDPlayer 检测
    ld_info = auto_detect(VERSIONS_PATH)
    if ld_info:
        print(f"[LDPlayer] {ld_info.version_name} @ {ld_info.install_path}")

    # 初始化注入器
    injector_path = settings.injector_path_override or \
        os.path.join(_project_root, "dist", "keymap_injector.exe")
    dll_path = settings.dll_path_override or \
        os.path.join(_project_root, "dist", "keymap_hook.dll")
    injector = Injector(injector_path, dll_path)
    if os.path.exists(injector_path):
        injector.init()
        import time
        time.sleep(0.2)

    dn_hwnd = get_dnplayer_hwnd()

    # 配置并启动监控
    config = game.to_monitor_config(
        injector_path=injector_path,
        poll_interval_ms=settings.poll_interval_ms,
        debounce_count=settings.debounce_count,
    )
    config.injector = injector

    run_monitor_loop(config, no_debug=args.no_debug, parent_hwnd=dn_hwnd)


def run_gui(args):
    """GUI 模式入口。"""
    # ---- DPI 感知 (必须在 PySide6 导入之前设置，否则 Qt 先占) ----
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QMessageBox

    from src.gui import App, MainWindow, SystemTray, SettingsDialog, AboutDialog
    from src.gui.app import get_project_root
    from src.shared.config import GameConfig, AppSettings
    from src.shared.injector import Injector
    from src.shared.ldplayer import auto_detect
    from src.shared.i18n import I18n
    from src.detector import count_processes, get_dnplayer_hwnd, EMULATOR_PROCESS
    from src.detector.monitor import MonitorThread

    _ = get_project_root

    CONFIG_DIR = os.path.join(_project_root, "config")
    GAMES_DIR = os.path.join(_project_root, "games")
    LOCALE_DIR = os.path.join(_project_root, "locales")

    # ── 初始化 App -─
    app = App(sys.argv, app_id="AutoInputSwitcher")
    if app.is_running:
        app.show_already_running_warning()
        sys.exit(0)

    # ── 加载设置 & i18n ──
    SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
    settings = AppSettings.load(SETTINGS_PATH)

    i18n = I18n(LOCALE_DIR)
    lang = settings._data.get("gui", {}).get("language", "")
    if not lang:
        lang = I18n.detect_system_language()
        settings._data.setdefault("gui", {})["language"] = lang
    i18n.load(lang)

    # ── 扫描游戏 ──
    games = GameConfig.scan_games(GAMES_DIR)
    if not games:
        QMessageBox.warning(None, i18n.t("app.title"),
                            i18n.t("error.no_games"))
        sys.exit(1)

    # ── LDPlayer 检测 ──
    ld_info = auto_detect(os.path.join(CONFIG_DIR, "ldplayer_versions.json"))

    # ── 初始化注入器 ──
    injector_path = settings.injector_path_override or \
        os.path.join(_project_root, "dist", "keymap_injector.exe")
    dll_path = settings.dll_path_override or \
        os.path.join(_project_root, "dist", "keymap_hook.dll")
    injector = Injector(injector_path, dll_path)

    # ── 创建主窗口 ──
    window = MainWindow(i18n)

    # 游戏列表
    game_list = [(g.name, g) for g in games]
    window.set_games(game_list)

    # ── 创建系统托盘 ──
    tray = SystemTray(i18n)
    tray.set_language_state(lang)

    # ── MonitorThread 引用 ──
    monitor_thread = [None]  # mutable container
    dn_hwnd = [None]

    def _prepare_keymap_environment(game_config):
        """准备按键环境 — dir_kmps.dir 过滤 + .kmp 复制 + 旧按键清理。

           返回 True 表示修改了磁盘文件，需要重启 LDPlayer。
        """
        emu_path = settings.ldplayer_install_path or \
            (ld_info.install_path if ld_info else None)
        if not emu_path:
            return False

        need_restart = False
        packages = game_config.package
        cust_dir = os.path.join(emu_path, "vms", "customizeConfigs")

        # ── 1. dir_kmps.dir: 删除匹配游戏包名的条目 ──
        dir_path = os.path.join(emu_path, "vms", "recommendConfigs",
                                "dir_kmps.dir")
        if packages and os.path.isfile(dir_path):
            with open(dir_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            before = len(data["kmps"])
            data["kmps"] = [k for k in data["kmps"]
                           if not any(pkg in k.get("packageNamePattern", "")
                                     for pkg in packages)]
            if len(data["kmps"]) < before:
                with open(dir_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                need_restart = True

        # ── 2. 复制 games/<game>/keymaps/ 前 2 个 .kmp 到 customizeConfigs ──
        #     已有同名文件跳过；新增文件需重启 LDPlayer
        src_files = game_config.keymap_paths()[:2]
        our_names = set()
        if src_files and os.path.isdir(cust_dir):
            for src in src_files:
                bn = os.path.basename(src)
                our_names.add(bn)
                dst = os.path.join(cust_dir, bn)
                if os.path.isfile(dst):
                    continue  # 已有，跳过
                try:
                    shutil.copy2(src, dst)
                    need_restart = True  # 新增文件需要重启
                except Exception:
                    pass

        # ── 3. 清理 customizeConfigs 中该游戏的其他 .kmp ──
        # 通过 .smp 文件判断哪些 .kmp 属于当前游戏
        moved = 0
        if packages:
            for smp_path in glob.glob(os.path.join(cust_dir, "*.smp")):
                smp_bn = os.path.basename(smp_path)
                # .smp 文件名通常以包名开头
                if not any(pkg in smp_bn for pkg in packages):
                    continue

                try:
                    with open(smp_path, "r", encoding="utf-8") as f:
                        smp = json.load(f)
                except Exception:
                    continue

                # 收集该 .smp 引用的 .kmp
                kmp_names = set()
                for res_data in smp.get("resolutionRelatives", {}).values():
                    kid = res_data.get("keyboardId", "")
                    if kid:
                        kmp_names.add(kid)
                        # 也可能只是文件名不含路径
                        kmp_names.add(os.path.basename(kid))

                # 移动不在我们列表中的 .kmp
                for kname in kmp_names:
                    if kname in our_names:
                        continue
                    kmp_path = os.path.join(cust_dir, kname)
                    if os.path.isfile(kmp_path):
                        backup_dir = os.path.join(cust_dir,
                                                  "userCustomizeKeymapBackup")
                        os.makedirs(backup_dir, exist_ok=True)
                        shutil.move(kmp_path, os.path.join(backup_dir, kname))
                        moved += 1

        if moved > 0:
            need_restart = True

        return need_restart

    # ── 连接信号 ──

    def on_start():
        # 检查 LDPlayer
        proc_count = count_processes(EMULATOR_PROCESS)
        if proc_count == 0:
            QMessageBox.warning(window, i18n.t("main.error"),
                                i18n.t("error.no_ldplayer"))
            return
        if proc_count > 1:
            QMessageBox.warning(window, i18n.t("main.error"),
                                i18n.t("error.multi_instance"))
            return

        # 获取当前选中游戏
        game_config = window._game_panel.current_data()
        if game_config is None:
            return

        # ── 准备按键环境 (dir_kmps.dir 过滤 + .kmp 复制 + 旧按键清理) ──
        if _prepare_keymap_environment(game_config):
            QMessageBox.information(
                window, i18n.t("app.title"),
                i18n.t("error.dir_kmps_filtered")
            )
            return  # 不运行监控，需要重启 LDPlayer

        # 获取 LDPlayer 窗口句柄
        hwnd = get_dnplayer_hwnd()
        dn_hwnd[0] = hwnd

        # 初始化注入器
        if os.path.exists(injector_path):
            injector.init()
            # 额外等待 200ms 确保 DLL hook 完全就绪
            import time
            time.sleep(0.2)

        # 创建 MonitorConfig
        config = game_config.to_monitor_config(
            injector_path=injector_path,
            poll_interval_ms=settings.poll_interval_ms,
            debounce_count=settings.debounce_count,
        )
        config.injector = injector

        # 创建 MonitorThread
        show_toast = settings.show_toast
        save_debug = settings.save_debug_screenshot
        thread = MonitorThread(config, parent_hwnd=hwnd,
                               show_toast=show_toast,
                               save_debug_screenshot=save_debug,
                               none_state_enabled=settings.none_state_switch)
        thread.status_changed.connect(window.on_status_changed)
        thread.match_score.connect(window.on_match_score)
        thread.log_message.connect(window.on_log)
        thread.error_occurred.connect(window.on_error)
        thread.finished.connect(on_monitor_stopped)
        monitor_thread[0] = thread

        # 先把焦点切换到 LDPlayer，再启动监控线程
        # 否则首次检测+切换时 LDPlayer 还没获得焦点，mouse_drag_key 可能被焦点切换打断
        import time as _time
        if hwnd:
            try:
                win32gui.SetForegroundWindow(hwnd)
                _time.sleep(0.3)   # 等待焦点变更完全生效
            except Exception:
                pass

        thread.start()
        window.set_monitoring(True)
        tray.set_monitoring(True)
        window._log(f"Monitor started — Game: {game_config.name}")

    def on_stop():
        if monitor_thread[0] is not None:
            monitor_thread[0].stop()
            monitor_thread[0].wait(3000)  # 等待最多 3 秒
            if monitor_thread[0].isRunning():
                monitor_thread[0].terminate()
            monitor_thread[0] = None
        window.set_monitoring(False)
        tray.set_monitoring(False)
        window._log("Monitor stopped")

    def on_monitor_stopped():
        window.set_monitoring(False)
        tray.set_monitoring(False)

    def on_show():
        window.show()
        window.raise_()
        window.activateWindow()
        # 强制置顶到 Windows 前台（仅 raise/activate 在 Windows 上不够可靠）
        try:
            win32gui.SetForegroundWindow(int(window.winId()))
        except Exception:
            pass

    def on_language_changed(lang_code):
        i18n.load(lang_code)
        window.refresh_ui()
        tray.refresh_ui()
        tray.set_language_state(lang_code)
        settings._data.setdefault("gui", {})["language"] = lang_code
        settings.save(SETTINGS_PATH)

    def on_settings():
        dlg = SettingsDialog(settings, ld_info, i18n, window)
        dlg.language_changed.connect(on_language_changed)
        if dlg.exec():
            settings.save(SETTINGS_PATH)
            window.refresh_ui()
            tray.refresh_ui()

    def on_about():
        dlg = AboutDialog(i18n, window)
        dlg.exec()

    def on_exit():
        on_stop()
        tray.hide()
        app.quit()

    # ── 连接窗口信号 ──
    window.start_requested.connect(on_start)
    window.stop_requested.connect(on_stop)
    window.settings_requested.connect(on_settings)
    window.about_requested.connect(on_about)

    # ── 连接托盘信号 ──
    tray.show_requested.connect(on_show)
    tray.start_requested.connect(on_start)
    tray.stop_requested.connect(on_stop)
    tray.exit_requested.connect(on_exit)
    tray.language_changed.connect(on_language_changed)

    # ── 显示托盘 ──
    tray.show()

    # ── 启动时行为 ──
    if not settings._data.get("gui", {}).get("start_minimized", False):
        window.show()
        window.raise_()
        window.activateWindow()
        try:
            win32gui.SetForegroundWindow(int(window.winId()))
        except Exception:
            pass
    else:
        tray.show_message(i18n.t("app.title"),
                          i18n.t("tray.hide"))

    sys.exit(app.exec())


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LDPlayer 按键方案自动切换工具",
    )
    parser.add_argument("--cli", action="store_true",
                        help="命令行模式 (默认 GUI)")
    parser.add_argument("--game", help="游戏 ID")
    parser.add_argument("--list", action="store_true", help="仅列出窗口")
    parser.add_argument("--list-games", action="store_true", help="列出可用游戏")
    parser.add_argument("--match", metavar="PATH", help="对已有图片匹配")
    parser.add_argument("--no-debug", action="store_true", help="不生成调试图")

    args = parser.parse_args()

    if args.cli:
        run_cli(args)
    else:
        run_gui(args)
