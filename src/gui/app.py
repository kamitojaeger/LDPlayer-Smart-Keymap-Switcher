#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
应用入口 — QApplication 初始化、单例检测、DPI 感知
"""

import os
import sys

from PySide6.QtCore import Qt, QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox


class App(QApplication):
    """应用主类，封装 QApplication 初始化 + 单例检测。

    用法:
        app = App(sys.argv, app_id="AutoInputSwitcher")
        if app.is_running:
            sys.exit(0)
        window = MainWindow(app)
        window.show()
        sys.exit(app.exec())
    """

    def __init__(self, argv: list, app_id: str = "AutoInputSwitcher",
                 lock_dir: str = None):
        """初始化应用。

        参数：
            argv:     命令行参数
            app_id:   应用唯一标识（用于单例检测）
            lock_dir: 锁文件目录，默认系统临时目录
        """
        super().__init__(argv)

        self.setApplicationName(app_id)
        self.setOrganizationName("LDPlayerTools")
        self.setApplicationVersion("1.0.0")

        # 单例检测
        self._lock_dir = lock_dir or os.environ.get("TEMP", os.path.expanduser("~"))
        os.makedirs(self._lock_dir, exist_ok=True)
        self._lock_file = QLockFile(
            os.path.join(self._lock_dir, f"{app_id}.lock")
        )
        self._lock_file.setStaleLockTime(0)
        self._is_running = not self._lock_file.tryLock(0)

        # 设置图标
        self._setup_icon()

    @property
    def is_running(self) -> bool:
        """是否已有实例在运行。"""
        return self._is_running

    def _setup_icon(self):
        """设置应用图标。"""
        # 使用内置样式，后续可替换为自定义图标
        self.setStyle("Fusion")
        self.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    def show_already_running_warning(self):
        """弹出「已在运行」警告。"""
        QMessageBox.warning(
            None,
            self.applicationName(),
            "应用已在运行中，请检查系统托盘。\n"
            "Application is already running. Check the system tray.",
        )

    def __del__(self):
        if hasattr(self, '_lock_file') and self._lock_file.isLocked():
            self._lock_file.unlock()


def get_project_root() -> str:
    """返回项目资源根目录。兼容 PyInstaller 打包。"""
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        return os.path.dirname(_sys.executable)
    return os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    ))
