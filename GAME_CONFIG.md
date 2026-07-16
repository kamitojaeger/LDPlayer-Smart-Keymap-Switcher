# Game Config Format Specification

> *[中文版](GAME_CONFIG_zh_CN.md)*

> Version: schema v2 | Last updated: 2026-07-16

Each game has its own folder `games/<name>/` containing `game.json` + `keymaps/` + `templates/`.

---

## 1. Top-Level Structure

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

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | int | ✅ | Always `2` |
| `name` | str | ✅ | Display name of the game |
| `package` | str \| str[] | ✅ | Android package name(s), used for dir_kmps.dir filtering. Use array for multiple packages |
| `resolution` | object | | Reference resolution, default 1920×1080 |
| `detection` | object | ✅ | Detection parameters |
| `regions` | object | ✅ | Named region pool |
| `states` | list | ✅ | State definition list |
| `none_state` | object | | Keymap to use when no state matches |

---

## 2. detection — Detection Parameters

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

| Field | Default | Description |
|---|---|---|
| `ref_game_w` | 1920 | Reference game area width |
| `ref_game_h` | 1080 | Reference game area height |
| `ref_titlebar_h` | 60 | Title bar height (auto-ignored in RenderWindow mode) |
| `match_threshold` | 0.75 | Global match threshold |
| `feature_mask.dark_percentile` | 22 | Dark pixel percentile |
| `feature_mask.bright_percentile` | 82 | Bright pixel percentile |

---

## 3. regions — Search Regions (xywh format)

**Recommended xywh format** (based on 1920×1080 reference coordinate system):

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

| Field | Type | Description |
|---|---|---|
| `x` | int | Expected top-left X of the template (1920×1080 reference) |
| `y` | int | Expected top-left Y of the template |
| `width` | int | Region width (0 = use template's actual width) |
| `height` | int | Region height (0 = use template's actual height) |
| `search_expand` | int | Pixel expansion in all 4 directions, default 8 |

**Search rectangle** = `(x-expand, y-expand, x+width+expand, y+height+expand)`

**Constraints**: `x + template_width + expand ≤ 1920`, `y + template_height + expand ≤ 1080`. Violation triggers `TPL TOO LARGE` error.

**Legacy format** (compatible with GTASA, not recommended for new games):

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

Supports 5 positioning methods: `bottom_right` / `bottom_left` / `top_right` / `top_left` / `center`.

---

## 4. states — State Definitions

### 4.1 Base Fields

```json
{
  "id": "vehicle_drive_1",
  "name": "Vehicle Driving",
  "description": "Vehicle driving state — four arrow outer rings visible",
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

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | str | ✅ | Unique identifier, used in logs and state machine |
| `name` | str | | Display name |
| `description` | str | | Description |
| `keymap` | str | ✅ | Relative path to .kmp file (relative to game directory) |
| `mouse_drag_key` | int \| null | | Virtual key code to send after switching. `null` = don't send. Auto-parsed from .kmp if omitted |
| `priority` | int | | Priority when multiple states compete, default 0. Higher = wins |
| `match_logic` | str | ✅ | `"any"` = any template match passes / `"all"` = all templates must match |
| `templates` | list | ✅ | Template list |

### 4.2 Template Entries

```json
{ "path": "templates/vehicle/Drive_1_upArrow.png", "region": "tl_arrow_up" }
```

| Field | Type | Required | Description |
|---|---|---|---|
| `path` | str | ✅ | Relative path to template PNG |
| `region` | str | | Region ID from regions pool, default `"default"` |
| `matching_mode` | str | | `"pixel"`(default) / `"hog"` / `"edge"` |
| `threshold` | float | | Per-template threshold override |

### 4.3 min_pass_ratio — Relaxed "all" Logic

Only applies when `match_logic: "all"` and templates ≥ 3:

```json
{ "match_logic": "all", "min_pass_ratio": 0.75 }
```

| min_pass_ratio | 4 templates | 5 templates | Effect |
|---|---|---|---|
| None (default) | 4/4 | 5/5 | All must pass global threshold |
| 0.75 | 3/4 | 4/5 | ≥75% passing is sufficient, combined = minimum score among passers |

2-template `all` is never relaxed (safety).

### 4.4 negative_templates — Negative Suppression

```json
{
  "negative_templates": [
    { "path": "templates/vehicle/Drive_carHorn.png", "region": "br_car_horn" }
  ],
  "negative_penalty": 0.50
}
```

| Field | Type | Description |
|---|---|---|
| `negative_templates` | list | Negative template list, same format as `templates` |
| `negative_penalty` | float | Suppression strength, default 0.50 |

**Logic**: When any negative template match score ≥ 0.35, the state's combined score is multiplied by `(1 - penalty × best_neg/0.75)`.

Typical use case: `vehicle_passenger`'s `leaveVehicle` icon may falsely match in driving scenes; use `Drive_carHorn` as a negative template to suppress its score.

---

## 5. none_state — No-Match State

```json
{
  "none_state": {
    "keymap": "keymaps/GTASA(walk mode).kmp",
    "mouse_drag_key": null
  }
}
```

Triggered when all state scores fall below the threshold and `none_state_switch: true`.

---

## 6. Adding a New Game — Checklist

1. Copy `games/_template/` → `games/<new_game>/`
2. Edit `game.json`: fill in package / states / regions
3. Place screenshots in `templates/` (**1920×1080 PNG**)
4. Export .kmp from LDPlayer → `keymaps/`
5. Run `scripts/templateDebugger.py` to debug region for each template
6. Test with the EXE

---

## 7. templateDebugger Usage

```bash
# Single template
python scripts/templateDebugger.py \
  --screenshot codm_walk.png \
  --template "games/CODM/templates/walk+swim+flying/jump.png"

# Multiple templates
python scripts/templateDebugger.py \
  --screenshot codm_vehicle.png \
  --template "games/CODM/templates/vehicle/Drive_1_upArrow.png" \
            "games/CODM/templates/vehicle/Drive_1_downArrow.png" \
  --output debug_arrows
```

Output `*_debug.png`: red boxes = search regions, green/yellow = match positions, each template labeled independently.
