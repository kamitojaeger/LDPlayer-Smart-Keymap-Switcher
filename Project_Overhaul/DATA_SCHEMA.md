# 数据格式规范 (JSON Schema)

> 这是项目配置文件的数据格式定义。所有 agent 修改配置文件时必须遵守此规范。

---

## 1. `games/<game_name>/game.json` — 游戏配置

### Schema

```json
{
  "name": "string — 游戏显示名称 (如 'GTA: San Andreas')",
  "package": "string|string[] — Android 包名 (如 'com.rockstargames.gtasa'，或渠道包多包名数组 ['com.garena.game.codm', 'com.activision.callofduty.shooter'])。加载时统一规范化为 string[]",
  "description": "string (可选) — 游戏简介",
  "author": "string (可选) — 配置作者",
  "version": "string (可选) — 配置版本号",
  "schema_version": "number — 配置文件格式版本 (当前 2，未来向后兼容用)",

  "resolution": {
    "width": "number — 游戏区参考宽度 (如 1920，目前仅支持16：9分辨率，后续再考虑支持20:9)",
    "height": "number — 游戏区参考高度 (如 1080，目前仅支持16：9分辨率，后续再考虑支持20:9)"
  },

  "detection": {
    "method": "string — 'template_matching' (当前唯一支持)",
    "interval_ms": "number — 检测间隔毫秒 (默认 500)",
    "threshold": "number — 匹配成功阈值 0.0~1.0 (默认 0.75)",

    "feature_mask": {
      "enabled": "boolean — 是否启用 feature mask",
      "dark_percentile": "number — 暗部百分位 (默认 22)",
      "bright_percentile": "number — 亮部百分位 (默认 82)"
    }
  },

  "regions": {
    "<region_id>": {
      "method": "string — 定位方法: 'bottom_right'|'top_left'|'top_right'|'bottom_left'|'center'",
      "search_expand": "number — 搜索区域外扩像素 (默认 16)",
      "margin_bottom": "number — 距游戏区下边距 (method=bottom_right/bottom_left 时)",
      "margin_top": "number — 距游戏区上边距 (method=top_left/top_right 时)",
      "margin_right": "number — 距游戏区右边距 (method=bottom_right/top_right 时)",
      "margin_left": "number — 距游戏区左边距 (method=bottom_left/top_left 时)",
      "slack": "number — 搜索区域余量 (默认 20)",
      "center_range_w": "number — 以中心向外扩展水平范围 (method=center 时)",
      "center_range_h": "number — 以中心向外扩展垂直范围 (method=center 时)"
    }
    // ... 按需定义多个命名区域，可在 states[].templates[].region 中引用
  },

  "states": [
    {
      "id": "string — 状态唯一标识 (如 'walk', 'drive')",
      "name": "string — 状态显示名称 (如 '行走模式')",
      "description": "string (可选) — 状态描述",
      "priority": "number (可选) — 状态优先级，越大越优先。当多个 state 同时匹配时按优先级排序；相同优先级取最高匹配率。默认 0",
      "keymap": "string — 按键方案 .kmp 路径，相对于 game.json 所在目录",
      "mouse_drag_key": "number|null — 射击视角恢复虚拟键码 (如 17=Ctrl)，null 表示不需要",

      "templates": [
        {
          "path": "string — 模板图片路径，相对于 game.json 所在目录 (如 'templates/walk.png')",
          "region": "string — 引用 regions 中定义的区域 ID"
        }
        // ... 可定义多个模板，匹配位于不同屏幕区域
      ],
      "match_logic": "string — 'any'=任一模板命中即匹配 | 'all'=全部模板命中才匹配 (默认 'all')"
    }
    // ... 至少 2 个 states
  ],

  "none_state": {
    // 可选 — 无匹配时的按键方案。配合设置中的"无匹配结果自动释放鼠标"使用。
    // 未配置则 even 勾选设置项也不会生效。
    "keymap": "string — .kmp 路径，相对于 game.json 所在目录",
    "mouse_drag_key": "number|null — 可选的鼠标拖拽键码"
  }
}
```

> **向后兼容**：旧格式（schema_version=1，`state.template` 字符串 + 全局 `detection.search_region`）仍会加载。
> 加载器检测到旧格式时，自动将 `detection.search_region` 升级为 `regions.default`，并将 `state.template` 包装为
> `templates: [{"path": "...", "region": "default"}]`。见 §1.4。

