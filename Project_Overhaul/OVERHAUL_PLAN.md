# LDPlayer Auto Input Switcher — 项目重构总体规划

> **版本**: 1.2  
> **日期**: 2026-07-11  
> **状态**: Phase 1-5 已完成，多区域 schema v2 已规划  
> **目标受众**: 后续接手重构的开发 agent / 协作者

---

## 1. 项目背景

LDPlayer（雷电模拟器）按键方案自动切换工具。

**核心机制（策略 v2 / CFW 重定向）**：
1. `keymap_hook.dll` 注入到 `dnplayer.exe`，hook `kernelbase.CreateFileW`
2. Ctrl+F 触发 LDPlayer 3 次读取 `.kmp`：[0]=当前方案(不拦截)，[1][2]=下一方案→重定向到目标内容
3. 效果：内部索引不变，但实际加载的键位 = 目标方案

**当前版本演进**：v2 → v10（见 `hook_demo/backup_vN/`，共 9 个备份，注意绝对不能修改备份文件夹中的东西）

| 版本 | 增量 |
|---|---|
| v2 | CFW 重定向策略，核心需求达成 |
| v3 | 多版本兼容 (LDPlayer9 + LDPlayer14) |
| v4 | `init` 预初始化命令 |
| v5 | OpenCV 模板匹配 walk/drive 状态检测 + 自动切换 |
| v6 | keybd_event 射击视角自动恢复 |
| v7 | 切换延时优化 1550ms → 650ms |
| v8 | Toast 覆盖层 |
| v9 | RenderWindow 纯安卓画面截图 |
| v10 | 修复最大化窗口退出 Bug |

**当前技术栈**：
- C++ x86 (VS 2022 + MSVC + MASM)：DLL 注入 + inline hook
- Python 3.11+：dxcam 截图 + OpenCV 模板匹配 + 状态机 + 自动切换
- 编译依赖 VS 2022 Community + Windows SDK 10.x

---

## 2. 重构目标

1. **现代化 GUI** — 图形界面替代命令行，系统托盘 + 一键启停 + 状态显示
2. **多游戏支持** — 游戏模板/按键/配置统一管理，JSON 配置驱动
3. **便捷部署** — PyInstaller 打包，用户解压即用，无需安装任何环境
4. **多语言支持** — 简体中文 + 英文，初次启动跟随系统语言，可在设置中切换

---

## 3. 架构设计

```
┌─────────────────────────────────────────────────┐
│                  GUI 层 (PySide6)                 │
│  主窗口 · 系统托盘 · 游戏面板 · 设置 · 关于       │
├─────────────────────────────────────────────────┤
│                检测层 (Python)                    │
│  截图 → 模板匹配 → 状态机 → injector → Toast     │
├─────────────────────────────────────────────────┤
│                核心层 (C++ x86)                   │
│  keymap_hook.dll + keymap_injector.exe           │
├─────────────────────────────────────────────────┤
│                数据层 (games/)                    │
│  gtasa/ · pubg/ · _template/ · + 更多...         │
├─────────────────────────────────────────────────┤
│                配置层 (config/)                   │
│  settings.json · ldplayer_versions.json          │
└─────────────────────────────────────────────────┘
```

**数据流**：
```
用户点击"启动" → QThread 启动监控循环
  → 每 500ms: capture.py 截图 (RenderWindow 优先, 回退 dxcam)
  → matcher.py: OpenCV 模板匹配 (带 feature mask)
  → state_machine.py: 检测状态变化 (去抖)
  → 若变化: injector.py 调用 keymap_injector.exe
  → 发送 mouse_drag_key (如需要) → overlay.py 显示 Toast
  → GUI 更新状态显示
```

**设计原则**：
- C++ 层**不动业务逻辑**，仅移动文件位置
- Python 层从单一脚本拆分为职责明确的模块
- 游戏数据与代码完全分离
- 所有路径/参数改为配置文件驱动，消除硬编码

---

## 4. 目标目录结构

