#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主窗口 — 布局：标题栏 + 游戏面板 + 控制按钮 + 日志区
"""

import os

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QPlainTextEdit, QGroupBox,
    QSizePolicy, QMessageBox,
)
from PySide6.QtGui import QFont, QCloseEvent


class MainWindow(QMainWindow):
    """应用主窗口。

    信号:
        start_requested:  用户点击启动
        stop_requested:   用户点击停止
        settings_requested: 请求打开设置对话框
        about_requested:   请求打开关于对话框
    """

    start_requested = Signal()
    stop_requested = Signal()
    settings_requested = Signal()
    about_requested = Signal()
    game_changed = Signal(int)       # 游戏下拉框变更 (index)

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self._i18n = i18n
        self._monitoring = False
        self._init_ui()
        self._translate_ui()

    def _init_ui(self):
        """构建 UI 布局。"""
        self.setWindowTitle("Auto Input Switcher")
        self.setMinimumSize(520, 480)
        self.resize(580, 500)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── 标题 ──
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self._title_label = QLabel("Auto Input Switcher")
        self._title_label.setFont(title_font)
        self._title_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self._title_label)

        # ── 游戏面板 ──
        game_group = QGroupBox()
        game_layout = QVBoxLayout(game_group)

        from .game_panel import GamePanel
        self._game_panel = GamePanel(self._i18n)
        self._game_panel.game_changed.connect(self.game_changed.emit)
        game_layout.addWidget(self._game_panel)
        root.addWidget(game_group)

        # ── 状态指示 ──
        status_layout = QHBoxLayout()
        status_layout.setSpacing(16)

        self._status_label = QLabel("●")
        self._status_label.setStyleSheet("color: gray; font-size: 16px;")
        self._status_text = QLabel("Not Monitoring")
        status_font = QFont()
        status_font.setPointSize(11)
        self._status_text.setFont(status_font)

        self._match_label = QLabel("")
        self._match_label.setFont(status_font)

        status_layout.addWidget(self._status_label)
        status_layout.addWidget(self._status_text)
        status_layout.addStretch()
        status_layout.addWidget(self._match_label)
        root.addLayout(status_layout)

        # ── 控制按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self._start_btn = QPushButton("▶  Start")
        self._start_btn.setMinimumHeight(40)
        self._start_btn.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; "
            "border-radius: 4px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #388e3c; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self._start_btn.clicked.connect(self._on_start)

        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setMinimumHeight(40)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(
            "QPushButton { background-color: #c62828; color: white; "
            "border-radius: 4px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #d32f2f; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self._stop_btn.clicked.connect(self._on_stop)

        btn_layout.addStretch()
        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._stop_btn)
        btn_layout.addStretch()
        root.addLayout(btn_layout)

        # ── 日志区 ──
        log_group = QGroupBox()
        log_layout = QVBoxLayout(log_group)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(500)
        self._log_view.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self._log_view)
        root.addWidget(log_group)

        # ── 底部 ──
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setFixedSize(36, 36)
        self._settings_btn.setToolTip("Settings")
        self._settings_btn.clicked.connect(self.settings_requested.emit)

        self._about_btn = QPushButton("ⓘ")
        self._about_btn.setFixedSize(36, 36)
        self._about_btn.setToolTip("About")
        self._about_btn.clicked.connect(self.about_requested.emit)

        footer_layout.addWidget(self._settings_btn)
        footer_layout.addWidget(self._about_btn)
        footer_layout.addStretch()

        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet("color: #888;")
        footer_layout.addWidget(version_label)

        root.addLayout(footer_layout)

    def _translate_ui(self):
        """刷新 UI 文本（语言切换时调用）。"""
        i = self._i18n
        self.setWindowTitle(i.t("app.title"))
        self._title_label.setText(i.t("app.title"))
        self._start_btn.setText(i.t("main.start"))
        self._stop_btn.setText(i.t("main.stop"))
        self._log_view.setPlaceholderText(i.t("main.not_monitoring"))
        self._game_panel.refresh_ui()

        if not self._monitoring:
            self._status_text.setText(i.t("main.not_monitoring"))
            self._match_label.setText("")
            self._status_label.setStyleSheet("color: gray; font-size: 16px;")

    def refresh_ui(self):
        """完整刷新 UI（语言切换 + 状态）。"""
        self._translate_ui()

    def set_games(self, games: list):
        """设置游戏列表 [(name, index), ...]"""
        self._game_panel.set_games(games)

    def current_game_index(self) -> int:
        """当前选中的游戏索引。"""
        return self._game_panel.current_index()

    @property
    def monitoring(self) -> bool:
        return self._monitoring

    def set_monitoring(self, active: bool):
        """切换监控状态，更新按钮和状态指示。"""
        self._monitoring = active
        if active:
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
            self._game_panel.setEnabled(False)
            self._status_label.setStyleSheet("color: #4caf50; font-size: 16px;")
        else:
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
            self._game_panel.setEnabled(True)
            self._status_label.setStyleSheet("color: gray; font-size: 16px;")
            self._status_text.setText(self._i18n.t("main.not_monitoring"))
            self._match_label.setText("")

    @Slot(str, str)
    def on_status_changed(self, old_state: str, new_state: str):
        """状态变化回调（来自 MonitorThread）。"""
        state_name = self._i18n.t(f"state.{new_state}")
        self._status_text.setText(f"{self._i18n.t('main.status')}{state_name}")
        self._log(f"State switch: {old_state} → {new_state} ({state_name})")

    @Slot(float)
    def on_match_score(self, score: float):
        """匹配率回调（来自 MonitorThread）。"""
        self._match_label.setText(
            f"{self._i18n.t('main.match_rate')}{score:.4f}"
        )

    @Slot(str)
    def on_error(self, msg: str):
        """错误回调（来自 MonitorThread）。"""
        self._log(f"[ERROR] {msg}", error=True)
        QMessageBox.warning(self, self._i18n.t("main.error"), msg)

    @Slot(str)
    def on_log(self, msg: str):
        """日志回调（来自 MonitorThread）。"""
        self._log(msg)

    def _on_start(self):
        self.start_requested.emit()

    def _on_stop(self):
        self.stop_requested.emit()

    def _log(self, msg: str, error: bool = False):
        """向日志区追加一行。"""
        from PySide6.QtGui import QTextCursor
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        if error:
            cursor.insertHtml(f'<span style="color:#ef5350">{msg}</span><br>')
        else:
            cursor.insertText(msg + "\n")
        self._log_view.setTextCursor(cursor)
        self._log_view.ensureCursorVisible()

    def closeEvent(self, event: QCloseEvent):
        """关闭窗口 → 最小化到托盘。"""
        event.ignore()
        self.hide()