### 完整示例 (GTASA — 单区域简单场景)

```json
{
  "name": "GTA: San Andreas",
  "package": "com.rockstargames.gtasa",
  "description": "Grand Theft Auto: San Andreas — 需要自动切换行走/驾驶按键方案",
  "author": "LDPlayer Auto Input Switcher Team",
  "version": "1.0",
  "schema_version": 2,

  "resolution": {
    "width": 1920,
    "height": 1080
  },

  "detection": {
    "method": "template_matching",
    "interval_ms": 500,
    "threshold": 0.75,
    "feature_mask": {
      "enabled": true,
      "dark_percentile": 22,
      "bright_percentile": 82
    }
  },

  "regions": {
    "default": {
      "method": "bottom_right",
      "search_expand": 16,
      "margin_bottom": 40,
      "margin_right": 40,
      "slack": 20
    }
  },

  "states": [
    {
      "id": "walk",
      "name": "行走模式",
      "description": "步行 / 跑步状态",
      "keymap": "keymaps/GTASA(walk mode).kmp",
      "mouse_drag_key": null,
      "priority": 0,
      "templates": [
        { "path": "templates/walk.png", "region": "default" }
      ],
      "match_logic": "any"
    },
    {
      "id": "drive",
      "name": "驾驶模式",
      "description": "驾车 / 飞行状态，需要射击视角",
      "keymap": "keymaps/GTASA(Drive mode).kmp",
      "mouse_drag_key": 17,
      "priority": 0,
      "templates": [
        { "path": "templates/drive.png", "region": "default" }
      ],
      "match_logic": "any"
    }
  ]
}
```

### 多区域示例 (假设 PUBG 驾驶检测)

```json
{
  "name": "PUBG Mobile",
  "package": "com.tencent.ig",
  "schema_version": 2,
  "resolution": { "width": 1920, "height": 1080 },
  "detection": {
    "method": "template_matching",
    "interval_ms": 500,
    "threshold": 0.75,
    "feature_mask": { "enabled": true, "dark_percentile": 22, "bright_percentile": 82 }
  },

  "regions": {
    "minimap_indicator": {
      "method": "top_right",
      "margin_top": 60,
      "margin_right": 10,
      "search_expand": 12,
      "slack": 16
    },
    "crosshair": {
      "method": "center",
      "center_range_w": 80,
      "center_range_h": 80,
      "search_expand": 8
    },
    "weapon_slot": {
      "method": "bottom_right",
      "margin_bottom": 40,
      "margin_right": 40,
      "search_expand": 16,
      "slack": 20
    }
  },

  "states": [
    {
      "id": "walk",
      "name": "行走模式",
      "keymap": "keymaps/walk.kmp",
      "mouse_drag_key": null,
      "priority": 0,
      "templates": [
        { "path": "templates/walk_hud.png", "region": "weapon_slot" }
      ],
      "match_logic": "any"
    },
    {
      "id": "drive",
      "name": "驾驶模式",
      "keymap": "keymaps/drive.kmp",
      "mouse_drag_key": 17,
      "priority": 1,
      "templates": [
        { "path": "templates/drive_speed.png", "region": "minimap_indicator" },
        { "path": "templates/drive_hud.png", "region": "weapon_slot" }
      ],
      "match_logic": "all"
    },
    {
      "id": "combat",
      "name": "战斗模式",
      "keymap": "keymaps/combat.kmp",
      "mouse_drag_key": null,
      "priority": 2,
      "templates": [
        { "path": "templates/combat_crosshair.png", "region": "crosshair" },
        { "path": "templates/combat_ammo.png", "region": "weapon_slot" }
      ],
      "match_logic": "all"
    }
  ]
}
```

> 多区域场景中，"驾驶"状态需要**同时**满足 minimap 指示器 + 武器槽 HUD 两个位置的模板均命中
> (`match_logic: "all"`)，降低误判。"行走"状态只需任一命中 (`match_logic: "any"`)。

### 1.4 旧格式向后兼容 (schema_version=1)

旧格式（无 `schema_version` 或 =1）中，`detection.search_region` 全局定义 + `state.template` 为字符串：