```
LDPlayer_Auto_Input_Switcher/          # 项目根目录
│
├── main.py                             # 入口：GUI 启动器
├── requirements.txt                    # Python 依赖
├── .gitignore
├── README.md                           # 用户文档
│
├── src/
│   ├── core/                           # ═══ C++ 注入核心 ═══
│   │   ├── keymap_hook.cpp             #   Hook DLL 源码
│   │   ├── keymap_injector.cpp         #   注入器源码
│   │   ├── hook_stub.asm               #   CALL hook 汇编跳板
│   │   ├── version.rc                  #   版本资源
│   │   ├── build.ps1                   #   编译脚本
│   │   └── build.bat                   #   编译脚本
│   │
│   ├── detector/                       # ═══ Python 检测引擎 ═══
│   │   ├── __init__.py
│   │   ├── capture.py                  #   截图模块 (dxcam + RenderWindow)
│   │   ├── matcher.py                  #   OpenCV 模板匹配 + feature mask
│   │   ├── state_machine.py            #   状态机 (状态枚举 + 变化检测 + 去抖)
│   │   ├── overlay.py                  #   Toast 覆盖层
│   │   └── monitor.py                  #   监控主循环 (QThread)
│   │
│   ├── gui/                            # ═══ 图形界面 ═══
│   │   ├── __init__.py
│   │   ├── app.py                      #   QApplication + 单例检测
│   │   ├── main_window.py              #   主窗口: 标题栏 + 状态区 + 控制按钮
│   │   ├── system_tray.py              #   系统托盘: 图标 + 右键菜单
│   │   ├── game_panel.py               #   游戏选择 + 状态指示面板
│   │   ├── settings_dialog.py          #   设置对话框
│   │   └── about_dialog.py             #   关于对话框
│   │
│   └── shared/                         # ═══ 共享工具 ═══
│       ├── __init__.py
│       ├── config.py                   #   JSON 配置读写 + 路径解析
│       ├── injector.py                 #   keymap_injector.exe 的 Python 封装
│       ├── ldplayer.py                 #   LDPlayer 进程/窗口/版本检测
   │       └── logging_setup.py            #   日志配置
   │
   ├── locales/                            # ═══ 多语言资源 ═══
   │   ├── zh_CN.json                      #   简体中文翻译
   │   └── en_US.json                      #   English translations
   │
   ├── games/                              # ═══ 多游戏数据 (纯数据，无代码) ═══
│   ├── gtasa/                          #   GTA San Andreas
│   │   ├── game.json                   #     游戏元数据 + 状态定义
│   │   ├── templates/                  #     OpenCV 模板样本
│   │   │   ├── drive.png
│   │   │   └── walk.png
│   │   └── keymaps/                    #     LDPlayer 按键方案 .kmp
│   │       ├── drive_mode.kmp
│   │       └── walk_mode.kmp
│   │
│   ├── pubg/                           #   未来: PUBG Mobile
│   │   └── game.json
│   │
│   └── _template/                      #   添加新游戏的模板
│       ├── game.json                   #     → 复制并修改字段即可
│       ├── templates/                  #     → 放入样本截图
│       └── keymaps/                    #     → 放入 .kmp 文件
│
├── config/                             # ═══ 全局配置 ═══
│   ├── settings.json                   #   用户设置 (路径、间隔、行为、语言)
│   └── ldplayer_versions.json          #   LDPlayer 版本偏移表
│
├── locales/                            # ═══ 多语言 (i18n) ═══
│   ├── zh_CN.json                      #   简体中文
│   └── en_US.json                      #   English
│
├── dist/                               # ═══ 编译产物 (预编译，随发布包) ═══
│   ├── keymap_hook.dll                 #   预编译 Hook DLL (x86)
│   └── keymap_injector.exe             #   预编译注入器 (x86)
│
├── docs/                               # ═══ 文档 ═══
│   ├── DEV_GUIDE.md                    #   开发者文档 / 如何添加新游戏
│   └── REVERSE_ENGINEERING.md          #   逆向工程笔记
│
└── scripts/                            # ═══ 辅助脚本 ═══
    ├── build.bat                       #   编译 C++ 组件
    ├── build.ps1
    └── package.py                      #   PyInstaller 打包脚本

# ⚠️ 以下目录不在此次重构范围内，保持不变：
#
#   hook_demo/backup_vN/   — 历史版本备份，只读
#   hook_demo/test/        — 测试数据
#   *.py (根目录)           — 早期分析脚本，Phase 5 归档
#   __pycache__/           — 缓存
```

---

## 5. 关键设计决策

### 5.1 GUI 框架: PySide6 ✅

