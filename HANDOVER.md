# 项目交接文档 — LDPlayer Auto Input Switcher

> 最后更新: 2026-07-16 | 项目状态: 生产就绪，通过 GTASA + CODM 双游戏验证，准备用户试用
>
> **Target audience**: 接手开发的 Agent/开发者，需要快速理解项目全貌并能修改/扩展。

---

## 1. 一句话概述

通过 OpenCV 模板匹配识别游戏画面 → 状态机去抖 → C++ DLL 注入切换 LDPlayer 按键方案。零用户交互，后台静默运行。

---

## 2. 快速上手 (5 分钟)

```bash
# 开发环境: Python 3.11+ 即可
pip install -r requirements.txt
python main.py

# 打包发布:
python scripts/package.py
# → dist_package/AutoInputSwitcher.exe (119MB, --onefile)

# C++ 重新编译 (需要 MSVC 2022):
cd src/core && powershell -File build.ps1
# → dist/keymap_hook.dll (87KB) + dist/keymap_injector.exe (136KB)

# 测试模板匹配:
python -c "from src.detector.matcher import match_template; ..."
```

---

## 3. 项目规模 (2026-07-15)

| 指标 | 值 |
|---|---|
| Python 代码 | ~2,500 lines (13 个模块) |
| C++ 代码 | ~737 lines (hook + injector + asm) |
| 游戏配置 | 3 个 (GTASA 2 states, CODM 12 states, Black Russia 2 states) |
| 模板文件 | 24 张 PNG (GTASA 2 + CODM 22) |
| .kmp 按键 | 11 个 (GTASA 2 + CODM 7 + _template 2) |
| EXE 体积 | 119MB (PyInstaller --onefile) |
| 代码行数分布 | `main.py` 483 | `matcher.py` 449 | `config.py` 463 | `monitor.py` 531 |

---

## 4. 核心架构

### 4.1 数据流

```
[截图] capture.py                           # RenderWindow 子窗口 / dxcam 回退
   ↓ 1920×1080 BGR numpy array
[匹配] matcher.py                           # feature_mask + TM_CCOEFF_NORMED + 区域裁剪
   ↓ {state_id: match_score, ...}
[去抖] state_machine.py                     # 连续 N 帧一致 + 优先级竞争
   ↓ target_state_id
[切换] main.py → injector.py               # subprocess 调用 keymap_injector.exe
   ↓ CreateFileW hook → CFW redirect
[提示] overlay.py                           # Tkinter 半透明 Toast
```

### 4.2 模块职责

| 文件 | 行数 | 职责 |
|---|---|---|
| `src/detector/capture.py` | — | 找 LDPlayer 窗口 → dxcam 截图 (BGR array) |
| `src/detector/matcher.py` | 449 | feature_mask 生成 + `match_template` + `match_multi` + `compute_search_rect` |
| `src/detector/state_machine.py` | 122 | `update(match_results)` → 去抖 → `(changed, old, new)` + priority 排序 |
| `src/detector/monitor.py` | 531 | QThread 监控循环 + 键位去重 (`_last_loaded_kmp`) |
| `src/detector/overlay.py` | — | Tkinter 半透明 Toast |
| `src/shared/config.py` | 463 | `GameConfig.from_json()` — 解析 game.json, 自动补 priority/package, `to_monitor_config()` |
| `src/shared/injector.py` | — | `Injector.init()` / `switch()` — 封装 keymap_injector.exe 子进程 |
| `src/shared/ldplayer.py` | — | LDPlayer 进程检测 / 路径枚举 / 版本匹配 |
| `src/shared/i18n.py` | — | JSON-based i18n, 系统语言自动检测 |
| `src/gui/` | 6 个文件 | PySide6 GUI (main_window / settings / tray / about / app) |
| `main.py` | 483 | CLI 入口 + GUI 入口 + `_prepare_keymap_environment()` |

---

## 5. C++ 注入核心

### 5.1 策略: CFW Redirect (v2)

Ctrl+F 触发后 LDPlayer 读取 3 次 .kmp:

