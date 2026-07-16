# LDPlayer 按键切换工具 v9（纯安卓画面截图）

## 相比 v8 的增量

| 维度 | v8 (backup_v8_toastOverwrite) | v9 (当前版本) |
|---|---|---|
| **按键注入** | keymap_injector init + 切换 | 不变 |
| **状态检测** | OpenCV 模板匹配 walk/drive | 不变 |
| **射击视角** | keybd_event 自动恢复 | 不变 |
| **切换速度** | ~650ms（-58%） | 不变 |
| **Toast 提示** | 自定义覆盖层 | 不变 |
| **截图精度** | 截图含上边栏+右侧工具栏 | 🔧 **仅截纯安卓画面 (RenderWindow)** |
| **窗口缩放适配** | 手动微调偏移量 | ✅ 自适应，窗口任意缩放/全屏均准确 |

## v9 核心改进：RenderWindow 纯安卓画面截图

### 问题

v5-v8 使用 `GetClientRect` 截取 dnplayer 客户端区域，包含上边栏和右侧工具栏（各约 60px）。不同 LDPlayer 版本、不同分辨率/DPI 下，标题栏和工具栏的实际像素宽度不同，导致基于固定像素偏移的模板匹配在窗口缩放时精度下降。

### 发现

dnplayer 主窗口 (`LDPlayerMainFrame`) 内含一个子窗口：类名 `RenderWindow`，标题 `TheRender`。该子窗口仅包含安卓渲染画面，不含任何 LDPlayer UI 元素。

### 解决方案

1. `get_dnplayer_render_rect()` — 枚举 dnplayer 子窗口查找 `RenderWindow` 并返回其屏幕坐标
2. `resolve_capture_target()` 优先级：
   - `RenderWindow` 子窗口（纯安卓画面）
   - → 回退 `GetClientRect`（含标题栏+工具栏，兼容旧版 LDPlayer）
3. `match_drive_walk()` 根据截图来源自动切换参考坐标系：

| 参数 | RenderWindow（纯游戏区） | ClientRect（含边框工具栏） |
|---|---|---|
| 参考尺寸 | 1920×1080 | 1980×1140 |
| Scale | `h / 1080` | `h / 1140` |
| 图标右边距 | 40px + slack | 100px + slack |
| 图标下边距 | 40px + slack | 40px + slack + extra |
| 右边缩进 | 0 | 60px |

缩放/全屏时 scale 自动适配，无需手动调整偏移量。

### 微调参数（同步调整）

新增 `SEARCH_EXPAND = 16`：搜索区域向左、向上各延长 16 参考像素，覆盖窗口缩放时的 UI 偏移。

## 支持的模拟器版本

| 版本 | 安装路径示例 | 进程名 | dnplycore.dll 偏移 |
|---|---|---|---|
| LDPlayer9 海外版 | `F:\LDPlayer\LDPlayer9` | dnplayer.exe | HOOK=0x2019C, FUNC=0x9CA10, RTRN=0x201A1 |
| LDPlayer14 海外版 | `F:\LDPlayer\LDPlayer14` | dnplayer.exe | HOOK=0x1DD33, FUNC=0x959F0, RTRN=0x1DD38 |

## 文件清单

| 文件 | 说明 | v9 状态 |
|---|---|---|
| **keymap_hook.dll** | Hook DLL（注入到 dnplayer.exe） | 不变 |
| **keymap_injector.exe** | 注入器（切换延时 650ms） | 不变 |
| keymap_hook.cpp | Hook DLL 源码 | 不变 |
| keymap_injector.cpp | 注入器源码（TriggerOnceAndVerify Sleep 100ms） | 不变 |
| hook_stub.asm | CALL hook 汇编跳板 | 不变 |
| build.ps1 / build.bat | 编译脚本 | 不变 |
| version.rc | 版本资源 | 不变 |
| **screenshot_ldplayer.py** | 🔧 Python 截图 + 模板匹配 + 自动切换 + 射击视角 + Toast | 🔧 v9 |
| **toast_overlay.py** | Toast 覆盖层模块 | 不变 |
| requirements.txt | Python 依赖 | 不变 |
| run_python.bat | venv Python 启动脚本 | 不变 |
| test_mouse_drag_key.py | 第一轮按键测试脚本 | 不变 |
| test_mouse_drag_key2.py | 第二轮按键测试脚本 | 不变 |
| driveSample.png | 驾驶模式样本（178×176） | 不变 |
| walkSample.png | 行走模式样本（180×178） | 不变 |
| com.android.settings_1920x1080(AAA~DDD).kmp | 测试用 .kmp 文件 | 不变 |

## 调用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 一键启动
python screenshot_ldplayer.py
# 或
run_python.bat screenshot_ldplayer.py