**选择理由**：
- LGPL 协议，自由商用
- `QSystemTrayIcon` 原生系统托盘支持
- `QThread` 天然适配后台监控循环（不改动现有 500ms 循环逻辑）
- Qt Designer 可辅助 UI 排版
- 打包体积约 40MB，可接受

**备选方案**：
- CustomTkinter：系统托盘支持弱，放弃
- Electron：体积 100MB+，与 C++ IPC 复杂，过度设计

### 5.2 多游戏配置: `game.json`

每个游戏一个文件夹，一个 `game.json` 描述一切。详见 `DATA_SCHEMA.md`。

**设计要点**：
- 状态列表 `states[]` 驱动状态机，支持多模板 + 多区域匹配
- `regions` 命名区域池，支持 5 种定位方法 (bottom_right/top_left/center 等)
- 检测参数可 per-game 覆盖
- 添加新游戏 = 复制 `_template/` + 改 JSON + 放素材，**零代码改动**
- v1→v2 自动兼容，现有 GTASA 配置无需修改

### 5.3 部署: PyInstaller

```bash
# 打包命令
pyinstaller --onefile --windowed \
  --add-data "dist;dist" \
  --add-data "games;games" \
  --add-data "config;config" \
  --name AutoInputSwitcher \
  main.py
```

**发布包结构**：
```
AutoInputSwitcher_v1.0/
├── AutoInputSwitcher.exe    # 主程序 (含 Python + 所有 pip 依赖)
├── dist/                    # C++ 预编译组件
├── games/                   # 游戏数据
├── config/                  # 默认配置
└── README.txt               # 快速开始
```

用户无需安装 Python、VS、OpenCV。首次启动自动检测 LDPlayer 安装路径和版本偏移。

### 5.4 C++ 层: 保持不动

`keymap_hook.cpp`、`keymap_injector.cpp`、`hook_stub.asm` **不修改业务逻辑**，仅移动文件到 `src/core/`。编译产物输出到 `dist/`。

### 5.5 Python 脚本拆分

现有 `screenshot_ldplayer.py` (~800 行) 拆分为：

| 新模块 | 来源 | 职责 |
|---|---|---|
| `capture.py` | 截图逻辑 | RenderWindow 枚举 + dxcam 回退 + 坐标转换 |
| `matcher.py` | 模板匹配 | OpenCV matchTemplate + feature mask + 坐标计算 |
| `state_machine.py` | 状态逻辑 | 状态枚举 + 去抖 + 变化检测 |
| `overlay.py` | `toast_overlay.py` | Toast 窗口 (几乎不改) |
| `monitor.py` | 主循环 | `init` → 循环 → 决策 → 调用 injector (改为 QThread) |

### 5.6 多语言 (i18n): JSON 资源文件 ✅

**选择理由**：
- 暂仅需 2 种语言 (zh_CN / en_US)，无需重型 i18n 框架
- JSON 格式简单，非开发人员也可编辑翻译
- Python 标准库 `locale` 模块即可检测系统语言
- `PySide6.QtCore.QLocale` 也可辅助检测

**文件格式** (`locales/zh_CN.json`, `locales/en_US.json`)：
```json
{
  "app.title": "LDPlayer 按键自动切换",
  "app.tray.start": "启动监控",
  "app.tray.stop": "停止监控",
  ...
}
```

**语言检测逻辑**：
1. 首次启动：读取 `settings.json` → `gui.language` 字段
2. 若未设置 (`""` 或 null) → 调用 `locale.getdefaultlocale()` 检测系统语言
3. 系统为中文 (`zh_CN` / `zh_*`) → 默认 `zh_CN`，其余 → 默认 `en_US`
4. 用户可在设置中切换，切换后写入 `settings.json` 并即时刷新 UI

**实现模块**：`src/shared/i18n.py`
```python
class I18n:
    def __init__(self, locale_dir: str): ...
    def load(self, lang: str): ...
    def t(self, key: str, **kwargs) -> str: ...
    def detect_system_language() -> str: ...
```

### 5.7 多区域模板匹配 (schema v2)

**问题**：Phase 3 的 v1 schema 中 `search_region` 是全局唯一定义 — 所有状态的模板都在同一屏幕区域搜索。
对于需要检查多处 UI 元素才能判断状态的游戏（如 PUBG 需同时检查小地图 + 武器槽），v1 无法表达。

**方案**：将搜索区域从全局下沉到每个 state 内部，形成 `regions` 池 + `templates[]` per-state 结构。