| 次数 | 内容 | 行为 |
|---|---|---|
| [0] | 当前方案 | **不重定向** (让 LDPlayer 识别当前位置) |
| [1] | 下一个方案 | **重定向到目标 .kmp** |
| [2] | 下一个方案(再读) | **重定向到目标 .kmp** |

**效果**: 内部索引 = 下一个方案名，实际内容 = 目标方案 → 实际键位 = 目标。

### 5.2 关键常量

| 项目 | 值 |
|---|---|
| 编译目标 | x86 (32-bit) — dnplayer.exe 是 32 位 |
| CFW hook | kernelbase.CreateFileW |
| CALL hook | dnplycore.dll `call setKeyboardConfig` |
| 共享内存名 | `LDKeymapSwitch_Mem` |
| 鼠标按键 | keybd_event (非 SendInput) |

### 5.3 LDPlayer 版本偏移

| 版本 | HOOK_RVA | FUNC_RVA | RTRN_RVA |
|---|---|---|---|
| LDPlayer 9 海外版 | 0x2019C | 0x9CA10 | 0x201A1 |
| LDPlayer 14 海外版 | 0x1DA53 | 0x96130 | 0x1DA58 |

**注意**: V14 偏移于 2026-07-15 更新为 0x1DA53 (之前版本为 0x1DD33)。`keymap_hook.cpp` DllMain 中通过特征匹配 `E8 (CALL) → target` 自动选择正确的偏移组。

### 5.4 SharedData 结构

在 `keymap_hook.cpp` 和 `keymap_injector.cpp` 中**各自定义**（必须一致）。Layout:

```cpp
magic(4) | targetPath[1024] | flags(4) | fullPath[1024](WCHAR×1024) |
savedInstance(4) | funcAddress(4) | hookStatus(4) | hookCount(4) |
lastThis(4) | lastOriginalArg(4) | lastReplacementArg(4) | lastHookEsp(4) |
callTarget(4) | cfwKmpCount(4) | cfwRedirectCount(4) |
lastKmpPath[1024](WCHAR) | lastRequestedKmpPath[1024](WCHAR) |
kmpHistoryCount(4) | kmpHistory[8][260](WCHAR) | kmpHistoryRedirected[8](4) |
// Plan B (GUI piggyback):
wmSwitchMsg | guiThreadId | wndprocInstalled | subclassHwnd |
switchPending | switchResult | switchThreadId |
switchCfwBefore/After | switchHookBefore/After | switchArgMode
```

**修改 SharedData 时必须两边同步更新**，否则共享内存乱码。

---

## 6. 图像识别

### 6.1 feature_mask 生成 (`matcher.py`)

```python
gray = cv2.imread(template, IMREAD_GRAYSCALE)
dark  = np.percentile(gray, 22)  # 暗部阈值
bright = np.percentile(gray, 82)  # 亮部阈值
mask[dark]  = 255  # 深色 = 特征
mask[bright] = 255 # 亮色 = 特征
mask = dilate(mask) # 膨胀覆盖边缘
```

缓存策略: `_sample_mask_cache = {template_path: (gray, mask)}`，避免重复计算。

### 6.2 匹配方法

- `TM_CCOEFF_NORMED` + mask → 异常时回退无 mask
- 搜索区域由 `compute_search_rect()` 根据 region 配置裁剪
- 5 种定位方法: `bottom_right` / `bottom_left` / `top_right` / `top_left` / `center`

### 6.3 CODM 的 18 个精确 region

CODM 有 18 个独立 region，每个从 scan_regions.py 的实测扫描数据导出。不同车辆方向的按键位置不同（如坦克和轿车的左右箭头在不同位置），因此同一模板在不同 state 中使用不同 region：
- `br_arrow_right` (171,237) ≠ `br_arrow_right_tank` (387,294)
- `br_arrow_left` (441,237) ≠ `br_arrow_left_tank` (611,296)

### 6.4 常见模板问题

| 问题 | 原因 | 方案 |
|---|---|---|
| 匹配率虚低 | 模板方差低 (90%+ 中灰像素) | 裁掉多余背景，保留特征区域 |
| 两个模板匹配同一位置 | 模板重叠率 > 90% (如 heli_up/down) | 合并做组合模板或裁至极小 |
| CCOEFF 负分 | feature_mask 将透明背景(PNG alpha)当成暗部特征 | 改 mask 生成逻辑或改用不透明模板 |

