# Game Config 格式规范

> *[English](GAME_CONFIG.md)*

> 版本: schema v2 | 最后更新: 2026-07-16

每个游戏一个文件夹 `games/<name>/`，内含 `game.json` + `keymaps/` + `templates/`。

---

## 1. 顶层结构

```json
{
  "schema_version": 2,
  "name": "CODM",
  "package": "com.activision.callofduty.shooter",
  "resolution": { "width": 1920, "height": 1080 },
  "detection": { ... },
  "regions": { ... },
  "states": [ ... ],
  "none_state": { ... }
}
```

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `schema_version` | int | ✅ | 固定 `2` |
| `name` | str | ✅ | 游戏显示名 |
| `package` | str \| str[] | ✅ | Android 包名，用于 dir_kmps.dir 过滤。多包名用数组 |
| `resolution` | object | | 参考分辨率，默认 1920×1080 |
| `detection` | object | ✅ | 检测参数 |
| `regions` | object | ✅ | 命名区域池 |
| `states` | list | ✅ | 状态定义列表 |
| `none_state` | object | | 无匹配时使用的按键配置 |

---

## 2. detection — 检测参数

```json
{
  "ref_game_w": 1920,
  "ref_game_h": 1080,
  "ref_titlebar_h": 60,
  "match_threshold": 0.75,
  "feature_mask": {
    "enabled": true,
    "dark_percentile": 22,
    "bright_percentile": 82
  }
}
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `ref_game_w` | 1920 | 参考游戏区宽度 |
| `ref_game_h` | 1080 | 参考游戏区高度 |
| `ref_titlebar_h` | 60 | 标题栏高度（RenderWindow 模式自动忽略） |
| `match_threshold` | 0.75 | 全局匹配阈值 |
| `feature_mask.dark_percentile` | 22 | 暗部百分位 |
| `feature_mask.bright_percentile` | 82 | 亮部百分位 |

---

## 3. regions — 识别区域 (xywh 格式)

**推荐 xywh 格式**（基于 1920×1080 参考坐标系）：

```json
{
  "br_jump": {
    "x": 1748,
    "y": 694,
    "width": 136,
    "height": 136,
    "search_expand": 16
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `x` | int | 模板预期左上角 X (1920×1080 参考) |
| `y` | int | 模板预期左上角 Y |
| `width` | int | 区域宽度 (0 = 用模板实际宽度) |
| `height` | int | 区域高度 (0 = 用模板实际高度) |
| `search_expand` | int | 四向扩展像素，默认 8 |

**搜索矩形** = `(x-expand, y-expand, x+width+expand, y+height+expand)`

**约束**: `x + 模板宽 + expand ≤ 1920`，`y + 模板高 + expand ≤ 1080`。超出会触发 `TPL TOO LARGE` 错误。

**旧格式**（兼容 GTASA，不推荐新游戏使用）：

```json
{
  "default": {
    "method": "bottom_right",
    "margin_right": 40,
    "margin_bottom": 40,
    "slack": 20,
    "search_expand": 16
  }
}
```

支持 `bottom_right/bottom_left/top_right/top_left/center` 五种定位方法。

---

## 4. states — 状态定义

### 4.1 基础字段

```json
{
  "id": "vehicle_drive_1",
  "name": "车辆驾驶",
  "description": "车辆驾驶状态 — 四方向箭头外圈可见",
  "keymap": "keymaps/CODM((car_drive_1).kmp",
  "mouse_drag_key": null,
  "priority": 12,
  "match_logic": "all",
  "templates": [
    { "path": "templates/vehicle/Drive_1_upArrow.png", "region": "tl_arrow_up" },
    { "path": "templates/vehicle/Drive_1_downArrow.png", "region": "bl_arrow_down" }
  ]
}
```

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `id` | str | ✅ | 唯一标识，日志和状态机使用 |
| `name` | str | | 显示名 |
| `description` | str | | 描述 |
| `keymap` | str | ✅ | .kmp 文件相对路径 (基于游戏目录) |
| `mouse_drag_key` | int \| null | | 虚拟键码，切换到此状态后发送。`null`=不发送。可从 .kmp 文件自动解析 |
| `priority` | int | | 多状态竞争时的优先级，默认 0。越大越优先 |
| `match_logic` | str | ✅ | `"any"` = 任一模板匹配即通过 / `"all"` = 全部模板必须匹配 |
| `templates` | list | ✅ | 模板列表 |

### 4.2 templates 条目

```json
{ "path": "templates/vehicle/Drive_1_upArrow.png", "region": "tl_arrow_up" }
```

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `path` | str | ✅ | 模板 PNG 相对路径 |
| `region` | str | | regions 中的区域 ID，默认 `"default"` |
| `matching_mode` | str | | `"pixel"`(默认) / `"hog"` / `"edge"` |
| `threshold` | float | | 单模板阈值覆盖 |

### 4.3 min_pass_ratio — 宽松 all 逻辑

仅 `match_logic: "all"` 且模板 ≥ 3 时生效：

```json
{ "match_logic": "all", "min_pass_ratio": 0.75 }
```

| min_pass_ratio | 4 模板 | 5 模板 | 效果 |
|---|---|---|---|
| 无 (默认) | 4/4 | 5/5 | 全部必须通过全局阈值 |
| 0.75 | 3/4 | 4/5 | ≥75% 通过即可，combined = 通过者最低分 |

2 模板的 `all` 不会放宽（安全考虑）。

### 4.4 negative_templates — 反向抑制

```json
{
  "negative_templates": [
    { "path": "templates/vehicle/Drive_carHorn.png", "region": "br_car_horn" }
  ],
  "negative_penalty": 0.50
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `negative_templates` | list | 反向模板列表，格式同 `templates` |
| `negative_penalty` | float | 压制强度，默认 0.50 |

**逻辑**: 当任意反向模板匹配分数 ≥ 0.35 时，state 的 combined 分数乘以 `(1 - penalty × best_neg/0.75)`。

典型场景：`vehicle_passenger` 的 `leaveVehicle` 按钮在驾驶场景中可能误匹配，用 `Drive_carHorn` 做反向模板压制其分数。

---

## 5. none_state — 无匹配状态

```json
{
  "none_state": {
    "keymap": "keymaps/GTASA(walk mode).kmp",
    "mouse_drag_key": null
  }
}
```

当所有 state 分数都低于阈值且 `none_state_switch: true` 时触发。

---

## 6. 添加新游戏 Checklist

1. 复制 `games/_template/` → `games/<新游戏>/`
2. 编辑 `game.json`：填写 package / states / regions
3. 截图放入 `templates/`（**1920×1080 PNG，建议工具内置截图功能输出**）
4. 从 LDPlayer 导出 .kmp → `keymaps/`
5. 运行 `scripts/templateDebugger.py` 调试每个模板的 region
6. 用 EXE 实测

---

## 7. templateDebugger 调试流程

```bash
# 单模板
python scripts/templateDebugger.py \
  --screenshot codm_walk.png \
  --template "games/CODM/templates/walk+swim+flying/jump.png"

# 多模板
python scripts/templateDebugger.py \
  --screenshot codm_vehicle.png \
  --template "games/CODM/templates/vehicle/Drive_1_upArrow.png" \
            "games/CODM/templates/vehicle/Drive_1_downArrow.png" \
  --output debug_arrows
```

输出 `*_debug.png`：红色框=搜索区域，绿色/黄色=匹配位置，每个模板独立标注。