```json
{
  "detection": {
    "search_region": { "method": "bottom_right", ... }
  },
  "states": [
    { "id": "walk", "template": "templates/walk.png", ... }
  ]
}
```

`GameConfig.from_json()` 加载时自动标准化为 v2 格式：

1. `detection.search_region` → `regions.default`（保留所有参数）
2. `state.template` → `state.templates: [{"path": "...", "region": "default"}]`
3. 未指定 `match_logic` → 默认 `"any"`（单模板场景等价行为）

现有 GTASA 的 `game.json` **无需手动修改**，标准化在内存中完成。新游戏请直接按 v2 格式编写。

---

## 2. `config/settings.json` — 全局应用设置

### Schema

```json
{
  "ldplayer": {
    "install_path": "string — LDPlayer 安装目录 (为空则自动检测)",
    "preferred_version": "string|null — 首选版本 'ld9'|'ld14'|null=自动",
    "auto_detect": "boolean — 是否自动检测 LDPlayer 路径 (默认 true)"
  },

  "monitor": {
    "poll_interval_ms": "number — 检测间隔毫秒 (默认 333, 范围 50~2000)",
    "debounce_count": "number — 去抖帧数 (默认 3, 连续 N 帧一致才触发切换)",
    "show_debug_window": "boolean — 是否显示调试截图窗口 (默认 false)"
  },

  "gui": {
    "start_minimized": "boolean — 启动时最小化到托盘 (默认 true)",
    "show_toast": "boolean — 是否显示 Toast 覆盖层 (默认 true)",
    "toast_duration_ms": "number — Toast 显示时长毫秒 (默认 3000)",
    "language": "string — 界面语言 'zh_CN'|'en_US' (默认 'zh_CN')"
  },

  "advanced": {
    "injector_path_override": "string|null — 自定义 injector 路径 (null=使用内置)",
    "dll_path_override": "string|null — 自定义 DLL 路径 (null=使用内置)",
    "log_level": "string — 'DEBUG'|'INFO'|'WARNING'|'ERROR' (默认 'INFO')"
  }
}
```

### 默认值示例

```json
{
  "ldplayer": {
    "install_path": "",
    "preferred_version": null,
    "auto_detect": true
  },
  "monitor": {
    "poll_interval_ms": 333,
    "debounce_count": 1,
    "show_debug_window": false
  },
  "gui": {
    "start_minimized": true,
    "show_toast": true,
    "toast_duration_ms": 3000,
    "language": "zh_CN"
  },
  "advanced": {
    "injector_path_override": null,
    "dll_path_override": null,
    "log_level": "INFO"
  }
}
```

---

## 3. `config/ldplayer_versions.json` — LDPlayer 版本偏移表

### Schema

```json
{
  "supported_versions": [
    {
      "id": "string — 版本标识 (如 'ld9_overseas')",
      "name": "string — 显示名称 (如 'LDPlayer 9 (海外版)')",
      "process_name": "string — 进程名 (如 'dnplayer.exe')",
      "dll_name": "string — 目标 DLL (如 'dnplycore.dll')",
      "offsets": {
        "hook_rva": "number — HOOK 点 RVA",
        "func_rva": "number — setKeyboardConfig 函数 RVA",
        "return_rva": "number — CALL 返回地址 RVA"
      },
      "detection": {
        "dll_size": "number|null — DLL 文件大小 (用于精确匹配，null=不使用)",
        "signature": "string|null — 特征字节 hex (如 '55 8B EC 83 E4 F8 81 EC', null=不使用)"
      }
    }
    // ... 至少 1 个版本
  ],
  "fallback_strategy": "string — 'prompt_user'|'skip' (找不到匹配版本时的行为)"
}
```

### 完整示例

```json
{
  "supported_versions": [
    {
      "id": "ld9_overseas",
      "name": "LDPlayer 9 (海外版)",
      "process_name": "dnplayer.exe",
      "dll_name": "dnplycore.dll",
      "offsets": {
        "hook_rva": 131484,
        "func_rva": 641552,
        "return_rva": 131489
      },
      "detection": {
        "dll_size": null,
        "signature": "55 8B EC 83 E4 F8 81 EC"
      }
    },
    {
      "id": "ld14_overseas",
      "name": "LDPlayer 14 (海外版)",
      "process_name": "dnplayer.exe",
      "dll_name": "dnplycore.dll",
      "offsets": {
        "hook_rva": 122163,
        "func_rva": 612848,
        "return_rva": 122168
      },
      "detection": {
        "dll_size": null,
        "signature": "55 8B EC 83 E4 F8 81 EC"
      }
    }
  ],
  "fallback_strategy": "prompt_user"
}
```

