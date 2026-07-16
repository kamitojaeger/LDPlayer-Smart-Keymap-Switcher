# LDPlayer 按键切换工具 v7（加速切换 + 自动射击视角）

## 相比 v6 的增量

| 维度 | v6 (backup_v6_autoSwitchMouse) | v7 (当前版本) |
|---|---|---|
| **按键注入** | keymap_injector init + 切换 | 不变 |
| **状态检测** | OpenCV 模板匹配 walk/drive | 不变 |
| **射击视角** | keybd_event 自动恢复 | 不变 |
| **切换速度** | ~1550ms | 🔧 **~650ms（-58%）** |

## v7 核心优化：injector 延时微调

对 `keymap_injector.cpp` 中 `TriggerOnceAndVerify()` 函数的验证等待 `Sleep(1000)` 进行逐级下调测试：

| ⑤ 验证等待 | 总延时 | 测试结果 |
|---|---|---|
| 1000ms (原始) | 1550ms | — |
| 750ms | 1300ms | ✓ |
| 500ms | 1050ms | ✓ |
| 250ms | 800ms | ✓ |
| **100ms** | **650ms** | ✓ |

仅优化一个 `Sleep` 点，总延时从 1550ms 降到 650ms（-58%），且按键切换 + 射击视角恢复均正常。

## 支持的模拟器版本

| 版本 | 安装路径示例 | 进程名 | dnplycore.dll 偏移 |
|---|---|---|---|
| LDPlayer9 海外版 | `F:\LDPlayer\LDPlayer9` | dnplayer.exe | HOOK=0x2019C, FUNC=0x9CA10, RTRN=0x201A1 |
| LDPlayer14 海外版 | `F:\LDPlayer\LDPlayer14` | dnplayer.exe | HOOK=0x1DD33, FUNC=0x959F0, RTRN=0x1DD38 |

## 文件清单

| 文件 | 说明 |
|---|---|
| **keymap_hook.dll** | Hook DLL（注入到 dnplayer.exe） |
| **keymap_injector.exe** | 🔧 注入器（优化版，切换延时 650ms） |
| keymap_hook.cpp | Hook DLL 源码 |
| keymap_injector.cpp | 🔧 注入器源码（TriggerOnceAndVerify Sleep 100ms） |
| hook_stub.asm | CALL hook 汇编跳板 |
| build.ps1 / build.bat | 编译脚本 |
| version.rc | 版本资源 |
| **screenshot_ldplayer.py** | Python 截图 + OpenCV 状态检测 + 自动切换 + 射击视角恢复 |
| requirements.txt | Python 依赖 |
| test_mouse_drag_key.py | 第一轮按键测试脚本 |
| test_mouse_drag_key2.py | 第二轮按键测试脚本（keybd_event 有效） |
| com.android.settings_1920x1080(AAA~DDD).kmp | 测试用 .kmp 文件 |

## 调用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 一键启动：init → 循环监控 → 自动切换 + 射击视角恢复
python screenshot_ldplayer.py
```

运行时流程：
1. 实例守卫 — 确认只有一个 dnplayer.exe
2. `keymap_injector.exe init` — 预注入 DLL
3. 进入循环（每 0.5 秒）：
   - dxcam 截图 → OpenCV 模板匹配 → 检测 walk ↔ drive 状态变化
   - 变化时调用 `keymap_injector.exe "<对应.kmp>"`
   - 若新 .kmp 含 ClassMouseDrag → `keybd_event` 发送对应 key

## 射击视角自动恢复

- `parse_kmp_mouse_drag_key()` 解析 .kmp JSON 查找 ClassMouseDrag key
- `send_key_vk()` 通过 `keybd_event` API 发送（绕过 LLKHF_INJECTED 过滤）

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

1. **提示不一致**：安卓系统弹出切换提示与实际键位不符
2. **杀毒软件报毒**：DLL 注入可能被 Defender 标记
3. **CFW hook 非线程安全**：恢复-调用-重装模式
4. **国内版不兼容**
5. **射击视角为无条件恢复**：每次切换后均发送 ClassMouseDrag key，不判断切换前状态
6. **共享内存直连方案未成功**：Python 直接写共享内存 + Post Ctrl+F 的快速方案未能正确触发切换，回退到 injector 方案

## 版本历史

- v1-v5: 基础注入 + OpenCV 检测
- v6: 自动射击视角恢复（keybd_event API）
- **v7**: 🔧 injector 延时优化，切换从 1550ms → 650ms
