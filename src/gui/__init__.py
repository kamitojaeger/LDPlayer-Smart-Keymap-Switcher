#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GUI 层 — PySide6 图形界面

模块职责：
    app.py             — QApplication 初始化 + 单例检测 + DPI
    main_window.py     — 主窗口布局
    game_panel.py      — 游戏下拉框 + 状态指示器
    system_tray.py     — 系统托盘 + 右键菜单
    settings_dialog.py — 设置对话框
    about_dialog.py    — 关于对话框
"""

from .app import App, get_project_root
from .main_window import MainWindow
from .game_panel import GamePanel
from .system_tray import SystemTray
from .settings_dialog import SettingsDialog
from .about_dialog import AboutDialog

__all__ = [
    "App", "get_project_root",
    "MainWindow",
    "GamePanel",
    "SystemTray",
    "SettingsDialog",
    "AboutDialog",
]
