# LDPlayer Auto Input Switcher — 项目总结

> 最后更新: 2026-07-14

## 快速定位

| 你想了解 | 去看 |
|---|---|
| 项目是什么、怎么用 | `README.md` |
| 代码在哪、架构怎样 | `HANDOVER.md` 或 `Project_Overhaul/OVERHAUL_PLAN.md` |
| 怎么加新游戏、配置格式 | `Project_Overhaul/DATA_SCHEMA.md` |
| 逆向工程细节（hook/偏移/Ctrl+F 机制） | 本文 §4 往下 |

---

## 当前状态总览

项目已从早期的 C++ 原型迭代为一个完整的 **Python 桌面应用**，经历了 5 个 Phase 的重构：

```
老旧结构 (hook_demo/ 一团):
  C++ DLL + Python 800行脚本 + TKinter Toast + 硬编码路径

当前结构:
  PySide6 GUI + modular Python (detector/shared/gui) + C++ core (dist/)
  + JSON 配置驱动 + 多语言 + PyInstaller 打包
```

| 模块 | 核心文件 | 状态 |
|---|---|---|
| **GUI** | `src/gui/main_window.py`, `system_tray.py`, `settings_dialog.py` | ✅ |
| **检测引擎** | `src/detector/matcher.py`, `state_machine.py`, `monitor.py` | ✅ |
| **配置系统** | `src/shared/config.py`, `games/gtasa/game.json` | ✅ |
| **LDPlayer 交互** | `src/shared/ldplayer.py`, `injector.py` | ✅ |
| **多语言** | `src/shared/i18n.py`, `locales/{zh_CN,en_US}.json` | ✅ |
| **注入核心(C++)** | `src/core/keymap_hook.cpp`, `hook_stub.asm`, `keymap_injector.cpp` | ✅ 稳定 |
| **打包** | `scripts/package.py` → `dist_package/` | ✅ |
| **开发辅助** | `scripts/scan_regions.py` (模板扫描 + regions 推算) | ✅ |

### 当前支持的游戏

| 游戏 | 识别状态 |
|---|---|
| GTA: San Andreas | 行走 / 驾驶 |
| Black Russia | 🔧 配置中 |
| CODM | 🔧 配置中 |

---

## 1. 项目目标

为 LDPlayer 雷电模拟器（海外版 9 / 14）开发辅助工具，实现游戏内**自动切换按键方案**。

### 完整流程

```
OpenCV 模板匹配识别游戏画面状态
  → 状态机去抖确认状态变化
  → 调用 keymap_injector.exe（DLL 注入 + CFW 重定向）
  → 实际键位切换到目标 .kmp 方案（无弹窗、无用户交互）
  → Toast 覆盖层提示切换结果
```

---

## 2. 环境信息

| 项目 | 值 |
|---|---|
| 工作目录 | `D:\LD_DEV\LDPlayer_Auto_Input_Switcher\` |
| C++ 注入代码 | `src/core/keymap_hook.cpp` + `hook_stub.asm` |
| 注入器 | `src/core/keymap_injector.cpp` |
| 编译目标 | x86 (32-bit) — dnplayer.exe 是 32 位 |
| 调试器 | `x64-x32dbg\release\x32\x32dbg.exe` |
| 编译工具 | VS 2022 Community, MSVC 14.51.36231, MASM |
| 支持版本 | LDPlayer 9 / 14 海外版（国内版已放弃） |

---

## 3. 按键映射文件体系

```
<LDPlayer安装路径>/vms/
├── customizeConfigs/     # 用户自定义按键配置
│   ├── <packagename>.smp   # per-app 按键方案配置 (JSON)
│   └── <packagename>.kmp   # 键盘映射文件
├── recommendConfigs/     # 系统推荐配置
└── config/
    └── leidian0.config     # hotkeySettings Ctrl+F 定义
