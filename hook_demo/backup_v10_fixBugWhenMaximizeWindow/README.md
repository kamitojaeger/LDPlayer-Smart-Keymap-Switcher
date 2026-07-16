# LDPlayer 按键切换工具 v10（修复最大化窗口退出 Bug）

## 相比 v9 的增量

| 维度 | v9 (backup_v9_captureAndroidOnly) | v10 (当前版本) |
|---|---|---|
| **按键注入** | keymap_injector init + 切换 | 🔧 **修复 ShowWindow(SW_RESTORE) Bug** |
| **状态检测** | OpenCV 模板匹配 + RenderWindow | 不变 |
| **射击视角** | keybd_event 自动恢复 | 不变 |
| **切换速度** | ~650ms（-58%） | 不变 |
| **Toast 提示** | 自定义覆盖层 | 不变 |
| **截图精度** | RenderWindow 纯安卓画面 | 不变 |

## v10 核心修复：最大化窗口退出问题

### 问题描述

LDPlayer 窗口处于**最大化状态**时，自动切换按键会**导致窗口退出最大化**，恢复为正常窗口尺寸。全屏状态不受影响。

### 根因

`keymap_injector.cpp` 的 `SendCtrlF()` 函数中自 v2 起无条件调用：

```cpp
ShowWindow(hwnd, SW_RESTORE);  // 无条件恢复 — 最大化窗口被还原
```

`SW_RESTORE` 的语义是"激活并显示窗口，如果窗口是最小化或最大化，恢复到原始尺寸"。当 LDPlayer 最大化时，此调用会将窗口还原。

### 修复

```cpp
// v10 修复：仅在窗口最小化时恢复，最大化/正常状态保持不变
if (IsIconic(hwnd)) {
    ShowWindow(hwnd, SW_RESTORE);  // 仅从最小化恢复
}
```

`IsIconic()` 判断窗口是否处于最小化状态。修复后：
- **最小化** → 恢复（正常行为）
- **最大化** → 保持最大化 ✓
- **全屏** → 保持全屏 ✓
- **正常** → 保持正常 ✓

## v9 功能保留：RenderWindow 纯安卓画面截图

dnplayer 主窗口内含 `RenderWindow` 子窗口，仅包含安卓渲染画面。v9 优先捕获该子窗口，自动适配窗口缩放/全屏，无需手动调整偏移量。详见 v9 README。

## 支持的模拟器版本

| 版本 | 安装路径示例 | 进程名 | dnplycore.dll 偏移 |
|---|---|---|---|
| LDPlayer9 海外版 | `F:\LDPlayer\LDPlayer9` | dnplayer.exe | HOOK=0x2019C, FUNC=0x9CA10, RTRN=0x201A1 |
| LDPlayer14 海外版 | `F:\LDPlayer\LDPlayer14` | dnplayer.exe | HOOK=0x1DD33, FUNC=0x959F0, RTRN=0x1DD38 |

## 文件清单

| 文件 | 说明 | v10 状态 |
|---|---|---|
| **keymap_hook.dll** | Hook DLL（注入到 dnplayer.exe） | 不变 |
| **keymap_injector.exe** | 🔧 注入器（修复最大化 Bug） | 🔧 v10 |
| keymap_hook.cpp | Hook DLL 源码 | 不变 |
| keymap_injector.cpp | 🔧 注入器源码（Sleep 100ms + IsIconic 修复） | 🔧 v10 |
| hook_stub.asm | CALL hook 汇编跳板 | 不变 |
| build.ps1 / build.bat | 编译脚本 | 不变 |
| version.rc | 版本资源 | 不变 |
| **screenshot_ldplayer.py** | Python 截图 + 模板匹配 + 自动切换 + 射击视角 + Toast + RenderWindow | v9 |
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
pip install -r requirements.txt
python screenshot_ldplayer.py
# 或
run_python.bat screenshot_ldplayer.py
```

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

1. **提示不一致**：✅ 已通过 Toast 覆盖层解决（v8）
2. **最大化退出**：✅ 已修复 ShowWindow(SW_RESTORE) Bug（v10）
3. **杀毒软件报毒**：DLL 注入可能被 Defender 标记
4. **CFW hook 非线程安全**：恢复-调用-重装模式
5. **国内版不兼容**
6. **射击视角为无条件恢复**：每次切换后均发送 ClassMouseDrag key
7. **RenderWindow 依赖**：若 LDPlayer 版本无 RenderWindow 子窗口，自动回退到 ClientRect 模式

## 版本历史

- v1-v5: 基础注入 + OpenCV 检测
- v6: 自动射击视角恢复（keybd_event API）
- v7: injector 延时优化（1550ms → 650ms）
- v8: Toast 覆盖层，解决安卓提示不一致
- v9: RenderWindow 纯安卓画面截图，自适应窗口缩放/全屏
- **v10**: 🔧 修复 LDPlayer 最大化窗口时切换按键退出最大化的问题（keymap_injector.cpp ShowWindow SW_RESTORE → IsIconic 条件恢复）