> **关于 RVA 值**：上表中的 RVA 为十进制。原始 C++ 源码中使用十六进制：
> - LD9: HOOK=0x2019C, FUNC=0x9CA10, RTRN=0x201A1
> - LD14: HOOK=0x1DD33, FUNC=0x959F0, RTRN=0x1DD38
>
> Python 层读取后可用十六进制字符串或十进制整数，取决于实现选择。

---

## 5. `games/_template/game.json` — 新游戏模板

```json
{
  "name": "游戏名称",
  "package": "com.example.game",
  "description": "",
  "author": "",
  "version": "1.0",
  "schema_version": 2,

  "resolution": {
    "width": 1920,
    "height": 1080
  },

  "detection": {
    "method": "template_matching",
    "interval_ms": 500,
    "threshold": 0.75,
    "feature_mask": {
      "enabled": true,
      "dark_percentile": 22,
      "bright_percentile": 82
    }
  },

  "regions": {
    "default": {
      "method": "bottom_right",
      "search_expand": 16,
      "margin_bottom": 40,
      "margin_right": 40,
      "slack": 20
    }
  },

  "states": [
    {
      "id": "state_a",
      "name": "状态A",
      "description": "",
      "keymap": "keymaps/state_a.kmp",
      "mouse_drag_key": null,
      "priority": 0,
      "templates": [
        { "path": "templates/state_a.png", "region": "default" }
      ],
      "match_logic": "any"
    },
    {
      "id": "state_b",
      "name": "状态B",
      "description": "",
      "keymap": "keymaps/state_b.kmp",
      "mouse_drag_key": null,
      "priority": 0,
      "templates": [
        { "path": "templates/state_b.png", "region": "default" }
      ],
      "match_logic": "any"
    }
  ]
}
```

### regions 定位方法说明

| 方法 | 定位基准 | 必需参数 |
|---|---|---|
| `bottom_right` | 游戏区右下角 | `margin_bottom`, `margin_right`, `search_expand`, `slack` |
| `bottom_left` | 游戏区左下角 | `margin_bottom`, `margin_left`, `search_expand`, `slack` |
| `top_right` | 游戏区右上角 | `margin_top`, `margin_right`, `search_expand`, `slack` |
| `top_left` | 游戏区左上角 | `margin_top`, `margin_left`, `search_expand`, `slack` |
| `center` | 游戏区正中心 | `center_range_w`, `center_range_h`, `search_expand` |

---

## 6. `locales/<lang>.json` — 多语言翻译文件

### Schema

```json
{
  "app.title": "string — 应用标题 (窗口标题栏)",
  "app.tray.start": "string — 系统托盘 '启动监控'",
  "app.tray.stop": "string — 系统托盘 '停止监控'",
  "app.tray.show": "string — 系统托盘 '显示主窗口'",
  "app.tray.quit": "string — 系统托盘 '退出'",

  "game.select": "string — 游戏选择标签",
  "game.no_games": "string — 无可用游戏提示",
  "game.state": "string — 当前状态显示",

  "monitor.start": "string — 启动按钮",
  "monitor.stop": "string — 停止按钮",
  "monitor.running": "string — 监控运行中状态",
  "monitor.stopped": "string — 监控已停止状态",
  "monitor.switched": "string — 状态切换提示模板 (含 {old} {new})",

  "settings.title": "string — 设置对话框标题",
  "settings.language": "string — 语言设置标签",
  "settings.language.zh_CN": "string — '简体中文'",
  "settings.language.en_US": "string — 'English'",
  "settings.ldplayer_path": "string — LDPlayer 路径标签",
  "settings.auto_detect": "string — 自动检测复选框",
  "settings.monitor_interval": "string — 检测间隔标签",
  "settings.debounce": "string — 去抖帧数标签",
  "settings.threshold": "string — 匹配阈值标签",
  "settings.save": "string — 保存按钮",
  "settings.cancel": "string — 取消按钮",

  "about.title": "string — 关于标题",
  "about.version": "string — 版本信息",
  "about.description": "string — 项目描述",

  "error.no_ldplayer": "string — LDPlayer 未运行错误",
  "error.multi_instance": "string — 多实例错误",
  "toast.switch_to": "string — Toast 切换提示模板 (含 {name})"
}
```

