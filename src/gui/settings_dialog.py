#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设置对话框 — 检测参数 + LDPlayer 路径 + 语言切换
"""

import os

from PySide6.QtCore import Signal, QObject, QEvent, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QWidget, QLabel, QSpinBox, QDoubleSpinBox,
    QLineEdit, QPushButton, QCheckBox, QComboBox,
    QFileDialog, QDialogButtonBox, QMessageBox,
)


class _SpinBoxClampFilter(QObject):
    """Event filter: 焦点离开或按 Enter 时，将手动输入的值钳制到 spinbox 范围。

    Qt 默认行为：当用户手动输入超出范围的值（如 min=200 时输入 150），
    focusOutEvent 调用 interpret() 发现 hasAcceptableInput()==False，
    不更新内部值，然后 updateEdit() 把显示恢复为旧值——用户感觉值"闪回"了。

    本过滤器在 Qt 处理 FocusOut/Enter 之前，先把 lineEdit 文本钳制到
    [min, max]，这样 Qt 的 interpret() 就能接受文本并正常提交。
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusOut:
            self._clamp_to_range(obj)
        elif event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._clamp_to_range(obj)
        return False  # 不消费事件，让 Qt 默认处理器继续运行

    @staticmethod
    def _clamp_to_range(spin):
        line_edit = spin.lineEdit()
        text = line_edit.text()

        # 去除前缀/后缀
        prefix = spin.prefix()
        suffix = spin.suffix()
        if prefix and text.startswith(prefix):
            text = text[len(prefix):]
        if suffix and text.endswith(suffix):
            text = text[:len(text) - len(suffix)]
        text = text.strip()

        if not text:
            return  # 空文本，交给 Qt 处理（恢复旧值）

        try:
            if isinstance(spin, QDoubleSpinBox):
                val = float(text)
                is_float = True
            else:
                val = int(text)
                is_float = False
        except ValueError:
            return  # 非数字，交给 Qt 处理

        lo = spin.minimum()
        hi = spin.maximum()

        if lo <= val <= hi:
            return  # 在范围内，Qt 会正常提交

        # 钳制到最近边界
        clamped = max(lo, min(hi, val))

        if is_float:
            new_text = f"{clamped:.{spin.decimals()}f}"
        else:
            new_text = str(int(clamped))

        # 重写 lineEdit 文本（含前缀/后缀），让 Qt 的 interpret() 接受
        line_edit.setText(f"{prefix}{new_text}{suffix}")


