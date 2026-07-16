#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
国际化模块 — 语言检测 + JSON 资源加载 + 翻译函数

用法:
    i18n = I18n("locales")
    i18n.load("zh_CN")       # 加载中文
    print(i18n.t("app.title"))  # "LDPlayer 按键自动切换"

    # 检测系统语言
    lang = I18n.detect_system_language()  # "zh_CN" or "en_US"
    i18n.load(lang)
"""

import os
import json
import locale
from typing import Optional


class I18n:
    """多语言管理器。

       翻译文件格式 (locales/<lang>.json):
           {"key": "value", ...}

       支持 Python str.format() 风格的参数插值:
           i18n.t("hello", name="World")  — 对应 "hello": "Hello, {name}!"
    """

    def __init__(self, locale_dir: str):
        """
        参数：
            locale_dir: 翻译文件目录（如 "locales"）
        """
        self._locale_dir = locale_dir
        self._translations: dict = {}
        self._current_lang: str = ""

    @property
    def current_lang(self) -> str:
        """当前语言代码。"""
        return self._current_lang

    def load(self, lang: str):
        """加载指定语言的翻译文件。

        参数：
            lang: 语言代码，如 "zh_CN", "en_US"
        """
        filepath = os.path.join(self._locale_dir, f"{lang}.json")
        if os.path.isfile(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                self._translations = json.load(f)
            self._current_lang = lang
        else:
            # 回退到英文
            fallback = os.path.join(self._locale_dir, "en_US.json")
            if os.path.isfile(fallback):
                with open(fallback, "r", encoding="utf-8") as f:
                    self._translations = json.load(f)
                self._current_lang = "en_US"
            else:
                self._translations = {}
                self._current_lang = ""

    def t(self, key: str, **kwargs) -> str:
        """获取翻译文本，支持参数插值。

        参数：
            key:    翻译键
            **kwargs: 格式化参数（对应翻译文本中的 {name} 占位符）

        返回：
            翻译后的字符串，找不到键则返回 key 本身。
        """
        text = self._translations.get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    @staticmethod
    def detect_system_language() -> str:
        """检测系统语言，返回语言代码。

           中文系统 → "zh_CN"，其他 → "en_US"。
        """
        try:
            sys_lang, _ = locale.getdefaultlocale()
        except Exception:
            sys_lang = None

        if sys_lang and (sys_lang.startswith("zh") or sys_lang == "Chinese"):
            return "zh_CN"
        return "en_US"

    def available_languages(self) -> list:
        """返回可用语言列表 [(code, display_name), ...]"""
        langs = []
        if os.path.isdir(self._locale_dir):
            for fname in sorted(os.listdir(self._locale_dir)):
                if fname.endswith(".json"):
                    code = fname[:-5]
                    # 从翻译文件中读取语言显示名
                    path = os.path.join(self._locale_dir, fname)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        name = data.get("_language_name", code)
                    except Exception:
                        name = code
                    langs.append((code, name))
        return langs
