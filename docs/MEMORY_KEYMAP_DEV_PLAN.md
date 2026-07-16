# 方案 B: 内存直写按键方案 — 开发文档

> 背景: LDPlayer 当 `customizeConfigs/` 目录下对应游戏的 .kmp 文件超过一定数量后，Ctrl+F 不再循环切换，而是弹出下拉选择栏，导致当前的 DLL 注入方案失效。
>
> 方案 B 目标: 绕过 Ctrl+F 机制，直接从内存中定位并修改当前游戏的按键映射数据。

## 1. 前置发现: .kmp 文件格式

`.kmp` 文件是 **纯文本 UTF-8 JSON**（非二进制），结构如下:

```json
{
  "keyboardMappings": [
    {
      "class": "ClassKeyboardDisc",
      "data": {
        "type": 0,
        "origin": { "x": 1824, "y": 8413 },
        "radius": 773,
        "leftKey": 65,      // 虚拟键码: A
        "upKey": 87,        // W
        "rightKey": 68,     // D
        "downKey": 83       // S
      }
    },
    {
      "class": "ClassMouseDrag",
      "data": {
        "key": 17,          // Ctrl — 射击视角
        "mode": 0,
        "origin": { "x": 6086, "y": 3156 }
      }
    },
    {
      "class": "ClassKeyboardCurve",
      "data": {
        "key": 32,          // Space — 跳跃
        "curve": [ {"x": 9505, "y": 6879, "timing": 0} ]
      }
    }
  ]
}
```

### 已确认的 class 类型

| class | 数据特征 | 示例 |
|---|---|---|
| `ClassKeyboardDisc` | 虚拟方向摇杆: 4 方向 + 半径 `radius` | WASD 移动 |
| `ClassMouseDrag` | 鼠标拖拽射击: `key`= 激活键, `sensitivity` | Ctrl + 鼠标 = 射击 |
| `ClassKeyboardCurve` | 曲线按键: `key` + `curve[]` = 关键帧位置 | 单点 = 普通按键 |
| `ClassKeyboardMacros` | 宏按键: `macros` 字符串 = 触控脚本 | Esc → touch + switch-mouse |
| `ClassMouseTrigger` | 鼠标点击: `point` 坐标 | 点击屏幕某位置 |

### 坐标系统

`origin.x` / `origin.y` 的值**不是屏幕像素**（如 9495 远超 1920）。推测是 LDPlayer 内部归一化坐标（可能基于触摸传感器分辨率），需通过逆向确定映射关系。

## 2. 目标: 找到内存中的按键结构体

### 已知入口

- `vbox::CInputMgr::setKeyboardConfig(this, char* kmpPath)` — 加载 .kmp 的入口，位置 `dnplycore.dll + 0x9CA10`
- `vbox::CInputMgr` 的 this 指针通过 vtable getter 获取（`call [ecx+0xD8]`）
- `CInputMgr` 内部必然持有当前活跃的 `keyboardMappings` 数组

### 逆向路线

```
setKeyboardConfig 函数 (0x9CA10)
  → 解析 .kmp JSON → 存储到内部数据结构
  → 映射关系: JSON class 名称 → C++ 类构造
  → 最终数据存放在 CInputMgr 的成员中
```

**核心思路**: 我们不调用 `setKeyboardConfig`，而是直接找到它写入内存的那个数据结构地址，往里面写我们想要的值。

## 3. 分阶段逆向计划

### 阶段 3.1: 定位内存中的按键数组

**目标**: 找到当前游戏的所有 `keyboardMapping` 条目在内存中的地址

**方法 A — 特征值搜索**:
1. 在 LDPlayer 中加载一个已知 .kmp（如 walk mode: A W D S 键位）
2. 用 x32dbg 附加 dnplayer.exe
3. 在 Cheat Engine 或 x32dbg 中搜索已知特征值:
   - `ClassKeyboardDisc` 的 origin 坐标 (1824, 8413) — 4 字节 int
   - key 值 65 (A) / 87 (W) / 68 (D) / 83 (S)
   - 连续搜索 4 个 key 值可以唯一标识该结构体
