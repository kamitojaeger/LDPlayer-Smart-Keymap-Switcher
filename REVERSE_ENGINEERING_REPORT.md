# LDPlayer 雷电模拟器 逆向工程报告

## 1. 环境发现

| 项目 | 值 |
|---|---|
| LDPlayer 9 路径 | `F:\leidian\LDPlayer9\` |
| 主程序 | `dnplayer.exe` (6.4MB, 32-bit, Qt C++) |
| 核心 DLL | `dnplycore.dll` (1MB, 32-bit) |
| 控制台工具 | `ldconsole.exe` |
| 虚拟机引擎 | `Ld9BoxHeadless.exe` / `Ld9VirtualBox.exe` |
| 数据目录 | `vms/leidian0` (VM 数据) |
| 按键配置文件目录 | `vms/customizeConfigs/` (用户) / `vms/recommendConfigs/` (系统推荐) |
| x32dbg | `D:\LD_DEV\LDPlayer_Auto_Input_Switcher\x64-x32dbg\release\x32\x32dbg.exe` |

## 2. 按键映射文件体系

### 文件类型

- **`.smp`** — Per-app 按键方案配置，核心字段 `resolutionRelatives.{res}.keyboardId` 指向当前选中的 `.kmp`
- **`.kmp`** — 键盘映射配置 (JSON)，包含 `keyboardMappings` 数组、`configInfo`（包名匹配规则）、`keyboardConfig`
- **`.jmp`** — 摇杆映射配置
- **`.dir`** — 目录索引（`dir_kmps.dir`, `dir_jmps.dir`, `dir_noices.dir`, `dir_commons.dir`）

### `.smp` 文件结构

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

## 3. 进程架构与 IPC

### 运行的进程

```
dnplayer.exe (PID 33724)  ← GUI主程序 (32-bit)
  └── 加载 dnplycore.dll  ← 全部逻辑在此
      ├── CInputMgr          ← 输入管理器
      ├── CInputKeyboard     ← 键盘输入处理
      ├── VBoxClientImpl     ← 与虚拟机通信的客户端
      └── CWinPipe           ← 命名管道通信

Ld9BoxHeadless.exe (PID 36528)  ← VirtualBox 引擎
  ├── 监听 TCP 2222
  └── 通过命名管道与 dnplayer 通信

Ld9BoxSVC.exe (PID 11936)  ← 后台服务
```

### IPC 机制（从 dnplycore.dll 逆向得出）

**命名管道 (Named Pipes)** — 主要通信方式：

```
\\.\pipe\ld-winpipe-read-33724    ← dnplayer 读取管道 (PID 后缀)
\\.\pipe\ld-winpipe-write-33724   ← dnplayer 写入管道
\\.\pipe\ld-winpipe-read-CapturePipe  ← 截屏管道
```

使用 `CWinPipe::SendRaw` / `CWinPipe::RecvRaw` 发送/接收二进制消息。

**共享内存 (FileMapping)** — 大量数据通信：

- `CreateFileMappingW/A`
- `OpenFileMappingW`
- `MapViewOfFile`
- `CreateSemaphoreW` / `ReleaseSemaphore` 用于同步

**FastPipe (VirtualBox 自定义 PCI 设备)**：

- VirtualBox XML 配置中注册了 `fastpipe` PCI 设备
- `fastpipe2.dll` 是 Windows 侧驱动
- 用于宿主机 ↔ 客户机 Android 系统高速通信

## 4. 关键类与函数（从 dnplycore.dll 字符串中提取）

### 输入管理器

| 类/函数 | 说明 |
|---|---|
| `vbox::CInputMgr` | 输入管理器主类 |
| `CInputMgr::OnMsg` | 处理 Windows 消息 |
| **`CInputMgr::setKeyboardConfig`** | ⭐ **应用新按键配置的核心函数** |
| `CInputMgr::EnableShowKeyboard` | 显示/隐藏按键叠加层 |
| `vbox::CInputKeyboard` | 键盘输入处理 |

### 按键显示

| 类/函数 | 说明 |
|---|---|
| `vbox::CKeyboardShow` | 按键叠加层显示 |
| `CKeyboardShow::SetShow` | 设置显示状态 |
| `CKeyboardShow::ClearAllKeys` | 清除所有按键显示 |
| `CKeyboardShow::CheckInvalidate` | 检查是否需要重绘 |

### 虚拟化通信

| 类/函数 | 说明 |
|---|---|
| `vbox::VBoxClientImpl` | VirtualBox 客户端实现 |
| `VBoxClientImpl::_putRawKeyEventSync` | 同步发送原始按键事件（→ 客户机） |
| `VBoxClientImpl::_putMultiTouchSync` | 多点触控事件 |
| `VBoxClientImpl::_putSingleTouchSync` | 单点触控事件 |
| `VBoxClientImpl::_putScancodeSync` | 发送扫描码 |
| `VBoxClientImpl::_putWheelSync` | 鼠标滚轮事件 |
| `VBoxClientImpl::initADB` | 初始化 ADB 连接 |
| `VBoxClientImpl::autoAdbReconnect` | 自动重连 ADB |

### 窗口管理

```
Main:   HWND=591670  Class='L' Text='LDPlayer'
Child:  HWND=2621644 Class='R' Text='TheRender'  ← 游戏渲染窗口
```

### 热键配置 (从 leidian0.config 中提取)

```json
"hotkeySettings.keyboardModelKey": {"modifiers": 2, "key": 70}
```

- `modifiers=2` = MOD_CONTROL
- `key=70` = VK_F (即 Ctrl+F)

## 5. F12 / Ctrl+F 按键切换流程（推测）

```
用户按 Ctrl+F
  → dnplycore.dll 接收按键事件
    → CInputMgr::OnMsg 或键盘钩子检测热键
      → dir_kmps.dir 中查找匹配包名的所有 .kmp
        → 按文件名排序，获取当前索引
          → 切换到下一个 .kmp
            → CInputMgr::setKeyboardConfig 应用新配置
              → 更新 .smp 中的 keyboardId