```
game.json (v2)
  ├─ regions: {             ← 命名区域定义池（可跨 state 复用）
  │    "minimap":  { method: top_right, ... },
  │    "hud":      { method: bottom_right, ... },
  │    "crosshair":{ method: center, ... }
  │  }
  │
  └─ states:
       ├─ { id: "walk",  templates: [{path, region:"hud"}],               match_logic:"any" }
       └─ { id: "drive", templates: [{path, region:"minimap"}, {path, region:"hud"}], match_logic:"all" }
```

**match_logic**：
- `"any"` — 任一模板命中即认为匹配（单模板场景、或任一指标均有效）
- `"all"` — 全部模板命中才认为匹配（多区域组合校验，防误判）

**region 定位方法**：`bottom_right`、`bottom_left`、`top_right`、`top_left`、`center`（5 种）

**向后兼容**：旧 `game.json`（无 regions/单 template）由 `GameConfig.from_json()` 自动标准化。详见 `DATA_SCHEMA.md` §1.4。

**影响范围**（后续实施）：
- `matcher.py`：`match_multi()` 改为遍历 `state.templates[]`，按 `region` 查不同搜索区域
- `config.py`：`GameConfig` 新增 `regions` 解析 + `state.templates` 标准化
- `state_machine.py`：**无需修改**（综合匹配值计算在 matcher 层完成）
- 现有 GTASA 配置：**无需修改**（自动标准化）

---

## 6. 分阶段实施计划

### Phase 1: 文件结构调整

**目标**：建立新目录骨架，移动文件，不改代码逻辑。

| 步骤 | 操作 |
|---|---|
| 1.1 | 创建 `src/core/`、`src/detector/`、`src/gui/`、`src/shared/`、`games/`、`config/`、`dist/`、`docs/`、`scripts/` |
| 1.2 | 复制 C++ 源码到 `src/core/`（保留 `hook_demo/` 原文件不动） |
| 1.3 | 复制编译产物到 `dist/` |
| 1.4 | 复制 `toast_overlay.py` → `src/detector/overlay.py`（先不拆分，整体移入） |
| 1.5 | 创建 `config/settings.json` 和 `config/ldplayer_versions.json` |
| 1.6 | 创建 `games/gtasa/game.json`，复制模板和 .kmp |
| 1.7 | 创建 `games/_template/` |
| 1.8 | 创建 `requirements.txt` (project root) |

**验证**：目录结构完整，无文件丢失。

### Phase 2: Python 模块拆分

**目标**：把 `screenshot_ldplayer.py` 拆分为独立的 detector 模块。

| 步骤 | 操作 |
|---|---|
| 2.1 | 提取 `capture.py`：`get_dnplayer_render_rect()`、`get_dnplayer_client_rect()`、`resolve_capture_target()`、截图逻辑 |
| 2.2 | 提取 `matcher.py`：`match_sample_in_corner()`、`match_drive_walk()`、feature mask、坐标计算 |
| 2.3 | 提取 `state_machine.py`：状态枚举、去抖、变化检测逻辑 |
| 2.4 | 提取 `monitor.py`：`run_monitor_loop()`（先保持单线程，后续改 QThread） |
| 2.5 | 整合 `overlay.py`：将 `toast_overlay.py` 内容保持不动移入 |
| 2.6 | 创建 `src/detector/__init__.py`：导出公共接口 |
| 2.7 | 创建 `main.py` 临时入口：先用 CLI 参数验证拆分后功能正常 |

**验证**：`python main.py` 能正常启动监控循环，GTASA 切换功能正常。

### Phase 3: 配置化 & 多游戏支持

**目标**：消除硬编码，实现配置驱动。

| 步骤 | 操作 |
|---|---|
| 3.1 | 实现 `src/shared/config.py`：JSON 加载/保存/路径解析 |
| 3.2 | 修改 `monitor.py` 从 `game.json` 读取状态定义、模板路径、.kmp 路径 |
| 3.3 | 实现 `src/shared/ldplayer.py`：自动检测 LDPlayer 安装路径和版本 |
| 3.4 | 将 `keymap_injector.cpp` 中的硬编码偏移移到 `ldplayer_versions.json` |
| 3.5 | 实现游戏自动扫描：遍历 `games/` 目录，读 `game.json` |

**验证**：放一个新的游戏模板（如 mock game），能被自动扫描并加载。