4. 记录找到的地址，验证是否为 CInputMgr 的成员

**方法 B — 数据断点**:
1. 在 `setKeyboardConfig` 内部下断点
2. 步进到解析 JSON 后写入内存的代码
3. 在目标内存地址设硬件断点，触发时观察调用栈
4. 回溯到 CInputMgr 中存储该指针的成员偏移

**方法 C — 内存 dump 对比**:
1. 加载 walk.kmp → dump dnplayer.exe 内存 → 搜索 A/W/D/S (0x41/0x57/0x44/0x53) 连续出现的位置
2. 加载 drive.kmp → dump 内存 → 对比两个 dump 的差异
3. 发生变化的区域即为按键映射数据

### 阶段 3.2: 确定数据结构布局

推测 C++ 内存布局（需验证）:

```
// 单个按键映射条目
struct KeyMapping {
    uint32_t classType;      // 0=Disc, 1=MouseDrag, 2=Curve, 3=Macros, 4=MouseTrigger
    int32_t  originX;        // 归一化 X 坐标
    int32_t  originY;        // 归一化 Y 坐标
    int32_t  key1;           // 主键 (virtual key code)
    int32_t  key2;           // 副键 (0 = 无)
    int32_t  radius;         // ClassKeyboardDisc 的半径
    // ... 更多字段
};

// CInputMgr 内部（偏移未知，需通过逆向确定）
struct CInputMgr {
    // offset 0x??  — 指向当前 keymap 名称的指针 (char*)
    // offset 0x??  — keyMapping 条目数量 (int)
    // offset 0x??  — 指向 KeyMapping 数组的指针
};
```

**验证方法**: 已知 `.kmp` 是 JSON，可以构造一个"探针 .kmp"——每个字段用不同的唯一值（如 origin.x=1111, origin.y=2222, radius=3333），加载后在内存中搜索 0x0457 (1111) 0x08AE (2222) 0x0D05 (3333) 的连续模式来定位。

### 阶段 3.3: 建立 .kmp JSON → 内存字段的映射表

对每种 class 类型，逐一确定:
1. JSON 字段名 → 内存偏移
2. 数据类型（int/float/string）
3. 数值是否需要转换（如坐标缩放）

**推荐方法**: 创建 5 个最小化的探针 .kmp，每种 class 一个，只包含该 class 必要的最少字段，加载后用特征值定位。

### 阶段 3.4: 实现内存读写

**方案 A — C++ DLL 扩展**（推荐）:
在现有 `keymap_hook.dll` 中新增功能:
```cpp
// 新共享内存命令
// flags bit2 = 内存直写模式
struct SharedData {
    // ... 现有字段 ...
    DWORD memoryMode;           // 0=CFW模式, 1=内存直写模式
    DWORD keyMappingCount;      // 要写入的条目数
    KeyMappingRaw mappings[64]; // 按键映射数据（固定大小数组）
};
```

**方案 B — Python + ReadWriteProcessMemory**:
通过 `win32api` / `ctypes` 直接读写 dnplayer.exe 的内存:
```python
import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL('kernel32')
# ReadProcessMemory / WriteProcessMemory
```

## 4. 与现有方案的集成

### 切换流程（内存直写模式）

```
[injector.py]
  → 读取目标 .kmp JSON 文件
  → 解析 keyboardMappings 数组
  → 将 JSON 字段转换为内存格式
  → 通过共享内存传入 DLL

[keymap_hook.dll]  
  → 从共享内存读取 KeyMappingRaw 数组
  → WriteProcessMemory 写入 dnplayer.exe 目标地址
  → （可选）调用内部刷新函数使更改生效
```

### 坐标转换

.JSON 中的坐标值（`origin.x`, `origin.y` 等）是 LDPlayer 内部格式。
需通过以下方式确定是否需要转换:

1. 加载一个 .kmp，读取 JSON 中 `origin.x` = X_json
2. 在内存中找到对应条目，读取 `originX` = X_mem
3. 比较 X_json 和 X_mem:
   - 若相等 → 无需转换，JSON 值直接用作内存值
   - 若有固定比例 → 记录缩放因子 `scale = X_mem / X_json`
   - 若完全不同 → 坐标系统不同，需另寻映射关系

## 5. 风险评估

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| LDPlayer 版本更新导致内存偏移变化 | 🔴 高 | 采用特征值搜索 + 版本偏移表（同现有 hook 方案） |
| 内存结构体布局复杂（含虚函数表指针等） | 🟡 中 | 从简单类型（int坐标、key值）开始，逐步扩展 |
| 写入后 LDPplayer 需要额外刷新才能生效 | 🟡 中 | 逆向 setKeyboardConfig 找到通知机制（可能是 PostMessage 或回调） |
| 多线程并发写入导致崩溃 | 🟢 低 | 监控循环是单线程的；可加 CriticalSection |
| 杀毒软件检测 ReadWriteProcessMemory | 🔴 高 | 写入操作在 DLL 内部（已注入的合法模块），不走外部进程 |

## 6. 优先行动项

| 步骤 | 优先级 | 预计耗时 | 产出 |
|---|---|---|---|
| 创建探针 .kmp 加载 → x32dbg/Cheat Engine 搜索特征值 | P0 | 2-4h | 确认内存地址是否可定位 |
| dump walk vs drive 内存，diff 找变化区域 | P0 | 1-2h | 确认按键数据区域 |
| 确定 CInputMgr 的 keymap 相关成员偏移 | P1 | 4-8h | C++ 结构体定义 |
| 验证坐标是否需要转换 | P1 | 1h | 坐标映射公式 |
| 测试 WriteProcessMemory 直接修改 key 值 | P1 | 2h | 概念验证 (PoC) |
| 实现完整的 JSON→内存 转换器 | P2 | 4-8h | Python 端集成 |
| 集成到 keymap_hook.dll / keymap_injector.exe | P2 | 8-16h | 完整的切换链路 |

## 7. 快速验证命令

```bash
# 1. 创建探针 .kmp (最小化按键)
echo '{"keyboardMappings":[{"class":"ClassKeyboardDisc","data":{"type":0,"origin":{"x":1111,"y":2222},"radius":3333,"leftKey":65,"upKey":0,"rightKey":0,"downKey":0}}]}' > probe.kmp

# 2. 复制到 LDPlayer customizeConfigs
cp probe.kmp "F:/LDPlayer/LDPlayer14/vms/customizeConfigs/"

# 3. 加载后在 Cheat Engine 搜索:
#    - 4-byte: 1111 (0x0457)
#    - 如果命中，检查周围是否有 2222 (0x08AE) 和 3333 (0x0D05)
#    - 连续出现 → 确认找到结构体

# 4. 验证: 修改内存中的 key 值 (65 → 87)，看游戏按键是否从 A 变成 W
```

## 8. 参考资料

- 已逆向的函数偏移: 见 `config/ldplayer_versions.json`
- .kmp 解析调用链: `setKeyboardConfig` → 内部 JSON parser → 填充 CInputMgr 成员
- 现有 hook 通信机制: `LDKeymapSwitch_Mem` 共享内存，结构定义在 `keymap_hook.cpp`
- x32dbg 调试器路径: `x64-x32dbg/release/x32/x32dbg.exe`

---

## 9. 进展记录

### 2026-07-14: 阶段 3.1 实验

#### 完成项

**9.1 LDPlayer14 偏移更新**
- 发现当前版本偏移已变化，通过签名搜索定位新偏移：
  - `HOOK_RVA`: 0x1DA53 (旧: 0x1DD33)
  - `FUNC_RVA`: 0x96130 (旧: 0x959F0)
  - `RTRN_RVA`: 0x1DA58 (旧: 0x1DD38)
