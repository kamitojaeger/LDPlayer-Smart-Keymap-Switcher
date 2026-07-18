#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置管理 — JSON 配置读写 + 路径解析 + 游戏自动扫描

职责：
  - GameConfig: 从 game.json 加载单个游戏配置
  - GameConfig.scan_games(): 遍历 games/ 目录，自动发现游戏
  - AppSettings: 全局 settings.json 读写
"""

import os
import json
import copy
from typing import Optional


# ---------------------------------------------------------------------------
# GameConfig — 单个游戏的完整配置
# ---------------------------------------------------------------------------

class GameConfig:
    """单个游戏的完整配置，从 game.json 加载。

    自动标准化：v1 格式 (schema_version=1 或无) 加载时自动升级为 v2 内部格式。

    属性（只读）:
        schema_version: int — 1|2
        name, package, description, author, version
        resolution: (width, height)
        detection: 标准化后的检测配置 dict
        regions: 标准化后的命名区域池 {region_id: region_config}
        states: list[dict]  每个 state 含 id/name/templates[]/keymap/match_logic...
        game_dir: 游戏数据根目录（game.json 所在目录）
    """

    def __init__(self, data: dict, game_dir: str):
        self._data = self._normalize(data)
        self.game_dir = game_dir

    # ------------------------------------------------------------------
    # v1 → v2 标准化
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(data: dict) -> dict:
        """检测并标准化配置格式：v1 → v2 内存升级。"""
        schema_ver = data.get("schema_version", 1)

        if schema_ver >= 2:
            # 已是 v2+，确保 match_logic / priority 默认值
            for s in data.get("states", []):
                if "match_logic" not in s:
                    s["match_logic"] = "any"
                if "priority" not in s:
                    s["priority"] = 0
            return data

        # ---- v1 → v2 升级 ----
        data = copy.deepcopy(data)
        data["schema_version"] = 2

        # 1. detection.search_region → regions.default
        det = data.get("detection", {})
        sr = det.pop("search_region", {})
        if sr:
            data["regions"] = {"default": sr}
        elif "regions" not in data:
            # 没有 search_region 也没有 regions → 最小默认
            data["regions"] = {
                "default": {
                    "method": "bottom_right",
                    "search_expand": 16,
                    "margin_bottom": 40,
                    "margin_right": 40,
                    "slack": 20,
                }
            }

        # 2. state.template (字符串) → state.templates (列表)
        for s in data.get("states", []):
            tmpl = s.pop("template", None)
            if tmpl is not None:
                s["templates"] = [{"path": tmpl, "region": "default"}]
            # match_logic 默认
            if "match_logic" not in s:
                s["match_logic"] = "any"
            # priority 默认
            if "priority" not in s:
                s["priority"] = 0

        return data

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def schema_version(self) -> int:
        return self._data.get("schema_version", 1)

    @property
    def name(self) -> str:
        return self._data.get("name", "")

    @property
    def package(self) -> list:
        """返回包名列表（始终为 list）。
           输入可以是 "com.example" 或 ["com.example", "com.example.garena"]。
        """
        pkg = self._data.get("package", "")
        if isinstance(pkg, str):
            return [pkg] if pkg else []
        if isinstance(pkg, list):
            return [p for p in pkg if p]
        return []

    @property
    def description(self) -> str:
        return self._data.get("description", "")

    @property
    def author(self) -> str:
        return self._data.get("author", "")

    @property
    def version(self) -> str:
        return self._data.get("version", "")

    @property
    def resolution(self) -> tuple:
        r = self._data.get("resolution", {})
        return (r.get("width", 1920), r.get("height", 1080))

    @property
    def detection(self) -> dict:
        return self._data.get("detection", {})

    @property
    def regions(self) -> dict:
        """返回标准化后的命名区域池 {region_id: region_config}。"""
        return self._data.get("regions", {})

    @property
    def states(self) -> list:
        """返回标准化后的 states 列表（v2 格式：每个含 templates[] + match_logic）。"""
        return self._data.get("states", [])

    @property
    def none_state(self) -> Optional[dict]:
        """无匹配时的按键方案（可选）。格式: {\"keymap\": abs_path, \"mouse_drag_key\": int|None}。
           为 None 表示未配置，none_state 功能不会生效。
        """
        ns = self._data.get("none_state")
        if ns and ns.get("keymap"):
            return {
                "keymap": os.path.join(self.game_dir, ns["keymap"]),
                "mouse_drag_key": ns.get("mouse_drag_key"),
            }
        return None

    def state_ids(self) -> list:
        """返回状态 ID 列表。"""
        return [s["id"] for s in self.states]

    def keymap_paths(self) -> list:
        """返回所有唯一按键方案的绝对路径列表（去重）。

           收集 states[].keymap + none_state.keymap，去除重复文件。
           用于复制 .kmp 到 LDPlayer 的 vms/customizeConfigs 目录。
        """
        paths = set()
        for s in self.states:
            kmp = s.get("keymap")
            if kmp:
                resolved = os.path.join(self.game_dir, kmp)
                if os.path.isfile(resolved):
                    paths.add(resolved)
        ns = self._data.get("none_state")
        if ns and ns.get("keymap"):
            resolved = os.path.join(self.game_dir, ns["keymap"])
            if os.path.isfile(resolved):
                paths.add(resolved)
        return sorted(paths)

    def get_state(self, state_id: str) -> Optional[dict]:
        """按 ID 查找状态定义。"""
        for s in self.states:
            if s["id"] == state_id:
                return s
        return None

    def kmp_for_state(self, state_id: str) -> Optional[str]:
        """返回指定状态的 .kmp 绝对路径。"""
        s = self.get_state(state_id)
        if s:
            return os.path.join(self.game_dir, s["keymap"])
        return None

    def mouse_drag_key_for_state(self, state_id: str) -> Optional[int]:
        """返回指定状态的 mouse_drag_key，None 表示不需要。"""
        s = self.get_state(state_id)
        if s:
            return s.get("mouse_drag_key")
        return None

    # ------------------------------------------------------------------
    # matcher / monitor 配置生成
    # ------------------------------------------------------------------

    def to_matcher_config(self) -> dict:
        """生成 matcher 模块可用的检测配置字典。

           v2: 不再从 search_region 提取全局边距，matcher 按 region 独立计算。
           保留 feature mask / threshold / 分辨率等全局参数。
        """
        from src.detector.matcher import DEFAULT_DETECTION

        det = self.detection
        fm = det.get("feature_mask", {})
        res = self.resolution

        cfg = copy.deepcopy(DEFAULT_DETECTION)
        cfg.update({
            "ref_game_w": res[0],
            "ref_game_h": res[1],
            "ref_capture_w": res[0] + 60,    # 游戏区 + 工具栏
            "ref_capture_h": res[1] + 60,    # 游戏区 + 标题栏
            "match_threshold": det.get("threshold", 0.75),
            "mask_dark_percentile": fm.get("dark_percentile", 22),
            "mask_bright_percentile": fm.get("bright_percentile", 82),
        })
        return cfg

    def state_configs_for_matcher(self) -> list:
        """返回供新版 match_multi() 使用的 state 配置列表。

           格式: [{"id": str, "templates": [{"path": abs_path, "region": str}, ...],
                   "match_logic": "any"|"all"}, ...]
        """
        configs = []
        for s in self.states:
            templates = []
            for t in s.get("templates", []):
                tmpl = {
                    "path": os.path.join(self.game_dir, t["path"]),
                    "region": t.get("region", "default"),
                }
                if "matching_mode" in t:
                    tmpl["matching_mode"] = t["matching_mode"]
                templates.append(tmpl)
            nts = s.get("negative_templates", [])
            negative_templates = []
            for nt in nts:
                ntmpl = {
                    "path": os.path.join(self.game_dir, nt["path"]),
                    "region": nt.get("region", "default"),
                }
                if "matching_mode" in nt:
                    ntmpl["matching_mode"] = nt["matching_mode"]
                negative_templates.append(ntmpl)
            cfg = {
                "id": s["id"],
                "templates": templates,
                "match_logic": s.get("match_logic", "any"),
            }
            if negative_templates:
                cfg["negative_templates"] = negative_templates
                cfg["negative_penalty"] = s.get("negative_penalty", 0.50)
            if "min_pass_ratio" in s:
                cfg["min_pass_ratio"] = s["min_pass_ratio"]
            configs.append(cfg)
        return configs

    def to_monitor_config(self, injector_path: str,
                          poll_interval_ms: int = 500,
                          debounce_count: int = 3,
                          none_state_frames: int = 20):
        """生成 MonitorConfig 对象（v2：states_config 含 templates[] + regions）。"""
        from src.detector.monitor import MonitorConfig

        det = self.detection
        initial = "__none__" if self._data.get("none_state") else None

        states_config = {}
        priorities = {}
        for s in self.states:
            sid = s["id"]
            priorities[sid] = s.get("priority", 0)
            templates = []
            for t in s.get("templates", []):
                tmpl = {
                    "path": os.path.join(self.game_dir, t["path"]),
                    "region": t.get("region", "default"),
                }
                if "matching_mode" in t:
                    tmpl["matching_mode"] = t["matching_mode"]
                templates.append(tmpl)
            # Negative templates
            nts = s.get("negative_templates", [])
            negative_templates = []
            for nt in nts:
                ntmpl = {
                    "path": os.path.join(self.game_dir, nt["path"]),
                    "region": nt.get("region", "default"),
                }
                if "matching_mode" in nt:
                    ntmpl["matching_mode"] = nt["matching_mode"]
                negative_templates.append(ntmpl)
            states_config[sid] = {
                "templates": templates,
                "match_logic": s.get("match_logic", "any"),
                "keymap": os.path.join(self.game_dir, s["keymap"]),
                "mouse_drag_key": s.get("mouse_drag_key"),
            }
            if negative_templates:
                states_config[sid]["negative_templates"] = negative_templates
                states_config[sid]["negative_penalty"] = s.get("negative_penalty", 0.50)
            if "min_pass_ratio" in s:
                states_config[sid]["min_pass_ratio"] = s["min_pass_ratio"]

        return MonitorConfig(
            injector_path=injector_path,
            states_config=states_config,
            regions_config=self.regions,
            detection_config=self.to_matcher_config(),
            initial_state=initial,
            none_state_config=self.none_state,
            none_state_frames=none_state_frames,
            poll_interval_ms=poll_interval_ms if poll_interval_ms is not None
                else det.get("interval_ms", 333),
            debounce_count=debounce_count,
            match_threshold=det.get("threshold", 0.75),
            disc_reset_enabled=det.get("disc_reset_enabled", False),
            priorities=priorities,
        )

    @classmethod
    def from_json(cls, path: str) -> "GameConfig":
        """从 game.json 路径加载配置（自动 v1→v2 标准化）。"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        game_dir = os.path.dirname(os.path.abspath(path))
        return cls(data, game_dir)

    @classmethod
    def scan_games(cls, games_dir: str) -> list["GameConfig"]:
        """遍历 games/ 目录，读取所有 game.json，返回 GameConfig 列表。

           跳过 _template/ 目录。
        """
        configs = []
        if not os.path.isdir(games_dir):
            return configs

        for entry in sorted(os.listdir(games_dir)):
            if entry.startswith("_") or entry.startswith("."):
                continue
            game_dir = os.path.join(games_dir, entry)
            if not os.path.isdir(game_dir):
                continue
            game_json = os.path.join(game_dir, "game.json")
            if os.path.isfile(game_json):
                try:
                    configs.append(cls.from_json(game_json))
                except Exception as e:
                    print(f"[Warning] Skip {game_json}: {e}")
        return configs


# ---------------------------------------------------------------------------
# AppSettings — 全局应用设置
# ---------------------------------------------------------------------------

class AppSettings:
    """全局应用设置，从 settings.json 加载。

    用法:
        settings = AppSettings.load("config/settings.json")
        print(settings.ldplayer_install_path)
        settings.ldplayer_install_path = "F:\\LDPlayer"
        settings.save("config/settings.json")
    """

    _DEFAULTS = {
        "ldplayer": {
            "install_path": "",
            "preferred_version": None,
            "auto_detect": True,
        },
        "monitor": {
            "poll_interval_ms": 333,
            "debounce_count": 1,
            "show_debug_window": False,
            "save_debug_screenshot": False,
            "none_state_enabled": True,
            "none_state_frames": 200,
        },
        "gui": {
            "start_minimized": False,
            "show_toast": True,
            "toast_duration_ms": 3000,
            "language": "",
        },
        "advanced": {
            "injector_path_override": None,
            "dll_path_override": None,
            "log_level": "INFO",
        },
    }

    def __init__(self, data: dict = None):
        self._data = data or copy.deepcopy(self._DEFAULTS)

    # -- ldplayer section --

    @property
    def ldplayer_install_path(self) -> str:
        return self._data.get("ldplayer", {}).get("install_path", "")

    @ldplayer_install_path.setter
    def ldplayer_install_path(self, value: str):
        self._data.setdefault("ldplayer", {})["install_path"] = value

    @property
    def ldplayer_auto_detect(self) -> bool:
        return self._data.get("ldplayer", {}).get("auto_detect", True)

    @property
    def ldplayer_preferred_version(self) -> Optional[str]:
        return self._data.get("ldplayer", {}).get("preferred_version")

    # -- monitor section --

    @property
    def poll_interval_ms(self) -> int:
        return self._data.get("monitor", {}).get("poll_interval_ms", 500)

    @property
    def debounce_count(self) -> int:
        return self._data.get("monitor", {}).get("debounce_count", 3)

    @property
    def save_debug_screenshot(self) -> bool:
        return self._data.get("monitor", {}).get("save_debug_screenshot", False)

    @property
    def none_state_enabled(self) -> bool:
        """N帧无匹配后切换到空白按键方案。默认 True。"""
        return self._data.get("monitor", {}).get("none_state_enabled", True)

    @property
    def none_state_frames(self) -> int:
        """进入 none 状态所需的连续无匹配帧数。默认 200。"""
        return self._data.get("monitor", {}).get("none_state_frames", 200)

    @property
    def show_debug_window(self) -> bool:
        return self._data.get("monitor", {}).get("show_debug_window", False)

    # -- gui section --

    @property
    def show_toast(self) -> bool:
        return self._data.get("gui", {}).get("show_toast", True)

    @property
    def toast_duration_ms(self) -> int:
        return self._data.get("gui", {}).get("toast_duration_ms", 3000)

    # -- advanced section --

    @property
    def injector_path_override(self) -> Optional[str]:
        return self._data.get("advanced", {}).get("injector_path_override")

    @property
    def dll_path_override(self) -> Optional[str]:
        return self._data.get("advanced", {}).get("dll_path_override")

    @classmethod
    def load(cls, path: str) -> "AppSettings":
        """从 JSON 文件加载设置，缺失项用默认值填充。"""
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = copy.deepcopy(cls._DEFAULTS)

        # 深度合并默认值（确保新增字段有默认值）
        merged = copy.deepcopy(cls._DEFAULTS)
        _deep_update(merged, data)
        return cls(merged)

    def save(self, path: str):
        """保存设置到 JSON 文件。"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)


def _deep_update(target: dict, source: dict):
    """递归合并 source 到 target，保留 target 中 source 未提供的键。"""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