```

### .smp 文件结构

```json
{
  "resolutionRelatives": {
    "1920x1080": {
      "keyboardId": "gamename_1920x1080(default).kmp",
      "joystickId": ""
    }
  }
}
```

---

## 4. 逆向工程成果

### 4.1 关键函数

通过 x32dbg 附加到 dnplayer.exe，在 CreateFileW 下断点捕获 .kmp 文件读取，回溯调用栈：

| 函数 | 地址 (海外版 RVA) | 说明 |
|---|---|---|
| `vbox::CInputMgr::setKeyboardConfig` | `dnplycore.dll + 0x9CA10` | 应用按键配置的核心函数 |
| 调用点 (CALL 指令) | `dnplycore.dll + 0x2019C` | `call setKeyboardConfig` |
| getter (vtable 0xD8) | `dnplycore.dll + 0x2018` | `lea eax, [ecx+0x34]; ret` |

### 4.2 setKeyboardConfig 函数

```asm
77ACCA10 | 55                   push ebp
77ACCA11 | 8BEC                 mov ebp, esp
77ACCA13 | 83E4 F8              and esp, FFFFFFF8
77ACCA16 | 81EC 14010000        sub esp, 114
...
77ACCA2A | 8B45 08              mov eax, [ebp+8]    ; 取第一个参数
; arg = 0 → "切换到下一个"; arg = char* → "加载指定方案"
```

调用约定: `__thiscall` (ecx = this, 栈传参数)

### 4.3 Ctrl+F 调用链

```
Windows 消息循环 → dnplayer.exe 消息分发
  → mov eax, [edi+10AC]
  → mov ecx, [eax+20]
  → push 0              ; arg = 0 (循环下一个)
  → call [ecx+D8]       ; vtable getter → 返回 this
  → mov ecx, eax
  → CALL setKeyboardConfig(this, 0)
```

### 4.4 类和 IPC 架构

```
dnplayer.exe (32-bit, Qt/C++)
  ├── dnplycore.dll (vbox::CInputMgr, CInputKeyboard, VBoxClientImpl)
  ├── Ld9BoxHeadless.exe (引擎)
  └── IPC: 命名管道 + 共享内存 + FastPipe
```

---

## 5. Hook 策略详解

### 5.1 共享内存

结构体 `SharedData` 位于 `LDKeymapSwitch_Mem`，injector ↔ DLL 通信。

### 5.2 两个钩子

#### Hook A: CreateFileW (CFW) — 已验证工作

- hook kernelbase.CreateFileW，拦截 .kmp 读取，重定向到目标方案
- "恢复-调用-重装" 模式（非线程安全）

#### Hook B: CALL Hook (setKeyboardConfig) — 已验证工作

- `hook_stub.asm`: CALL→JMP 转换，push 返回地址后 jmp setKeyboardConfig
- **2026-07-07 已修复栈布局 Bug**（见 §6）

---

## 6. 已解决的历史问题

### HookStub 栈布局 Bug (2026-07-07)

**根因**: JMP 不压返回地址 → setKeyboardConfig 的 [ebp+8] 读到垃圾值 → 参数替换无效

**修复**: hook_stub.asm 中 `jmp [g_f]` 前添加 `push [g_ret]`

### 命令语义重构 (2026-07-07)

| 命令 | modeFlags | 行为 |
|---|---|---|
| `keymap_injector.exe <target.kmp>` | 3 | CALL hook + CFW redirect + 一次 Ctrl+F |
| `keymap_injector.exe init` | - | 预注入 DLL |
| `keymap_injector.exe --status` | - | 打印诊断信息 |

---

## 7. 备份版本

`hook_demo/backup_vN/` 是**只读**历史快照，不可修改或删除：

| 版本 | 路径 | 说明 |
|---|---|---|
| v2 | `backup_v2_working/` | CFW redirect, LDPlayer9 海外版 |
| v3 | `backup_v3_multi/` | 多版本兼容 + kernelbase hook |
| v4-v10 | `backup_v4_preInit/` ~ `backup_v10_fixBugWhenMaximizeWindow/` | 迭代改进 |

---

## 8. 相关文件清单

| 文件 | 说明 |
|---|---|
| `README.md` | 用户文档 |
| `HANDOVER.md` | 技术交接文档 |
| `Project_Overhaul/OVERHAUL_PLAN.md` | 5 阶段重构规划 |
| `Project_Overhaul/DATA_SCHEMA.md` | JSON 配置规范 |
| `src/core/keymap_hook.cpp` | Hook DLL 主代码 |
| `src/core/hook_stub.asm` | CALL 钩子汇编 |
| `src/core/keymap_injector.cpp` | 注入器 |
| `src/detector/matcher.py` | 模板匹配核心 |
| `src/detector/monitor.py` | 监控主循环 |
| `scripts/scan_regions.py` | 模板扫描 + regions 推算工具 |
| `x64-x32dbg/release/x32/x32dbg.exe` | x32dbg 调试器 |