> **注意**：Step 3.4 涉及 C++ 层改动。`ldplayer_versions.json` 可以被 Python 层读取后通过命令行参数传给 `keymap_injector.exe`，或未来在 DLL 中通过共享内存读取。优先走 Python 传参方案，不改 C++。

### Phase 4: GUI 开发

**目标**：构建完整的 PySide6 图形界面。

| 步骤 | 操作 |
|---|---|
| 4.1 | `src/gui/app.py`：QApplication 初始化、单例检测、DPI 感知 |
| 4.2 | `src/gui/main_window.py`：主窗口布局 (标题栏 + 状态区 + 按钮) |
| 4.3 | `src/gui/game_panel.py`：游戏下拉框 + 状态指示器 (当前模式、匹配率) |
| 4.4 | `src/gui/system_tray.py`：系统托盘图标 + 右键菜单 (启动/停止/显示/退出) |
| 4.5 | `src/gui/settings_dialog.py`：设置项 (检测间隔、阈值、LDPlayer 路径) |
| 4.6 | `src/gui/about_dialog.py`：版本号、开源声明 |
| 4.7 | 将 `monitor.py` 改为 QThread，信号/槽连接 GUI 更新 |
| 4.8 | 实现 `src/shared/i18n.py`：语言检测 + JSON 资源加载 + `t()` 翻译函数 |
| 4.9 | 创建 `locales/zh_CN.json` 和 `locales/en_US.json` 翻译文件 |
| 4.10 | 集成 i18n 到 GUI：所有显示文本通过 `i18n.t()` 获取，语言切换时实时刷新 |
| 4.11 | 实现 `main.py` 最终入口：启动 GUI |

**验证**：GUI 可启动，选择游戏 → 点 Start → 监控运行 → 状态实时显示 → 点 Stop 停止。

### Phase 5: 打包 & 清理

**目标**：产出一键部署包，清理历史遗留文件。

| 步骤 | 操作 |
|---|---|
| 5.1 | 编写 `scripts/package.py`：PyInstaller 打包配置 |
| 5.2 | 测试打包产物在干净系统上运行 |
| 5.3 | 编写 `README.md` (用户文档) |
| 5.4 | 编写 `docs/DEV_GUIDE.md` (开发者指南) |
| 5.5 | 整合逆向工程笔记 → `docs/REVERSE_ENGINEERING.md` |
| 5.6 | 将根目录 `*.py` (分析脚本) 移到 `archive/` |
| 5.7 | 清理 `__pycache__/` |
| 5.8 | 验证：`hook_demo/backup_vN/` 未被修改 |

**验证**：发布包在无 Python 环境的 Windows 上解压即用。

---

## 7. 关键接口定义

### 7.1 `monitor.py` — 监控主循环接口

```python
class MonitorThread(QThread):
    """后台监控线程，500ms 周期"""

    # Signals → GUI
    status_changed = Signal(str, str)        # (old_state_id, new_state_id)
    match_score = Signal(float)              # 当前匹配率
    screenshot_ready = Signal(np.ndarray)    # 调试截图
    error_occurred = Signal(str)             # 错误信息

    def __init__(self, game_config: GameConfig, settings: AppSettings): ...
    def run(self): ...
    def stop(self): ...
```

### 7.2 `capture.py` — 截图模块接口

```python
def get_dnplayer_render_rect() -> tuple[int, int, int, int] | None:
    """枚举 dnplayer 子窗口，返回 RenderWindow 屏幕坐标 (left, top, right, bottom)"""

def get_dnplayer_client_rect() -> tuple[int, int, int, int]:
    """回退方案：GetClientRect"""

def capture_frame(target_info: dict) -> np.ndarray:
    """截图主入口，自动选择 RenderWindow / dxcam"""
```

### 7.3 `matcher.py` — 模板匹配接口

```python
def match_template(
    screenshot: np.ndarray,
    template_path: str,
    scale: float,
    region_config: dict           # ← 来自 game.json regions 池的单个区域定义
) -> tuple[float, tuple[int, int, int, int]]:
    """在指定区域搜索单个模板，返回 (匹配率, 匹配框坐标)"""

def match_multi(
    screenshot: np.ndarray,
    state_config: StateConfig,    # ← 单个 state 的完整配置 (含 templates[] + match_logic)
    regions: dict[str, dict],     # ← 全局 regions 池
    detection_config: dict,
    capture_source: str = ""
) -> dict[str, float]:
    """
    对单个 state 的所有模板做多区域匹配。
    - match_logic="any": 返回最佳匹配率
    - match_logic="all": 返回最低匹配率（全通过则为通过，有一个失败即 0）
    返回 {state_id: combined_score}
    """
```
> `capture.py`、`monitor.py` 接口不变。