# 离线匹配测试
python screenshot_ldplayer.py --match testScreenShots/screenshot.png
```

运行时流程：
1. 实例守卫 — 确认只有一个 dnplayer.exe
2. 获取 dnplayer 主窗口 HWND（用于 Toast 定位）
3. `keymap_injector.exe init` — 预注入 DLL
4. 进入循环（每 0.5 秒）：
   - **RenderWindow 截图** → OpenCV 模板匹配 → 检测 walk ↔ drive 变化
   - 变化时：**先弹出 Toast** → `keymap_injector.exe "<对应.kmp>"`
   - 若新 .kmp 含 ClassMouseDrag → `keybd_event` 发送对应 key
   - 截图来源切换时自动打印通知

## screenshot_ldplayer.py 关键函数

| 函数 | 说明 | v9 状态 |
|---|---|---|
| `get_dnplayer_render_rect()` | 枚举 dnplayer 子窗口找 RenderWindow | 🆕 |
| `get_dnplayer_client_rect()` | 获取客户端区域（回退方案） | 不变 |
| `resolve_capture_target()` | 截图目标决策（优先 RenderWindow） | 🔧 |
| `match_sample_in_corner()` | 单样本模板匹配（接受动态参数） | 🔧 |
| `match_drive_walk()` | 双样本匹配+自动坐标系选择 | 🔧 |
| `parse_kmp_mouse_drag_key()` | 解析 .kmp ClassMouseDrag key | 不变 |
| `send_key_vk()` | keybd_event 发送虚拟键 | 不变 |
| `run_monitor_loop()` | 循环监控+状态机+Toast | 🔧 |

## 可调参数（截图+匹配）

| 参数 | 默认值 | 说明 |
|---|---|---|
| REF_GAME_W/H | 1920/1080 | 游戏区参考尺寸 |
| REF_CAPTURE_W/H | 1980/1140 | 含工具栏的参考尺寸 |
| REF_MARGIN_BOTTOM/RIGHT | 40 | 图标距游戏区边距 |
| SEARCH_SLACK | 20 | 搜索区域余量 |
| SEARCH_EXPAND | 16 | 🔧 向左+向上延长 |
| REF_BOTTOM_EXTRA | 13 | 搜索区域上移微调 |
| REF_RIGHT_TRIM | 60 | 搜索区域右侧缩进 |
| MATCH_THRESHOLD | 0.75 | 匹配成功阈值 |
| MASK_DARK/BRIGHT_PERCENTILE | 22/82 | mask 阈值 |

## 工作原理

### 策略 v2（CFW 重定向）

Ctrl+F 切换按键时，LDPlayer 读取 .kmp 文件：
1. 第 1 次读取：当前方案 — 不重定向
2. 第 2、3 次读取：下一个方案 — 重定向到目标方案

### RenderWindow 截图

通过 `EnumChildWindows` 查找父窗口（dnplayer）下类名为 `RenderWindow` 的子窗口，直接截取其屏幕坐标区域，获取纯安卓渲染画面。

## 编译方法

```powershell
cd hook_demo
.\build.ps1
```

依赖：Visual Studio 2022 + Windows SDK 10.x + x86 目标

## injector 延时结构

| 延时点 | 函数 | 值 | 说明 |
|---|---|---|---|
| focus settle | `SendCtrlF` | 200ms | SetForegroundWindow 等待 |
| key interval | `SendCtrlF` | 50ms | WM_KEYDOWN→KEYUP 间隔 |
| post-dispatch | `SendCtrlF` | 300ms | 发送 Ctrl+F 后等待 |
| 验证等待 | `TriggerOnceAndVerify` | 100ms | 切换生效确认 |
| **切换总计** | | **650ms** | |

## 已知限制

1. **提示不一致**：✅ 已通过 Toast 覆盖层解决
2. **杀毒软件报毒**：DLL 注入可能被 Defender 标记
3. **CFW hook 非线程安全**：恢复-调用-重装模式
4. **国内版不兼容**
5. **射击视角为无条件恢复**：每次切换后均发送 ClassMouseDrag key
6. **共享内存直连方案未成功**
7. **RenderWindow 依赖**：若 LDPlayer 版本无 RenderWindow 子窗口，自动回退到 ClientRect 模式

## 版本历史

- v1-v5: 基础注入 + OpenCV 检测
- v6: 自动射击视角恢复（keybd_event API）
- v7: injector 延时优化（1550ms → 650ms）
- v8: Toast 覆盖层，解决安卓提示不一致
- **v9**: 🔧 RenderWindow 纯安卓画面截图，自适应窗口缩放/全屏
  - 优先捕获 RenderWindow 子窗口（不含标题栏/工具栏）
  - 自动切换参考坐标系（RenderWindow vs ClientRect）
  - 新增 SEARCH_EXPAND 参数
  - `match_sample_in_corner` 接受动态参数