---

## 7. 状态机 & 优先级

### 7.1 去抖

`StateMachine` 要求连续 `debounce_count` 帧匹配同一状态才触发切换。默认 1 帧 (即时切换)。

### 7.2 优先级竞争 (2026-07-14 新增)

同一帧中多个 state 超阈值时，按 `(priority DESC, score DESC)` 排序取第一。用于车辆场景——坦克驾驶 (pri=16) 优先级高于普通驾驶 (pri=12)。

```python
# state_machine.py
candidates = [(sid, info) for sid, info in results.items() if info["val"] >= threshold]
candidates.sort(key=lambda x: (priorities.get(x[0], 0), x[1]["val"]), reverse=True)
```

存量 game.json 无需改动——`config.py` 的 `_normalize()` 自动补 `priority: 0`。

### 7.3 键位去重 (2026-07-14 新增)

`monitor.py` 跟踪 `_last_loaded_kmp`，切换前比较目标 keymap，相同则跳过 `injector.switch()`。CODM 6 个 state 共用 `CODM((walk).kmp`，避免重复切换。

---

## 8. dir_kmps.dir 过滤 (Ctrl+F 下拉栏问题)

### 8.1 问题

LDPlayer 启动时从 `vms/recommendConfigs/dir_kmps.dir` (纯 JSON, 980 条) 一次性加载到内存。当某游戏匹配条目 ≥ 3 时，Ctrl+F 弹出下拉栏而非循环切换，导致 CFW redirect 失效。

### 8.2 解决方案

`main.py` 的 `_prepare_keymap_environment()` — 点击"启动监控"时执行:

```
1. 读 dir_kmps.dir → 删除所有匹配该游戏包名的条目 → 写回
2. 复制 games/<game>/keymaps/ 前 2 个 .kmp → customizeConfigs/ (已有同名跳过)
3. 检查 customizeConfigs/*.smp (按包名匹配) → 移动引用的旧 .kmp 到 userCustomizeKeymapBackup/
4. 如果 1/2/3 产生了任何改动 → 弹窗"请重启 LDPlayer" → return (不启动监控)
   否则 → 正常启动监控
```

**关键**: 此逻辑不需要 C++ hook（dir_kmps.dir 是 LDPlayer 启动时加载，hook 无法拦截）。直接修改磁盘文件 + 告知用户重启。

---

## 9. 配置系统

### 9.1 game.json 关键字段

```json
{
  "schema_version": 2,
  "package": "com.rockstar.gtasa" | ["com.a.a","com.b.b"],  // str 或 list
  "detection": { "threshold": 0.75, "dark_percentile": 22, ... },
  "regions": { "region_id": { "method": "bottom_right", "margin_right": 40, ... } },
  "states": [
    { "id": "walk", "keymap": "keymaps/...", "priority": 0,
      "templates": [{ "path": "templates/...", "region": "region_id" }],
      "match_logic": "all"|"any" }
  ],
  "none_state": { "keymap": "...", "mouse_drag_key": null }
}
```

完整 schema: `Project_Overhaul/DATA_SCHEMA.md`

### 9.2 settings.json

```json
{
  "poll_interval_ms": 333,    // 检测间隔
  "debounce_count": 1,        // 去抖帧数  
  "match_threshold": 0.75,    // 匹配阈值
  "language": "",             // 空 = 自动检测
  "show_toast": true,         // 切换提示
  "none_state_switch": false  // 无匹配释放鼠标
}
```

首次启动所有字段自动初始化为默认值。

### 9.3 添加新游戏

1. 复制 `games/_template/` → `games/<新游戏>/`
2. 编辑 `game.json`
3. 截图放入 `templates/` (1920×1080 PNG)
4. 导出 .kmp → `keymaps/`
5. 运行 `scan_regions.py` 辅助推算 region
6. 重启工具自动加载

---

## 10. 开发工具

### 10.1 scan_regions.py

全图模板匹配 + regions config 推算:

```bash
python scripts/scan_regions.py \
    --screenshot game_1920x1080.png \
    --templates templates/*.png \
    --output scan_result

# 输出: scan_result/scan_debug.png + regions_snippet.json
```

原理: 调用 `match_template()` 全图搜索 → 取最佳位置 → 反推 margin 参数 → 自动合并相近 region。

### 10.2 直接调 matcher 测试

```bash
python -c "
from src.detector.matcher import match_template
import cv2
img = cv2.imread('screenshot.png')
h,w = img.shape[:2]
score,loc,_,_ = match_template(img, 'tpl.png', h/1080, 0, 0, w, h)
print(f'score={score:.4f} loc={loc}')
"
```

### 10.3 dir_kmps.dir 恢复

```bash
# 恢复原始 (如果过滤出错):
cp F:/LDPlayer/LDPlayer9/vms/recommendConfigs/dir_kmps.dir.backup \
   F:/LDPlayer/LDPlayer9/vms/recommendConfigs/dir_kmps.dir
```

---

## 11. 编译 & 部署

### C++

```powershell
cd src/core
.\build.ps1          # 编译 keymap_hook.dll + keymap_injector.exe
cp keymap_hook.dll ..\..\dist\
cp keymap_injector.exe ..\..\dist\
```

编译环境: VS 2022 Community, MSVC 14.51, Windows SDK 10.0.26100, x86 target.

### Python → EXE

```bash
python scripts/package.py
# 输出: dist_package/
#   AutoInputSwitcher.exe         # PyInstaller --onefile
#   dist/                         # C++ 预编译组件
#   games/ config/ locales/       # 数据目录
```

打包逻辑自动:
- 清空 `config/settings.json` 中的 `install_path`/`language`
- 检查 `scripts/package.py` 中的 `INCLUDE_GAMES` 列表
- 复制 C++ binaries + game data + configs + locales

---

## 12. 已知问题 & 限制

| 问题 | 严重度 | 说明 |
|---|---|---|
| CFW hook 非线程安全 | 🟡 | "恢复-调用-重装" 模式，需 trampoline 改造 |
| 国内版 LDPlayer 不支持 | 🔴 | Ctrl+F 机制不同，已放弃 |
| DLL 注入杀软误报 | 🟡 | 添加 Defender 排除文件夹 |
| dir_kmps.dir 仅启动时加载 | 🟢 | 已通过磁盘修改 + 重启提示解决 |
| 低方差模板匹配率低 | 🟡 | 浅色半透明 UI (如 PUBG) 匹配率天生低 |
| QSpinBox 超范围值 | 🟢 | `_SpinBoxClampFilter` 已修复 (2026-07-12) |
| setKeyboardTracking(False) | 🟢 | 已全部移除，会导致手动编辑被丢弃 |

---

## 13. 备份 & 历史版本

`hook_demo/backup_vN/` **只读**，不可修改或删除:

| 版本 | 日期 | 要点 |
|---|---|---|
| v2 | 07-07 | CFW redirect, 仅 LD9 |
| v3 | 07-07 | 多版本兼容, kernelbase hook |
| v4 | 07-09 | init 预注入 |
| v5-v10 | 07-09 ~ 07-11 | 自动化/截图/Toast/窗口修复 |

调试日志和决策记录见 `.workbuddy/memory/` 目录。

---

## 14. 关键文件速查

| 你要做什么 | 看这个文件 |
|---|---|
| 改 C++ 注入逻辑 | `src/core/keymap_hook.cpp` + `hook_stub.asm` |
| 改匹配算法 | `src/detector/matcher.py` |
| 改状态机/优先级 | `src/detector/state_machine.py` |
| 改监控循环/键位去重 | `src/detector/monitor.py` |
| 改游戏配置格式 | `src/shared/config.py` + `Project_Overhaul/DATA_SCHEMA.md` |
| 改 GUI | `src/gui/` |
| 改 LDPlayer 检测 | `src/shared/ldplayer.py` |
| 改多语言 | `locales/zh_CN.json` + `en_US.json` + `src/shared/i18n.py` |
| 改打包逻辑 | `scripts/package.py` |
| 添加新游戏 | `games/_template/game.json` → 复制 → 编辑 |
| 扫描新游戏 region | `scripts/scan_regions.py` |
| 了解逆向工程细节 | `PROJECT_SUMMARY.md` + `docs/` |
| 恢复 dir_kmps.dir | `dir_kmps.dir.backup` (自动生成) |