class SettingsDialog(QDialog):
    """应用设置对话框。

    信号:
        settings_changed:  设置已保存
        language_changed(str): 语言切换
    """

    settings_changed = Signal()
    language_changed = Signal(str)

    def __init__(self, settings, ldplayer_info, i18n, parent=None):
        """
        参数：
            settings:       AppSettings 实例
            ldplayer_info:  LDPlayerInfo 实例 (可为 None)
            i18n:           I18n 实例
        """
        super().__init__(parent)
        self._settings = settings
        self._ld_info = ldplayer_info
        self._i18n = i18n
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        i = self._i18n
        self.setWindowTitle(i.t("settings.title"))
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)

        # 标签页
        tabs = QTabWidget()

        # ── 通用 ──
        gen_tab = QWidget()
        gen_form = QFormLayout(gen_tab)
        gen_form.setSpacing(10)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(50, 2000)
        self._interval_spin.setSuffix(" ms")
        gen_form.addRow(i.t("settings.poll_interval"), self._interval_spin)

        self._debounce_spin = QSpinBox()
        self._debounce_spin.setRange(1, 10)
        gen_form.addRow(i.t("settings.debounce_count"), self._debounce_spin)

        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.5, 0.99)
        self._threshold_spin.setSingleStep(0.05)
        self._threshold_spin.setDecimals(2)
        gen_form.addRow(i.t("settings.match_threshold"), self._threshold_spin)

        self._toast_check = QCheckBox()
        gen_form.addRow(i.t("settings.show_toast"), self._toast_check)

        self._toast_duration = QSpinBox()
        self._toast_duration.setRange(1000, 10000)
        self._toast_duration.setSingleStep(500)
        self._toast_duration.setSuffix(" ms")
        gen_form.addRow(i.t("settings.toast_duration"), self._toast_duration)

        self._debug_check = QCheckBox()
        gen_form.addRow(i.t("settings.show_debug"), self._debug_check)

        self._save_debug_check = QCheckBox()
        gen_form.addRow(i.t("settings.save_debug_screenshot"), self._save_debug_check)

        self._none_state_check = QCheckBox()
        self._none_state_spin = QSpinBox()
        self._none_state_spin.setRange(1, 999999)
        self._none_state_spin.setValue(20)
        self._none_state_spin.setSuffix(" " + i.t("settings.none_state_frames_unit"))
        none_row = QHBoxLayout()
        none_row.addWidget(self._none_state_check)
        none_row.addWidget(self._none_state_spin)
        none_row.addStretch()
        none_widget = QWidget()
        none_widget.setLayout(none_row)
        gen_form.addRow(i.t("settings.none_state_enabled"), none_widget)

        # 关闭行为
        self._minimize_tray_check = QCheckBox()
        gen_form.addRow(i.t("settings.minimize_to_tray"), self._minimize_tray_check)

        # 语言
        self._lang_combo = QComboBox()
        self._lang_combo.addItem("中文", "zh_CN")
        self._lang_combo.addItem("English", "en_US")
        gen_form.addRow(i.t("settings.language"), self._lang_combo)

        tabs.addTab(gen_tab, i.t("settings.general"))

        # ── LDPlayer ──
        ld_tab = QWidget()
        ld_layout = QVBoxLayout(ld_tab)
        ld_form = QFormLayout()
        ld_form.setSpacing(10)

        path_layout = QHBoxLayout()
        self._ld_path_edit = QLineEdit()
        self._ld_path_edit.setReadOnly(True)
        path_layout.addWidget(self._ld_path_edit)

        self._browse_btn = QPushButton(i.t("settings.browse"))
        self._browse_btn.clicked.connect(self._on_browse_ld)
        path_layout.addWidget(self._browse_btn)

        self._auto_detect_btn = QPushButton(i.t("settings.auto_detect"))
        self._auto_detect_btn.clicked.connect(self._on_auto_detect)
        path_layout.addWidget(self._auto_detect_btn)

        ld_form.addRow(i.t("settings.ldplayer_path"), path_layout)

        # 版本信息（只读）
        self._ld_version_label = QLabel("")
        ld_form.addRow("", self._ld_version_label)

        ld_layout.addLayout(ld_form)
        ld_layout.addStretch()
        tabs.addTab(ld_tab, i.t("settings.ldplayer"))

        # ── 高级 ──
        adv_tab = QWidget()
        adv_form = QFormLayout(adv_tab)
        adv_form.setSpacing(10)

        self._injector_edit = QLineEdit()
        adv_form.addRow(i.t("settings.injector_path"), self._injector_edit)

        self._dll_edit = QLineEdit()
        adv_form.addRow(i.t("settings.dll_path"), self._dll_edit)

        tabs.addTab(adv_tab, i.t("settings.advanced"))

        root.addWidget(tabs)

        # 安装钳制过滤器：防止手动输入超范围值时 Qt 静默回退到旧值
        self._clamp_filter = _SpinBoxClampFilter()
        for spin in (self._interval_spin, self._debounce_spin,
                     self._threshold_spin, self._toast_duration):
            spin.installEventFilter(self._clamp_filter)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_values(self):
        """从 AppSettings 加载当前值到 UI。"""
        s = self._settings

        # 通用
        self._interval_spin.setValue(s.poll_interval_ms)
        self._debounce_spin.setValue(s.debounce_count)
        self._threshold_spin.setValue(
            self._settings._data.get("monitor", {}).get("match_threshold", 0.75)
        )
        self._toast_check.setChecked(s.show_toast)
        self._toast_duration.setValue(s.toast_duration_ms)
        self._debug_check.setChecked(s.show_debug_window)
        self._save_debug_check.setChecked(s.save_debug_screenshot)
        self._none_state_check.setChecked(s.none_state_enabled)
        self._none_state_spin.setValue(s.none_state_frames)
        self._minimize_tray_check.setChecked(s.minimize_to_tray)

        # 语言
        lang = s._data.get("gui", {}).get("language", "zh_CN")
        idx = self._lang_combo.findData(lang)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)

        # LDPlayer
        if s.ldplayer_install_path:
            self._ld_path_edit.setText(s.ldplayer_install_path)
        elif self._ld_info:
            self._ld_path_edit.setText(self._ld_info.install_path)
        if self._ld_info:
            self._ld_version_label.setText(
                self._i18n.t("settings.detected_version",
                             version=self._ld_info.version_name,
                             hook=f"{self._ld_info.offsets['hook_rva']:#x}")
            )

        # 高级
        self._injector_edit.setText(s.injector_path_override or "")
        self._dll_edit.setText(s.dll_path_override or "")

    def _on_save(self):
        """保存设置。"""
        i = self._i18n
        s = self._settings

        # 强制提交 spinbox 的手动输入（防止用户输入后直接点 Save 未触发 FocusOut）
        for spin in (self._interval_spin, self._debounce_spin,
                     self._threshold_spin, self._toast_duration):
            spin.interpretText()

        # 通用
        s._data.setdefault("monitor", {})["poll_interval_ms"] = \
            self._interval_spin.value()
        s._data.setdefault("monitor", {})["debounce_count"] = \
            self._debounce_spin.value()
        s._data.setdefault("monitor", {})["match_threshold"] = \
            self._threshold_spin.value()
        s._data.setdefault("gui", {})["show_toast"] = \
            self._toast_check.isChecked()
        s._data.setdefault("gui", {})["toast_duration_ms"] = \
            self._toast_duration.value()
        s._data.setdefault("monitor", {})["show_debug_window"] = \
            self._debug_check.isChecked()
        s._data.setdefault("monitor", {})["save_debug_screenshot"] = \
            self._save_debug_check.isChecked()
        s._data.setdefault("monitor", {})["none_state_enabled"] = \
            self._none_state_check.isChecked()
        s._data.setdefault("monitor", {})["none_state_frames"] = \
            self._none_state_spin.value()

        s._data.setdefault("gui", {})["minimize_to_tray"] = \
            self._minimize_tray_check.isChecked()

        # 语言
        lang = self._lang_combo.currentData()
        old_lang = s._data.get("gui", {}).get("language", "zh_CN")
        s._data.setdefault("gui", {})["language"] = lang

        # LDPlayer
        ld_path = self._ld_path_edit.text().strip()
        if ld_path:
            s.ldplayer_install_path = ld_path

        # 高级
        s._data.setdefault("advanced", {})["injector_path_override"] = \
            self._injector_edit.text().strip() or None
        s._data.setdefault("advanced", {})["dll_path_override"] = \
            self._dll_edit.text().strip() or None

        self.settings_changed.emit()
        if lang != old_lang:
            self.language_changed.emit(lang)

        QMessageBox.information(self, i.t("settings.title"), i.t("settings.saved"))
        self.accept()

    def _on_browse_ld(self):
        path = QFileDialog.getExistingDirectory(
            self, self._i18n.t("settings.ldplayer_path")
        )
        if path:
            self._ld_path_edit.setText(path)

    def _on_auto_detect(self):
        from src.shared.ldplayer import auto_detect
        info = auto_detect()
        if info:
            self._ld_path_edit.setText(info.install_path)
            self._ld_version_label.setText(
                self._i18n.t("settings.detected_version",
                             version=info.version_name,
                             hook=f"{info.offsets['hook_rva']:#x}")
            )
        else:
            QMessageBox.warning(
                self,
                self._i18n.t("settings.ldplayer_path"),
                self._i18n.t("error.auto_detect_failed")
            )