### 7.4 `shared/injector.py` — 注入器封装

```python
class Injector:
    def __init__(self, injector_path: str, dll_path: str): ...

    def init(self) -> bool:
        """预初始化：keymap_injector.exe init"""

    def switch(self, kmp_path: str) -> bool:
        """切换按键：keymap_injector.exe <kmp_path>"""

    def status(self) -> dict:
        """获取诊断信息：keymap_injector.exe --status"""

    def send_mouse_drag_key(self, vk_code: int):
        """发送射击视角恢复键 (keybd_event)"""
```

### 7.5 `shared/config.py` — 配置管理

```python
class GameConfig:
    """单个游戏的完整配置"""
    schema_version: int           # 1=旧格式, 2=新格式 (regions + templates[])
    name: str
    package: str
    resolution: tuple[int, int]
    states: list[StateConfig]
    detection: DetectionConfig
    regions: dict[str, dict]     # v2: {region_id: {method, margins, ...}}

    @classmethod
    def from_json(cls, path: str) -> "GameConfig":
        """加载并自动标准化：v1→v2 (regions.default + templates 包装)"""

    @classmethod
    def scan_games(cls, games_dir: str) -> list["GameConfig"]: ...

    def to_matcher_config(self) -> dict: ...
    def to_monitor_config(self, injector_path: str) -> "MonitorConfig": ...

class AppSettings:
    """全局应用设置"""
    ldplayer_path: str
    ldplayer_version: str
    poll_interval_ms: int
    auto_start: bool

    @classmethod
    def load(cls, path: str) -> "AppSettings": ...
    def save(self, path: str): ...
```

---

## 8. 配置文件格式

详见 `DATA_SCHEMA.md`

---

## 9. 注意事项

### 必须遵守的约束

1. **`hook_demo/backup_vN/` 只读** — 任何操作不得修改或删除备份文件夹中的内容
2. **C++ 编译目标** — 必须是 x86 (32-bit)，因为 dnplayer.exe 是 32 位进程
3. **LDPlayer 版本** — 当前仅支持海外版 (9 / 14)，国内版 Ctrl+F 机制不同，已决定不对国内版LDPlayer进行适配
4. **杀毒软件** — DLL 注入可能被 Defender 标记，打包时需加入说明
5. **CFW hook 非线程安全** — "恢复-调用-重装"模式，未来考虑 trampoline 改造

### 现有资产复用

| 资产 | 源位置 | 目标位置 | 说明 |
|---|---|---|---|
| C++ 源码 (3 文件) | `hook_demo/*.{cpp,asm}` | `src/core/` | 复制，原文件保留 |
| C++ 编译产物 | `hook_demo/{dll,exe}` | `dist/` | 复制预编译文件 |
| Toast 模块 | `backup_v10/.../toast_overlay.py` | `src/detector/overlay.py` | 复制，几乎不改 |
| GTASA 模板 | `backup_v10/.../{drive,walk}Sample.png` | `games/gtasa/templates/` | 复制 |
| GTASA .kmp | `backup_v10/.../*.kmp` (GTASA 相关) | `games/gtasa/keymaps/` | 复制并重命名 |
| requirements.txt | `backup_v10/.../requirements.txt` | 根目录 | 合并 + 补充 PySide6 |
| 逆向工程文档 | `DEVDOC.md`, `PROJECT_SUMMARY.md`, `REVERSE_ENGINEERING_REPORT.md` | `docs/` | 整合 |

---

## 10. 后续扩展方向

| 优先级 | 方向 | 状态 |
|---|---|---|
| **P0** | 多区域模板匹配 (schema v2) | **已规划** — schema 已定义，见 §5.7 + DATA_SCHEMA.md §1 |
| P1 | trampoline 改造 CFW hook（线程安全） | 待实施 |
| P2 | 社区游戏模板市场 / 在线下载 | 待评估 |
| P2 | 多实例支持（多开 LDPlayer） | 待评估 |
| P3 | 共享内存直连方案（消除 injector 进程调用延时） | 待评估 |
