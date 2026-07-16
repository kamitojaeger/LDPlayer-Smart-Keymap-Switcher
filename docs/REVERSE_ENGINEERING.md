# LDPlayer 逆向工程参考

> 整合自 `DEVDOC.md`、`HANDOVER.md`、`PROJECT_SUMMARY.md`、`REVERSE_ENGINEERING_REPORT.md`

## 1. 目标环境

| 项目 | 值 |
|---|---|
| 主程序 | `dnplayer.exe` (32-bit, Qt C++) |
| 核心 DLL | `dnplycore.dll` (32-bit) |
| 按键配置目录 | `vms/customizeConfigs/` (用户) / `vms/recommendConfigs/` (系统) |
| 支持版本 | LDPlayer 9 / 14 (海外版) |

## 2. 按键映射文件体系

- **`.kmp`** — 键盘映射 (JSON)，含 `keyboardMappings` 数组、`configInfo`
- **`.smp`** — Per-app 方案选择，`resolutionRelatives.{res}.keyboardId` 指向当前 .kmp
- **`.jmp`** — 摇杆映射

## 3. 核心发现：setKeyboardConfig

### 函数信息

| 项目 | LD9 值 | LD14 值 |
|---|---|---|
| **函数 RVA** | `0x9CA10` | `0x959F0` |
| **签名** | `void setKeyboardConfig(void* this, uintptr_t arg)` | 同 |
| **调用约定** | `__thiscall` (ecx=this) | 同 |
| **arg=0** | 循环到下一个按键方案 | 同 |
| **arg≠0** | 当作 .kmp 文件路径字符串 | 同 |
| **this 来源** | `[ecx+0x34]` → vtable `[eax+0xD8]` getter | 同 |

### CALL 指令 HOOK 点

| 项目 | LD9 RVA | LD14 RVA |
|---|---|---|
| HOOK 点 (CALL 指令) | `0x2019C` | `0x1DD33` |
| 返回地址 (CALL 后下一条) | `0x201A1` | `0x1DD38` |

## 4. 调用链

```
Windows Message Loop → dnplayer.exe 消息分发
  → CInputMgr::OnMsg
    → mov eax, [edi+0x10AC]
    → mov ecx, [eax+0x20]        ; 子对象
    → push 0                      ; arg (0=循环)
    → mov eax, [ecx]
    → call [eax+0xD8]             ; getter → ecx=this
    → call setKeyboardConfig      ; HOOK 点
```

## 5. 注入策略 (v2 CFW Redirect)

### 方案：CFW Hook + CALL Hook 双钩

1. **CFW Hook** (`kernelbase.CreateFileW`)：拦截 .kmp 文件读取 [1] 和 [2]（Ctrl+F 触发 3 次读取），重定向到目标内容
2. **CALL Hook** (hook_stub.asm trampoline)：将 `CALL setKeyboardConfig` 替换为 `JMP HookStub`，HookStub 压入返回地址后跳转到 setKeyboardConfig

### CALL Hook 关键实现

`CALL` 自动压返回地址，`JMP` 不会。HookStub 必须在 `jmp [g_f]` 之前 `push [g_ret]`：
```
进入 setKeyboardConfig 时栈:
  [ESP+0] = return_addr (push [g_ret])
  [ESP+4] = arg (由 HookStub 替换)
```

### Ctrl+F 触发流程

Ctrl+F → LDPlayer 3 次读取 .kmp：
- [0] = 当前方案名 (不拦截)
- [1] = 查找下一个方案 (CFW 重定向到目标)
- [2] = 读取下一个方案内容 (CFW 重定向到目标)

## 6. keymap_injector.exe 命令

| 命令 | 功能 |
|---|---|
| `init` | 预注入 keymap_hook.dll |
| `<target.kmp>` | 默认模式：CALL hook + one Ctrl+F |
| `--loop <target.kmp>` | 备用：循环 Ctrl+F 直到匹配 |
| `--direct <target.kmp>` | 诊断：CreateRemoteThread 直调 |
| `--status` | 打印共享内存诊断信息 |

## 7. 运行时地址计算

```c
HMODULE hDll = GetModuleHandle("dnplycore.dll");
void* fn = (void*)((uintptr_t)hDll + HOOK_RVA);
```

所有地址基于 dnplycore.dll 基址 + 固定 RVA。

## 8. 编译

```batch
:: VS 2022 32-bit 命令行
cl /O2 /MT keymap_injector.cpp /Fekeymap_injector.exe
cl /LD /O2 keymap_hook.cpp hook_stub.asm /Fekeymap_hook.dll
```

或运行 `src/core/build.bat`。

## 9. 已知限制

1. **CFW hook 非线程安全**："恢复-调用-重装"模式，多线程并发可能丢 hook
2. **仅支持海外版** (9 / 14)：国内版 Ctrl+F 机制不同
3. **keybd_event 代替 SendInput**：SendInput 设置 `LLKHF_INJECTED`，被 LDPlayer 低层键盘钩过滤

## 10. 版本演进历史

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

备份见 `hook_demo/backup_vN/`（只读）。
