# LDPlayer 按键自动切换 - 开发文档

## 逆向成果

### 核心函数

| 项目 | 值 |
|---|---|
| **函数地址** | `dnplycore.dll` + 0x9CA10（运行时 = base + 0x9CA10） |
| **函数签名** | `void setKeyboardConfig(void* this_obj, uintptr_t arg)` |
| **调用约定** | `__thiscall`（ecx = this, 栈传 arg） |
| **this 来源** | vtable 偏移 0xD8 的 getter 返回值 |
| **getter 逻辑** | `lea eax, [ecx+0x34]; ret` |
| **arg=0** | 循环到下一个按键方案 |
| **arg≠0** | 当作 `.kmp` 文件路径字符串指针 |

### 调用链（从接收消息到切换）

```
Windows Message Loop
  → dnplayer.exe 消息分发 (00AE81F8)
    → CInputMgr::OnMsg (77A50161 附近)
      → 日志: push "vbox::CInputMgr::setKeyboardConfig" (77A5017A)
      → mov eax, [edi+10AC]         (77A50184)
      → mov ecx, [eax+20]           (77A5018D)   ← 子对象指针
      → push 0                      (77A50190)   ← 参数
      → mov eax, [ecx]              (77A50192)   ← vtable
      → call [eax+0xD8]             (77A50194)   ← getter
      → mov ecx, eax                (77A5019A)   ← this = getter结果
      → call setKeyboardConfig      (77A5019C)   ← 实际切换
```

## Demo 实现方案

### 方案 A1：CreateFile Hook（推荐用于快速验证）

**原理：** LDPlayer 按 Ctrl+F 时读取 `.kmp` 文件。钩住 `CreateFileW`，当 LDPlayer 打开某个 `.kmp` 文件时，将路径替换为我们指定的键位文件。

**优点：** 不需要知道 CInputMgr 实例地址，实现最简单

**缺点：** 只拦截读取文件这一刻，不是直接调用函数

### 方案 A2：Inline Hook（最终方案）

**原理：** 在 77A5019C（`call setKeyboardConfig`）处将 `CALL rel32` 替换为 `JMP HookStub`，HookStub 将参数 `0` 替换为目标 `.kmp` 文件路径指针后跳转回原函数。

**优点：** 直接调用 setKeyboardConfig，稳定可靠

**关键实现细节（2026-07-07 修复）：**

`CALL` 指令会自动压入返回地址，而 `JMP` 不会。因此 HookStub **必须在 `jmp [g_f]` 之前 `push [g_ret]`** 压入返回地址（0x201A1，即 CALL 后的下一条指令地址），使 setKeyboardConfig 看到正确的栈布局：

```
进入 setKeyboardConfig 时栈必须为:
  [ESP+0] = return_addr (0x201A1)   ← 由 push [g_ret] 提供
  [ESP+4] = arg                      ← 由 CALL 之前的 push 0 / HookStub 替换提供

函数 prologue: push ebp; mov ebp,esp 后
  [ebp+8] = arg  ✓ 正确读取参数
函数返回: ret 4 → 弹返回地址 + 清参数 → 正确返回 0x201A1
```

若缺少 `push [g_ret]`，`[ESP+0]` 是 arg（被当成返回地址），`[ebp+8]` 读到调用者栈垃圾值，参数替换完全无效。

### 方案 A3：CreateRemoteThread 直调（诊断用）

**原理：** 不 hook，直接通过 `CreateRemoteThread` 在目标进程中调用 `SwitchKeymap`（DLL 导出），由它调用 `setKeyboardConfig(savedInstance, targetPath)`。

**优点：** 零侵入，按需调用

**缺点：** 不在 GUI 线程上下文，不触发 `.kmp` 文件读取，目前无法实际切换按键。仅保留为诊断模式。

## 运行时地址计算

所有地址基于 dnplycore.dll 的加载基址（不同机器不同运行次不同）。

```c
HMODULE hDll = GetModuleHandleA("dnplycore.dll");
// 或加载:
// hDll = GetModuleHandle("F:\\leidian\\LDPlayer9\\dnplycore.dll");

// setKeyboardConfig 函数地址
void* setKeyboardConfig = (void*)((uintptr_t)hDll + 0x9CA10);

// vtable 地址 (用于扫描实例)
void* vtable = (void*)((uintptr_t)hDll + 0xD19C0);

// CreateFileW hook 地址
// 注意: kernel32.CreateFileW -> kernelbase.CreateFileW
void* createFileW = GetProcAddress(GetModuleHandleA("kernel32.dll"), "CreateFileW");
```

## 编译环境

### 需求

- Visual Studio 2022（已确认安装）
- MSVC v14.51.36231（已确认）
- Windows SDK（已确认）
- Python 3.11（已确认）

### 编译 DLL

```batch
:: 打开 VS 开发命令提示符
"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"

:: 编译 DLL (32-bit, 因为 dnplayer.exe 是 32 位)
cl /LD /O2 /MD keymap_hook.cpp /Fekeymap_hook.dll /link /DEF:keymap_hook.def
```

### 编译注入器

```batch
cl /O2 keymap_injector.cpp /Fekeymap_injector.exe
```

## 测试流程

1. 启动雷电模拟器（海外版），打开一个游戏
2. `keymap_injector.exe "<target.kmp>"` → 注入 DLL + 设置目标 + 触发一次 Ctrl+F
   - 默认模式启用 CALL hook 参数替换 + CreateFileW 重定向
   - 输出会显示 4 个勾选框验证 hook 链路是否完整
3. `keymap_injector.exe --status` → 查看诊断（不触发任何操作）
4. `keymap_injector.exe --loop "<target.kmp>"` → 备用：循环 Ctrl+F 靠原生切换
5. OK 后集成到 Python 工具中

## 编译方式

### PowerShell（推荐，无需 cmd）

```powershell
& "D:\LD_DEV\LDPlayer_Auto_Input_Switcher\hook_demo\build.ps1"
```

### cmd（传统）

```batch
cd /d D:\LD_DEV\LDPlayer_Auto_Input_Switcher\hook_demo
build.bat
```
