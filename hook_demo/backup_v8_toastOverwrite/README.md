# LDPlayer 按键切换工具 v8（+ Toast 覆盖提示）

## 相比 v7 的增量

| 维度 | v7 (backup_v7_fasterAutoSwitchMouse) | v8 (当前版本) |
|---|---|---|
| **按键注入** | keymap_injector init + 切换 | 不变 |
| **状态检测** | OpenCV 模板匹配 walk/drive | 不变 |
| **射击视角** | keybd_event 自动恢复 | 不变 |
| **切换速度** | ~650ms（-58%） | 不变 |
| **切换提示** | 安卓系统弹出（提示不一致） | 🔧 **自定义 Toast 覆盖层** |

## v8 核心新增：Toast 覆盖层

解决 v7 已知限制第 1 条"**提示不一致**"——安卓系统弹出的切换提示与实际键位不符。

新增 `toast_overlay.py` 模块，在 keymap 切换时：
- **提前弹出**：在调用 keymap_injector.exe 切换之前就显示 Toast
- **文案**："Switch to <按键名称>"（名称从 .kmp 文件名括号中提取）
- **位置**：LDPlayer 窗口中上（距顶部 80px），水平居中
- **样式**：半透明黑底白字（α=0.92），微软雅黑 24pt 加粗
- **尺寸**：原始 175%，宽度自适应文案，最长不超过 LDPlayer 窗口宽度（溢出加"..."），单行不换行
- **时长**：显示 3 秒后自动消失
- **行为**：不抢焦点（WS_EX_NOACTIVATE）、鼠标穿透（WS_EX_TRANSPARENT）、不显示在任务栏（WS_EX_TOOLWINDOW）
- **置顶保障**：每次事件循环 `update()` 调用 `SetWindowPos(HWND_TOPMOST)`，防止 LDPlayer DirectX 渲染面抢占 z-order

### 文件名解析示例

```
com.rockstargames.gtasa_1920x1080(Drive mode).kmp  →  "Switch to Drive mode"
com.rockstargames.gtasa_1920x1080(walk mode).kmp   →  "Switch to walk mode"
com.android.settings_1920x1080(AAA).kmp             →  "Switch to AAA"
```

## 文件清单

| 文件 | 说明 | v8 状态 |
|---|---|---|
| **keymap_hook.dll** | Hook DLL（注入到 dnplayer.exe） | v7 不变 |
| **keymap_injector.exe** | 注入器（切换延时 650ms） | v7 不变 |
| keymap_hook.cpp | Hook DLL 源码 | v7 不变 |
| keymap_injector.cpp | 注入器源码（TriggerOnceAndVerify Sleep 100ms） | v7 不变 |
| hook_stub.asm | CALL hook 汇编跳板 | v7 不变 |
| build.ps1 / build.bat | 编译脚本 | v7 不变 |
| version.rc | 版本资源 | v7 不变 |
| **screenshot_ldplayer.py** | Python 截图 + OpenCV 状态检测 + 自动切换 + 射击视角恢复 + 🔧 Toast 集成 | 🔧 v8 |
| **toast_overlay.py** | 🆕 Toast 覆盖层模块 | 🆕 v8 |
| requirements.txt | Python 依赖 | 不变 |
| run_python.bat | venv Python 启动脚本 | 🆕 v8 |
| test_mouse_drag_key.py | 第一轮按键测试脚本 | v7 不变 |
| test_mouse_drag_key2.py | 第二轮按键测试脚本 | v7 不变 |
| com.android.settings_1920x1080(AAA~DDD).kmp | 测试用 .kmp 文件 | v7 不变 |

## 调用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 一键启动
python screenshot_ldplayer.py
# 或
run_python.bat screenshot_ldplayer.py
```

运行时流程：
1. 实例守卫 — 确认只有一个 dnplayer.exe
2. `keymap_injector.exe init` — 预注入 DLL
3. 获取 dnplayer 主窗口 HWND（用于 Toast 定位）
4. 进入循环（每 0.5 秒）：
   - dxcam 截图 → OpenCV 模板匹配 → 检测 walk ↔ drive 状态变化
   - 变化时：**先弹出 Toast** → 调用 `keymap_injector.exe "<对应.kmp>"`
   - 若新 .kmp 含 ClassMouseDrag → `keybd_event` 发送对应 key
   - 分片 sleep（`_sleep_with_toast`）：每 50ms 处理 tkinter 事件循环

## 支持的模拟器版本

| 版本 | 安装路径示例 | 进程名 | dnplycore.dll 偏移 |
|---|---|---|---|
| LDPlayer9 海外版 | `F:\LDPlayer\LDPlayer9` | dnplayer.exe | HOOK=0x2019C, FUNC=0x9CA10, RTRN=0x201A1 |
| LDPlayer14 海外版 | `F:\LDPlayer\LDPlayer14` | dnplayer.exe | HOOK=0x1DD33, FUNC=0x959F0, RTRN=0x1DD38 |

## injector 延时结构

| 延时点 | 函数 | 值 | 说明 |
|---|---|---|---|
| focus settle | `SendCtrlF` | 200ms | SetForegroundWindow 等待 |
| key interval | `SendCtrlF` | 50ms | WM_KEYDOWN→KEYUP 间隔 |
| post-dispatch | `SendCtrlF` | 300ms | 发送 Ctrl+F 后等待 |
| 验证等待 | `TriggerOnceAndVerify` | **100ms** (原 1000ms) | 🔧 |
| **切换总计** | | **650ms** (原 1550ms) | **-58%** |

## 编译方法

```powershell
cd hook_demo
.\build.ps1
```

依赖：Visual Studio 2022 + Windows SDK 10.x + x86 目标

## 已知限制

1. **提示不一致**：✅ 已通过 Toast 覆盖层解决
2. **杀毒软件报毒**：DLL 注入可能被 Defender 标记
3. **CFW hook 非线程安全**：恢复-调用-重装模式
4. **国内版不兼容**
5. **射击视角为无条件恢复**：每次切换后均发送 ClassMouseDrag key，不判断切换前状态
6. **共享内存直连方案未成功**：Python 直接写共享内存 + Post Ctrl+F 的快速方案未能正确触发切换，回退到 injector 方案

## 版本历史

- v1-v5: 基础注入 + OpenCV 检测
- v6: 自动射击视角恢复（keybd_event API）
- v7: 🔧 injector 延时优化，切换从 1550ms → 650ms
- **v8**: 🆕 Toast 覆盖层，解决安卓提示不一致问题
