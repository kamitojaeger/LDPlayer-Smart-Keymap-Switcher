#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
游戏面板 — 游戏选择下拉框 + 刷新按钮
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout,
    QComboBox, QPushButton, QLabel,
)


class GamePanel(QWidget):
    """游戏选择面板。

    信号:
        game_changed(int): 选中游戏索引变化
    """

    game_changed = Signal(int)

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self._i18n = i18n
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标签
        self._label = QLabel("Game: ")
        layout.addWidget(self._label)

        # 下拉框
        self._combo = QComboBox()
        self._combo.setMinimumWidth(200)
        self._combo.currentIndexChanged.connect(self.game_changed.emit)
        layout.addWidget(self._combo, 1)

        # 刷新按钮
        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setFixedSize(32, 32)
        self._refresh_btn.setToolTip("Refresh game list")
        layout.addWidget(self._refresh_btn)

    def set_games(self, games: list):
        """设置游戏列表 [(display_name, data), ...]"""
        current = self._combo.currentData()
        self._combo.blockSignals(True)
        self._combo.clear()
        for name, data in games:
            self._combo.addItem(name, data)
        # 恢复选中
        if current is not None:
            idx = self._combo.findData(current)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)

    def current_index(self) -> int:
        return self._combo.currentIndex()

    def select_by_name(self, name: str):
        """根据 display name 设置选中项。"""
        idx = self._combo.findText(name)
        if idx >= 0:
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(idx)
            self._combo.blockSignals(False)

    def current_data(self):
        """返回当前选中项的 data（GameConfig 对象）。"""
        return self._combo.currentData()

    def refresh_ui(self):
        """刷新 UI 文本。"""
        self._label.setText(self._i18n.t("game.label"))
        self._refresh_btn.setToolTip(self._i18n.t("game.refresh"))

    def setEnabled(self, enabled: bool):
        """启用/禁用面板。"""
        super().setEnabled(enabled)
        self._combo.setEnabled(enabled)
        self._refresh_btn.setEnabled(enabled)
