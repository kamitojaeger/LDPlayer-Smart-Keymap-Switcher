# LDPlayer 按键切换工具 v6（自动射击视角）

## 相比 v5 的增量

| 维度 | v5 (backup_v5_preinit+OpenCVStateChecker) | v6 (当前版本) |
|---|---|---|
| **按键注入** | keymap_injector init + 切换 | 不变 |
| **状态检测** | OpenCV 模板匹配 walk/drive | 不变 |
| **射击视角** | 无 | 🆕 切换后自动恢复射击视角 (ClassMouseDrag) |
| **调试图** | 红框 + 绿框 + 匹配率 | 不变 |

## 射击视角自动恢复

### 问题

.kmp 文件中 `ClassMouseDrag` 定义了「射击视角」模式（鼠标锁定在窗口内，移动→拖动），`switch-mouse` 宏实现进入/退出切换。自动检测并切换按键方案后，射击视角状态会丢失，用户需要手动重新进入。

### 解决方案

1. 切换前解析目标 .kmp JSON，查找 `ClassMouseDrag` 及其绑定的虚拟键码
2. 切换完成后通过 `keybd_event` API 发送该键码

### 关键技术点

- **SendInput 不可用**：LDPlayer 的 `WH_KEYBOARD_LL` 低级钩子通过 `LLKHF_INJECTED` 标志过滤 SendInput 注入的输入
- **keybd_event 有效**：已废弃的 `keybd_event` API 不设置注入标志，能绕过过滤
- **发送的 key**：从 ClassMouseDrag 的 `data.key` 字段解析（DDD.kmp 示例：key=17，即 Ctrl 键）
- **延时**：切换后无需额外等待（injector 内部 subprocess.run 已确保切换完成）

## 支持的模拟器版本

| 版本 | 安装路径示例 | 进程名 | dnplycore.dll 偏移 |
|---|---|---|---|
| LDPlayer9 海外版 | `F:\LDPlayer\LDPlayer9` | dnplayer.exe | HOOK=0x2019C, FUNC=0x9CA10, RTRN=0x201A1 |
| LDPlayer14 海外版 | `F:\LDPlayer\LDPlayer14` | dnplayer.exe | HOOK=0x1DD33, FUNC=0x959F0, RTRN=0x1DD38 |

## 文件清单

| 文件 | 说明 |
|---|---|
| **keymap_hook.dll** | Hook DLL（注入到 dnplayer.exe） |
| **keymap_injector.exe** | 注入器 + 命令行工具 |
| keymap_hook.cpp | Hook DLL 源码 |
| keymap_injector.cpp | 注入器源码 |
| hook_stub.asm | CALL hook 汇编跳板 |
| build.ps1 / build.bat | 编译脚本 |
| version.rc | 版本资源 |
| **screenshot_ldplayer.py** | 🔧 Python 截图 + OpenCV 状态检测 + 自动切换 + 射击视角恢复 |
| requirements.txt | Python 依赖 |
| **test_mouse_drag_key.py** | 🆕 第一轮测试：SendInput 方式发送按键（全部无效） |
| **test_mouse_drag_key2.py** | 🆕 第二轮测试：keybd_event/PostMessage/SendMessage 等（keybd_event 有效） |
| com.android.settings_1920x1080(AAA~DDD).kmp | 测试用 .kmp 文件 |

## 调用方法

### keymap_injector（手动控制）

```bash
keymap_injector.exe init
keymap_injector.exe "<目标.kmp>"
keymap_injector.exe --status
```

### screenshot_ldplayer.py（自动检测 + 切换 + 射击视角）

```bash
pip install -r requirements.txt
python screenshot_ldplayer.py
```

运行时流程：
1. 实例守卫 — 确认只有一个 dnplayer.exe
2. `keymap_injector.exe init` — 预注入 DLL
3. 进入循环（每 0.5 秒）：
   - dxcam 截图 → OpenCV 模板匹配 → 检测 walk ↔ drive 状态变化
   - 变化时调用 `keymap_injector.exe "<对应.kmp>"`
   - **🆕 若新 .kmp 含 ClassMouseDrag → `keybd_event` 发送对应 key 进入射击视角**
   - Ctrl+C 停止

## screenshot_ldplayer.py 新增函数

| 函数 | 说明 |
|---|---|
| `parse_kmp_mouse_drag_key(kmp_path)` | 解析 .kmp JSON，返回 ClassMouseDrag 的 key 码（无则 None） |
| `send_key_vk(vk_code)` | 通过 `keybd_event` API 发送虚拟键（down + up） |

## 工作原理

### 策略 v2（CFW 重定向）

Ctrl+F 切换按键时，LDPlayer 读取 .kmp 文件：
1. 第 1 次读取：当前方案 — 不重定向
2. 第 2、3 次读取：下一个方案 — 重定向到目标方案

### CALL hook

dnplycore.dll 中 `call setKeyboardConfig` 处 inline hook（E8→E9），替换参数为目标文件名。

### CFW hook

kernelbase.CreateFileW 处 inline hook，拦截 .kmp 文件读取并重定向。

## 编译方法

```powershell
cd hook_demo
.\build.ps1
```

依赖：Visual Studio 2022 + Windows SDK 10.x + x86 目标

## 已知限制

1. **提示不一致**：安卓系统弹出"切换到 BBB"但实际键位是 CCC
2. **杀毒软件报毒**：DLL 注入可能被 Defender 标记
3. **CFW hook 非线程安全**：恢复-调用-重装模式
4. **国内版不兼容**
5. **🆕 射击视角为无条件恢复**：当前方案不考虑切换前是否已处于射击视角，每次切换后均发送 ClassMouseDrag key。若目标 .kmp 无 ClassMouseDrag 则不操作
6. **🆕 injector 内部延时**：subprocess.run 等待 injector 完成（含 1.5s 内部验证），是切换延迟的主要来源。后续可考虑在 Python 中直接操作共享内存 + 发送 Ctrl+F 来消除此延时

## 版本历史

- v1: 初始版本，Ctrl+F 参数替换（失败）
- v2: CFW 重定向策略
- v3: 多版本兼容（LDPlayer9 + LDPlayer14）
- v4: 预初始化 init 命令
- v5: 集成 OpenCV 状态检测 + 自动切换
- **v6**: 🆕 自动射击视角恢复（当前版本）
  - 解析 .kmp ClassMouseDrag key
  - keybd_event API 绕过输入注入过滤
  - 测试脚本验证多种按键发送方式