```

## 6. 可行的按键切换方案

### 方案 A：SendInput 模拟 Ctrl+F ✅ 最简

**优点**：无需逆向，只需要知道 LDPlayer 窗口句柄，用 `SendInput` 模拟 Ctrl+F

**缺点**：Ctrl+F 按照启动时文件名顺序循环，不能直接跳到指定按键方案

**实现**：已在 `keymap_switcher.py` 中实现 Strategy 1

### 方案 B：修改 .smp + 重启游戏应用 ✅ 可靠

**优点**：可靠，.smp keyboardId 修改后重启游戏即可生效

**缺点**：需要重启游戏，有短暂黑屏

**命令**：
```
ldconsole killapp --index 0 --packagename com.example.game
ldconsole runapp --index 0 --packagename com.example.game
```

**实现**：已在 `keymap_switcher.py` 中实现 Strategy 2

### 方案 C：[WIP] 通过命名管道 IPC 直接发送切换命令

需要：逆向 `CWinPipe::SendRaw` 的协议格式（4字节长度 + 4字节类型 + payload）

**价值**：实时切换，无需重启

### 方案 D：[WIP] 调用 CInputMgr::setKeyboardConfig

需要：
1. 用 x32dbg 调试 dnplayer.exe，找到 `setKeyboardConfig` 在内存中的地址
2. 注入 DLL 直接调用该函数

### 方案 E：[备选] 整理文件名控制循环顺序

利用 Ctrl+F 按文件名排序的特性，预先将 .kmp 文件名按字母序排列好。
用 `SetKeyboardId` + `SendInput` 模拟 Ctrl+F 精确跳转（需要知道当前处于哪个位置）。

## 7. 下一步建议

### 短期（最实用）
1. 启动 LDPlayer 后，枚举所有 .kmp 文件名并排序
2. 制作一个索引表（文件名 → 循环序号）
3. 工具箱：修改 .smp + 用 SendInput 发对应次数的 Ctrl+F
4. 或者直接走 "修改 .smp + 重启游戏" 路线

### 中期（RE 完成后）
1. 用 x32dbg 调试 dnplayer.exe，在 `ReadFile` 下条件断点（路径包含 `.smp`）
2. 按 Ctrl+F，观察调用栈，定位 `setKeyboardConfig` 的实际地址
3. 分析该函数的参数和调用方式
4. 编写 IPC 消息或 DLL 注入实现直接调用

### 长期
1. 完全理解命名管道的协议格式
2. 编写独立工具直接通过命名管道与 Ld9BoxHeadless 通信
3. 绕过 dnplayer.exe，直接控制按键映射