- 更新了 `src/core/keymap_hook.cpp` 和 `config/ldplayer_versions.json`
- 成功重新编译 `keymap_hook.dll` + `keymap_injector.exe`（MSVC 14.51 + MASM，x86）

**9.2 CALL hook 验证**
- 新 DLL CALL hook 验证成功 (status 0x5E = 全部通过)
- 成功将探针 `probe_disc.kmp`（含特征值 1111/2222/3333）加载到 LDPlayer

**9.3 CInputMgr 对象定位**
- `this` 指针: 0x051E8CB0
- 对象非标准 vtable 布局（首 4 字节不是虚表指针）
- 对象内发现多个 dnplycore.dll 函数指针和堆对象引用
- 调用点上下文（RVA 0x1DA53）:
  ```
  mov ecx, [eax+0x20]        ; 获取某指针
  push 0                      ; arg=0 (循环模式)
  call [ecx+0xD8]             ; vtable getter → 返回 CInputMgr*
  mov ecx, eax                ; this = getter 返回值
  call setKeyboardConfig      ; (已被 hook 替换为 jmp HookStub)
  ```

**9.4 关键发现: JSON 文本存在于内存中** ⭐
- LDPlayer **不将 keymap 值存储为二进制 int32**，而是**保留原始 JSON 字符串**
- 探针 `probe_disc.kmp` 的 JSON 文本在 **4 个内存位置**被找到:
  - `0x054C4D43`: 格式化 JSON 片段
  - `0x1DA749F7`: 完整 `"keyboardMappings"` JSON
  - `0x1DA75B97`: 另一个副本
  - `0x1DAC0D43`: 另一个副本
- 二进制搜索（int32 格式）1111/2222/3333 未命中，确认 LDPlayer 内部做了格式转换

#### 对 Plan B 的影响

**9.5 方案调整建议**
- 原始方案（找二进制结构体 → 直接写内存）需要大量逆向工作
- **新思路**: 利用内存中的 JSON 文本 — 修改 JSON 字符串后触发 LDPlayer 重新解析
  - 优点: 不需要理解 C++ 结构体布局
  - 风险: 需确认 LDPlayer 是否会重新读取/解析该 JSON
  - 备选: 写完后手动触发 setKeyboardConfig 重新加载

**9.6 下一步**
- [x] P0: ~~通过 CreateRemoteThread 调用 setKeyboardConfig~~ — **失败: 非 GUI 线程不执行工作**
- [x] P0: ~~调用内联函数 0x961F0 绕过外层包装~~ — **失败: 线程检查更深层**
- [ ] P0: x32dbg 单步跟踪确定线程检查的具体位置和绕过方法
- [ ] P0 (替代): Win32 `PostMessage` 自定义消息到 GUI 线程触发 keymap 加载
- [ ] P1: 逆向 CInputMgr 内部 keymap 数据结构，直接改内存中的 C++ 对象

### 2026-07-14 (续3): 静态分析 setKeyboardConfig 内部结构

**9.11 函数结构分析**
- `setKeyboardConfig` @ RVA 0x96130: 薄包装，~176 字节
  - 拷贝文件名 (arg != 0 时)
  - 检查 `this->[9]` 和 `this->[4]`（提前返回条件）
  - 调用子函数 `0x036F0` (1-2 次)
  - 调用 IAT 函数 `[0x6bdcd1f4]` / `[0x6bdcd1ec]`
- **内联函数** @ RVA 0x961F0 (~8KB): 紧接在 setKeyboardConfig 后
  - 有 SEH 异常处理
  - 访问 `this + 0xDD94` 成员 (CInputMgr 大型对象)
  - 有相同参数签名 `(CInputMgr* this, void* arg)`
- **子函数** @ RVA 0x036F0: 调用 IAT → Win32 API
- **测试结果**: 从远程线程调用内联函数 0x961F0 同样不触发 I/O
- **结论**: 线程检查位于更深层 (0x036F0 或 IAT 调用的 Win32 API 内部)
