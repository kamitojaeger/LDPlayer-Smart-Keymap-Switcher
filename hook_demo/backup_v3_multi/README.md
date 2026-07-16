# LDPlayer 按键切换工具 v3（多版本兼容）

## 支持的模拟器版本

| 版本 | 安装路径示例 | 进程名 | dnplycore.dll 偏移 |
|---|---|---|---|
| LDPlayer9 海外版 | `F:\LDPlayer\LDPlayer9` | dnplayer.exe | HOOK=0x2019C, FUNC=0x9CA10, RTRN=0x201A1 |
| LDPlayer14 海外版 | `F:\LDPlayer\LDPlayer14` | dnplayer.exe | HOOK=0x1DD33, FUNC=0x959F0, RTRN=0x1DD38 |

DLL 在 DllMain 中自动检测 dnplycore.dll 版本，循环尝试2组偏移，选择匹配的一组。

## 调用方法

### 默认模式（推荐）

```
keymap_injector.exe "<target.kmp 完整路径>"
```

**功能：** 注入 DLL + 触发一次 Ctrl+F + CFW 重定向

**效果：** 实际键位切换到目标方案（CCC），不影响其他按键

**示例：**
```
keymap_injector.exe "F:\LDPlayer\LDPlayer9\vms\customizeConfigs\com.android.settings_1920x1080(CCC).kmp"
keymap_injector.exe "F:\LDPlayer\LDPlayer14\vms\customizeConfigs\com.android.settings_1920x1080(CCC).kmp"
```

### --loop 模式（备用）

```
keymap_injector.exe --loop "<target.kmp>"
```

**功能：** 循环发送 Ctrl+F，直到 LDPlayer 原生切换到目标方案

**特点：** 不依赖 CFW hook，靠原生循环切换。提示和实际键位都一致，但需要多次 Ctrl+F（方案越多切换次数越多）

### --direct 模式（诊断）

```
keymap_injector.exe --direct "<target.kmp>"
```

**功能：** 通过 CreateRemoteThread 直接调用 setKeyboardConfig

**特点：** 诊断用，不触发 .kmp 读取

### --status 模式

```
keymap_injector.exe --status
```

**功能：** 打印 DLL 诊断信息（不执行任何操作）

**输出字段说明：**

| 字段 | 含义 |
|---|---|
| HookStatus | 位标志：0x02=dnplycore加载, 0x04=CALL站点, 0x08=目标匹配, 0x10=CALL hook安装, 0x20=CFW被调用, 0x40=CFW安装 |
| FuncAddress | setKeyboardConfig 运行时地址 |
| DecodedCallTarget | CALL 指令解码的目标地址（应与 FuncAddress 一致） |
| HookCount | CALL hook 触发次数（Ctrl+F 触发 setKeyboardConfig 的次数） |
| LastThis | setKeyboardConfig 的 this 指针 |
| LastOriginalArg | 原始参数（Ctrl+F 时为 0） |
| LastReplacementArg | 替换后的参数（指向共享内存中的目标文件名） |
| cfwKmpCount | .kmp 文件读取次数 |
| cfwRedirectCount | CFW 重定向次数 |

## 工作原理

### 策略 v2（CFW 重定向）

Ctrl+F 切换按键时，LDPlayer 会读取 .kmp 文件：
1. 第 1 次读取：当前方案（如 AAA）— 不重定向
2. 第 2、3 次读取：下一个方案（如 BBB）— 重定向到目标方案（CCC）的 .kmp 内容

**效果：** 内部索引记录 BBB，但实际读取的内容是 CCC → 实际键位为 CCC

### CALL hook

在 dnplycore.dll 中 `call setKeyboardConfig` 处安装 inline hook（E8→E9），替换参数为目标文件名。

### CFW hook

在 kernelbase.CreateFileW 处安装 inline hook，拦截 .kmp 文件读取并重定向。

## 编译方法

### 依赖

- Visual Studio 2022 (MSVC 14.x)
- Windows SDK 10.x
- x86 (32位) 目标

### 编译

```powershell
cd hook_demo
.\build.ps1
```

或手动编译：

```bat
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"
ml /c /coff hook_stub.asm
cl /LD /O2 /MT keymap_hook.cpp hook_stub.obj /Fekeymap_hook.dll /link
rc version.rc
cl /O2 /MT keymap_injector.cpp version.res /Fekeymap_injector.exe /link
```

## 已知限制

1. **提示不一致**：默认模式下，模拟器内安卓系统弹出的提示显示"下一个方案"名（如 BBB），而非目标方案名（CCC）。这是安卓系统内部的提示，无法通过 Windows 层面修改。实际键位是正确的（CCC）。
2. **杀毒软件报毒**：因使用 DLL 注入技术（CreateRemoteThread + VirtualAllocEx），可能被 Windows Defender 标记为 `Behavior:Win32/DefenseEvasion.A!ml`。解决方法：
   - 添加 Defender 排除文件夹
   - 提交微软白名单：https://www.microsoft.com/en-us/wdsi/filesubmission
   - 购买代码签名证书

## 文件清单

| 文件 | 说明 |
|---|---|
| keymap_hook.dll | Hook DLL（注入到 dnplayer.exe） |
| keymap_injector.exe | 注入器 + 命令行工具 |
| keymap_hook.cpp | Hook DLL 源码 |
| keymap_injector.cpp | 注入器源码 |
| hook_stub.asm | CALL hook 汇编跳板 |
| build.ps1 | PowerShell 编译脚本 |
| build.bat | 批处理编译脚本 |
| version.rc | 版本信息资源 |

## 版本历史

- v1: 初始版本，Ctrl+F 参数替换（失败）
- v2: CFW 重定向策略（LDPlayer9 海外版，已备份在 backup_v2_working/）
- **v3: 多版本兼容（LDPlayer9 海外/国内 + LDPlayer14，当前版本）**
  - 自动检测三组 dnplycore.dll 偏移
  - CFW hook 改为 kernelbase.CreateFileW（兼容 LDPlayer14）
  - 支持多种进程名
  - 添加版本信息减少杀毒误报
