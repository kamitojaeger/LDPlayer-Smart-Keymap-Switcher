#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
共享工具模块

模块职责：
    config.py    — JSON 配置读写 + 游戏自动扫描 (GameConfig, AppSettings)
    ldplayer.py  — LDPlayer 安装路径 & 版本检测 (LDPlayerInfo, auto_detect)
    injector.py  — keymap_injector.exe 封装 (Injector)
"""

from .config import (
    GameConfig,
    AppSettings,
)
from .ldplayer import (
    LDPlayerInfo,
    detect_install_path,
    detect_version,
    auto_detect,
)
from .injector import (
    Injector,
)

__all__ = [
    # config
    "GameConfig", "AppSettings",
    # ldplayer
    "LDPlayerInfo", "detect_install_path", "detect_version", "auto_detect",
    # injector
    "Injector",
]