### `locales/zh_CN.json` 示例

```json
{
  "app.title": "LDPlayer 按键自动切换",
  "app.tray.start": "启动监控",
  "app.tray.stop": "停止监控",
  "app.tray.show": "显示主窗口",
  "app.tray.quit": "退出",

  "game.select": "选择游戏",
  "game.no_games": "未找到游戏配置",
  "game.state": "当前状态",

  "monitor.start": "开始监控",
  "monitor.stop": "停止监控",
  "monitor.running": "监控运行中...",
  "monitor.stopped": "监控已停止",
  "monitor.switched": "已切换: {old} → {new}",

  "settings.title": "设置",
  "settings.language": "界面语言",
  "settings.language.zh_CN": "简体中文",
  "settings.language.en_US": "English",
  "settings.ldplayer_path": "LDPlayer 安装路径",
  "settings.auto_detect": "自动检测",
  "settings.monitor_interval": "检测间隔 (ms)",
  "settings.debounce": "去抖帧数",
  "settings.threshold": "匹配阈值",
  "settings.save": "保存",
  "settings.cancel": "取消",

  "about.title": "关于",
  "about.version": "版本",
  "about.description": "LDPlayer 模拟器按键方案自动切换工具",

  "error.no_ldplayer": "未检测到 LDPlayer 在运行，请先启动模拟器。",
  "error.multi_instance": "检测到多个 LDPlayer 实例，请只保留一个。",
  "toast.switch_to": "Switch to {name}"
}
```

### 添加新翻译 key 的规范

1. Key 命名：`模块.子模块.action` 点分小写英文，如 `settings.language.label`
2. 包含动态值的用 `{name}` 占位符，Python 端通过 `t("key", name="value")` 填充
3. 中英文 key 集合必须一致，缺少的任何 key 会回退到另一个语言的对应值 + 打印警告
4. 不要翻译占位符名称（`{name}` 在两份文件中保持不变）

---

## 7. 如何添加新游戏

1. 复制 `games/_template/` → 重命名为 `games/<game_name>/`
2. 编辑 `game.json`：
   - 填写 `name`、`package`、`resolution`
   - 在 `regions` 中定义所有需要检测的屏幕区域（参考 §5 的定位方法表）
   - 在 `states` 中为每个状态声明一个或多个 `templates`，并引用对应的 `region`
   - 设置 `match_logic`：单模板用 `"any"`，多区域组合判断用 `"all"`
3. 放入模板截图到 `templates/`
4. 放入 LDPlayer 按键方案 `.kmp` 文件到 `keymaps/`
5. 启动工具 → 新游戏自动出现在游戏列表中

**模板截图建议**：
- 从游戏实际画面中截取，分辨率与游戏一致
- 选择独特、不随游戏画面变化的 UI 元素
- PNG 格式，截取区域尽量小（当前 GTASA 约 180×178 像素）
- **多区域场景**：选择多个不同位置的 UI 元素，分别放入不同 region 的 template
  - 例：驾驶检测 = 小地图车速图标（`top_right`） + 底部武器槽样式（`bottom_right`）双重校验

### 状态优先级 (priority) 使用场景

当多个 state 可能同时命中时（如"驾驶坦克"需要 tank_smoke + Drive_arrows 同时命中，"搭乘坦克"仅需 tank_smoke），使用 `priority` 字段控制选择顺序：

- 高 priority 的 state 优先于低 priority 的 state
- 相同 priority 时取匹配率最高的 state
- 不需要优先级差异的场景设为 0（默认值）

### 键位去重 (Keymap Dedup)

多个细分 state 可以指向同一个 .kmp 文件（如走路/游泳/滑翔共用 walk.kmp）。monitor 层会在切换前比较目标 .kmp 与当前已加载的 .kmp：相同则跳过 injector 调用，仅更新状态追踪。
