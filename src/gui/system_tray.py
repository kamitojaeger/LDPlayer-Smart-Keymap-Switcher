#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
系统托盘 — 托盘图标 + 右键菜单
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction


class SystemTray(QSystemTrayIcon):
    """系统托盘，含右键菜单。

    信号:
        show_requested:    显示主窗口
        start_requested:   启动监控
        stop_requested:    停止监控
        exit_requested:    退出应用
        language_changed(str):  语言切换
    """

    show_requested = Signal()
    start_requested = Signal()
    stop_requested = Signal()
    exit_requested = Signal()
    language_changed = Signal(str)

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self._i18n = i18n
        self._init_ui()

    def _init_ui(self):
        # 图标：使用系统默认图标作为占位，后续可替换
        self.setIcon(self._create_default_icon())

        # 右键菜单
        self._menu = QMenu()

        self._show_action = QAction("Show", self._menu)
        self._show_action.triggered.connect(self.show_requested.emit)
        self._menu.addAction(self._show_action)

        self._menu.addSeparator()

        self._start_action = QAction("Start", self._menu)
        self._start_action.triggered.connect(self.start_requested.emit)
        self._menu.addAction(self._start_action)

        self._stop_action = QAction("Stop", self._menu)
        self._stop_action.setEnabled(False)
        self._stop_action.triggered.connect(self.stop_requested.emit)
        self._menu.addAction(self._stop_action)

        self._menu.addSeparator()

        # 语言子菜单
        self._lang_menu = QMenu("Language", self._menu)
        self._lang_zh = QAction("中文", self._lang_menu, checkable=True)
        self._lang_zh.triggered.connect(lambda: self._switch_lang("zh_CN"))
        self._lang_en = QAction("English", self._lang_menu, checkable=True)
        self._lang_en.triggered.connect(lambda: self._switch_lang("en_US"))
        self._lang_menu.addAction(self._lang_zh)
        self._lang_menu.addAction(self._lang_en)
        self._menu.addMenu(self._lang_menu)

        self._menu.addSeparator()

        self._exit_action = QAction("Exit", self._menu)
        self._exit_action.triggered.connect(self.exit_requested.emit)
        self._menu.addAction(self._exit_action)

        self.setContextMenu(self._menu)

        # 左键点击显示主窗口
        self.activated.connect(self._on_activated)

    def _switch_lang(self, lang: str):
        self._lang_zh.setChecked(lang == "zh_CN")
        self._lang_en.setChecked(lang == "en_US")
        self.language_changed.emit(lang)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # 左键单击
            self.show_requested.emit()

    def set_monitoring(self, active: bool):
        """更新监控状态（启用/禁用开始/停止菜单项）。"""
        self._start_action.setEnabled(not active)
        self._stop_action.setEnabled(active)
        self._start_action.setText(
            self._i18n.t("tray.start") + (" ✓" if not active else "")
        )

    def set_language_state(self, lang: str):
        """更新语言菜单选中状态。"""
        self._lang_zh.setChecked(lang == "zh_CN")
        self._lang_en.setChecked(lang == "en_US")

    def refresh_ui(self):
        """刷新 UI 文本。"""
        i = self._i18n
        self.setToolTip(i.t("tray.tooltip"))
        self._show_action.setText(i.t("tray.show"))
        self._start_action.setText(i.t("tray.start"))
        self._stop_action.setText(i.t("tray.stop"))
        self._exit_action.setText(i.t("tray.exit"))
        self._lang_menu.setTitle(i.t("settings.language"))

    def show_message(self, title: str, msg: str):
        """显示托盘气泡通知。"""
        self.showMessage(title, msg, QSystemTrayIcon.Information, 3000)

    @staticmethod
    def _create_default_icon() -> QIcon:
        """创建默认图标（简单的蓝色方块 + S 文字）。"""
        from PySide6.QtGui import QPixmap, QPainter, QColor
        from PySide6.QtCore import QRect

        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 蓝色圆角背景
        painter.setBrush(QColor("#1976d2"))
        painter.setPen(QColor("#1565c0"))
        painter.drawRoundedRect(QRect(4, 4, 56, 56), 12, 12)

        # 白色 S 文字
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setPixelSize(32)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(4, 4, 56, 56), 0x0084, "S")  # AlignCenter

        painter.end()
        return QIcon(pixmap)