---

## 15. 日常开发 Checklist

- [ ] 改 `SharedData` → 同时更新 `.h` 式的两边定义
- [ ] 改 C++ → `build.ps1` → 复制到 `dist/`
- [ ] 改 Python → `package.py` (如需发版)
- [ ] 改 game.json → 运行工具验证加载正常
- [ ] 改 locale → 两边 JSON 同步更新
- [ ] 新游戏 → 先 `scan_regions.py` 获取 region 再用
- [ ] 交付前 → 清理 `settings.json` 的 `install_path` / `language`

---

## 16. 2026-07-16 更新摘要

### 16.1 Region 体系: margin → xywh

Search regions 现在是 **1920×1080 基准像素坐标**（旧格式仍兼容 GTASA）：

```json
// 旧 (margin)
{"method":"bottom_right","margin_right":4,"margin_bottom":250,"slack":20}
// 新 (xywh)  
{"x":1748,"y":694,"width":136,"height":136,"search_expand":16}
```

Search rect = `(x-expand, y-expand, x+w+expand, y+h+expand)`。注意 x 必须 ≤ `1920 - 模板宽 - expand`。

### 16.2 匹配模式 (matching_mode)

每个模板可单独选择匹配算法：

| 值 | 算法 | 适用场景 |
|---|---|---|
| `"pixel"` (默认) | TM_CCOEFF_NORMED + feature_mask | 高对比度图标 |
| `"hog"` | Sobel gradient magnitude → TM_CCOEFF_NORMED | 亮度变化大但边缘稳定的 UI |
| `"edge"` | Canny 二值 → TM_CCORR_NORMED | (测试效果不佳，代码保留) |

### 16.3 宽松 "all" 逻辑 (min_pass_ratio)

3+ 模板的 `match_logic:"all"` 状态可加 `min_pass_ratio` 避免一个模板拉低全局：

```json
{"id":"vehicle_drive_1","match_logic":"all","min_pass_ratio":0.75}
// 4 模板 → 至少 3 个通过阈值即算匹配，combined = 通过者中最低分
// 2 模板不放松（安全考虑）
```

### 16.4 反向模板 (negative_templates)

抑制误匹配——当 anti 信号存在时降分：

```json
{"id":"vehicle_passenger","negative_templates":[
  {"path":"templates/vehicle/Drive_carHorn.png","region":"br_car_horn"}
],"negative_penalty":0.5}
// Drive_carHorn 匹配 ≥ 0.35 → vehicle_passenger 分数 × 0.5
```

### 16.5 ⚠️ 配置透传链

**任何新增到 game.json 的字段，必须经过三层透传才能到达 match_multi：**

| 层 | 文件 & 函数 | 
|---|---|
| 1 | `config.py::to_monitor_config()` + `state_configs_for_matcher()` |
| 2 | `monitor.py` 的 `state_configs` 构建 (两处：QThread 主循环 + CLI) |
| 3 | `match_multi()` 的 `state` 读取 |

缺失任何一层 = 字段静默丢失 = 功能不生效。今天已修复 `matching_mode`/`min_pass_ratio`/`negative_templates` 三字段的透传遗漏。

### 16.6 templateDebugger

独立脚本，不打包进 EXE。支持多模板调试：

```bash
python scripts/templateDebugger.py \
  --screenshot codm.png \
  --template "jump.png" "sneak.png" "Flying.png" \
  --output debug_result
```

自动检测 1920×1080 纯游戏区截图 vs 含标题栏截图，scale 与 EXE 完全一致。

### 16.7 Debug 截图

`draw_debug_overlay` 现显示每个模板的独立匹配框（带文件名 + 分数），而非仅 state 级别汇总。

### 16.8 game.json 完整格式

见 **`GAME_CONFIG.md`**（新文档）。
