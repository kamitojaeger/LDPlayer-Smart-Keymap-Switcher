#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
关于对话框 — 版本号 + 开源声明
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
)
from PySide6.QtGui import QFont


class AboutDialog(QDialog):
    """关于对话框。"""

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self._i18n = i18n
        self._init_ui()

    def _init_ui(self):
        i = self._i18n
        self.setWindowTitle(i.t("about.title"))
        self.setFixedSize(380, 260)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # 标题
        title = QLabel(i.t("app.title"))
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 版本
        version = QLabel(f"v{i.t('app.version')}")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #888;")
        layout.addWidget(version)

        layout.addSpacing(8)

        # 描述
        desc = QLabel(i.t("about.description"))
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(4)

        # 技术栈
        tech = QLabel(i.t("about.tech_stack"))
        tech.setAlignment(Qt.AlignCenter)
        tech.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(tech)

        # 许可
        lic = QLabel(i.t("about.license"))
        lic.setAlignment(Qt.AlignCenter)
        lic.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(lic)

        layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton(i.t("about.close"))
        close_btn.clicked.connect(self.accept)
        close_btn.setMinimumHeight(32)
        layout.addWidget(close_btn)
