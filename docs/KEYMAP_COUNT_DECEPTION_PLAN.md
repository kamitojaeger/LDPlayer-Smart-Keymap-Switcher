# 方案 C: 欺骗 LDPlayer 按键数量 — 开发文档

> 背景: LDPlayer 当某游戏在 `dir_kmps.dir` + `customizeConfigs/` 中合计 .kmp ≥ 3 时，Ctrl+F 弹出下拉栏而非循环切换，导致现有 DLL 注入方案失效。
>
> 方案 C 目标: 欺骗 LDPlayer 使其认为当前游戏仅有 2 个可选按键方案，恢复 Ctrl+F 循环行为。

## 1. 根因分析

### 数据来源

| 来源 | 路径 | 格式 | 加载时机 |
|---|---|---|---|
| 推荐配置索引 | `vms/recommendConfigs/dir_kmps.dir` | **JSON** (980 条) | LDPlayer 启动时 |
| 用户自定义配置 | `vms/customizeConfigs/*.kmp` | 遍历文件系统 | 按游戏动态扫描 |

`dir_kmps.dir` 结构 (纯文本 JSON):

```json
{
  "kmps": [
    {
      "packageNamePattern": "com.activision.callofduty.shooter|com.garena.game.codm",
      "fileName": "call of duty@02(battle royale).kmp",
      "resolutionType": 1,
      "resolutionPattern": { "width": 1600, "height": 900 },
      "priority": 0,
      "keyboardConfig": { ... }
    }
  ]
}
```

LDPlayer 通过 `packageNamePattern` (支持 `|` 分隔的多包名、`*` 通配符) 匹配当前运行游戏的包名，汇总匹配到的所有条目作为可选按键列表。

### 实测数据

```
GTASA (com.rockstargames.gtasa):
  dir_kmps.dir: 0 条匹配
  customizeConfigs: 2 个 .kmp (GTASA(walk mode).kmp, GTASA(Drive mode).kmp)
  合计: 2 → Ctrl+F 循环 ✓

CODM (com.activision.callofduty.shooter):
  dir_kmps.dir: 6 条匹配 (call of duty@01~03 + call of duty_w@01~03)
  customizeConfigs: 0 个 .kmp
  合计: 6 → Ctrl+F 弹出下拉栏 ✗
```

## 2. 方案设计

### 核心思路

在 LDPlayer 加载 `dir_kmps.dir` 或枚举 `customizeConfigs/` 下的 .kmp 文件时，拦截并**只保留 2 个我们需要的条目**，其余过滤掉。LDPlayer 内部看到 2 个按键 → Ctrl+F 循环 → 我们的 CFW redirect hook 正常接管。

### 2.1 方案 C1: customizeConfigs 覆盖优先 (首选, 0 代码改动)

**假设**: `customizeConfigs/` 中的 .kmp 会**覆盖**同名/同包的 `recommendConfigs` 条目。

**验证方法**:
```bash
# 1. 把 CODM 的 2 个 .kmp 复制到 customizeConfigs
cp "games/CODM/keymaps/CODM((walk).kmp" \
   "F:/LDPlayer/LDPlayer9/vms/customizeConfigs/"
cp "games/CODM/keymaps/CODM((car_drive_1).kmp" \
   "F:/LDPlayer/LDPlayer9/vms/customizeConfigs/"

# 2. 启动 LDPlayer → 进入 CODM → 按 Ctrl+F
# 预期: 只看到 2 个方案在循环（walk + car_drive_1）
#       而不是 6 个推荐方案
```

如果此假设成立，**零开发量**解决。我们的 `_maybe_sync_keymaps()` 函数（`main.py` 第 217-265 行）已经在做自动复制了。

### 2.2 方案 C2: 扩展 CFW Hook 过滤 dir_kmps.dir (备选)

如果 C1 不成立（`customizeConfigs` 不能覆盖推荐条目），则需要在 DLL 层面过滤。

**原理**: 扩展现有 `CreateFileW` hook，当 LDPlayer 读取 `dir_kmps.dir` 时:

1. 检测到文件名 = `dir_kmps.dir`
2. 读取原始文件内容 (JSON)
3. 根据当前游戏的包名，只保留 2 个匹配条目，**删除其余匹配条目**
4. 将修改后的 JSON 内容返回给 LDPlayer
5. LDPlayer 的内存中只有 2 个按键 → Ctrl+F 循环

**关键判断**: `dir_kmps.dir` 的加载是**仅启动时一次**还是**每次进入游戏时重新加载**?

- 如果仅启动时一次 → 需要 LDPlayer 重启才能生效，实用性差
- 如果每次进入游戏时重新加载 → 完美，Hook 可以在游戏运行时拦截

**快速验证**:
```bash
# 1. 启动 LDPlayer, 进入任意游戏
# 2. 修改 dir_kmps.dir (添加一条新条目)
# 3. 重启游戏 (不重启 LDPlayer), 按 Ctrl+F
# 4. 如果新条目出现在列表中 → 每次进入游戏重新加载 → C2 可行
```

### 2.3 方案 C3: Hook .kmp 文件枚举 (通用兜底)

如果以上方案都不可行，直接 hook LDPlayer 枚举 `.kmp` 文件的相关 API:

**Windows API 调用链** (推测):
```
FindFirstFileW("*.kmp") → FindNextFileW → 遍历 customizeConfigs/
CreateFileW("dir_kmps.dir") → 读取 JSON → 解析 packageNamePattern
```

**Hook 点**:
- `kernel32!FindFirstFileW` — 拦截目录枚举，返回只含 2 个我们需要的文件名
- 或 `kernelbase!CreateFileW` — 已 hook，扩展检测 `dir_kmps.dir` 文件名

**FindFirstFileW 方案**:
```
原始: FindFirstFileW("*.kmp") → 返回 6 个文件
Hook: FindFirstFileW("*.kmp") → 调用原始 → 获取全部结果
      → 内存中只保留 2 个目标文件名 → 伪造 FIND_DATA → 返回
      → FindNextFileW 也 hook → 控制返回次数
```

## 3. 新增 CFW Hook 逻辑 (方案 C2 详细设计)

在 `keymap_hook.cpp` 的 `HkCW` 函数中新增分支:

```cpp
// 现有逻辑: 拦截 .kmp 文件读取 → CFW redirect
// 新增逻辑: 拦截 dir_kmps.dir 文件读取 → 过滤内容

if (strstr(lpFileName, "dir_kmps.dir")) {
    // 1. 调用原始 CreateFileW 打开文件
    // 2. 读取全部内容到内存
    // 3. 解析 JSON, 找到匹配当前游戏包名的条目
    // 4. 只保留前 2 个条目, 删除其余匹配条目
    //    注意: 只删除"匹配当前包名"的条目, 
    //          其他游戏的条目保留不动
    // 5. 将修改后的 JSON 写入临时文件
    // 6. 返回临时文件的句柄
    // 7. 关闭时删除临时文件
}

// 或者更简单: 
// 不拦截 CreateFileW, 而是拦截 ReadFile
// 在 ReadFile 后修改缓冲区内容
```

### 伪代码

```cpp
static std::string lastKmpDirContent; // 缓存修改后的内容
static size_t     lastKmpDirOffset = 0; // 读取偏移

// 在 ReadFile hook 中:
if (isReadingDirKmps) {
    // 拦截第一次 ReadFile
    if (lastKmpDirContent.empty()) {
        // 先让原始 ReadFile 读取完整内容
        char buf[1024*1024];
        DWORD bytesRead;
        orig_ReadFile(hFile, buf, sizeof(buf), &bytesRead, NULL);
        
        // 解析 JSON
        json j = json::parse(buf);
        
        // 过滤: 对于匹配当前包名的条目, 只保留前 2 个
        std::string targetPkg = getCurrentGamePackage(); // 从共享内存获取
        auto& kmps = j["kmps"];
        vector<json> kept;
        int matchCount = 0;
        int totalCount = 0;
        for (auto& k : kmps) {
            if (packageMatches(k["packageNamePattern"], targetPkg)) {
                if (matchCount < 2) kept.push_back(k);
                matchCount++; // 不加入 kept, 但仍计数
            } else {
                kept.push_back(k); // 其他游戏保持不动
            }
            totalCount++;
        }
        j["kmps"] = kept;
        
        // 缓存修改后的内容
        lastKmpDirContent = j.dump();
        lastKmpDirOffset = 0;
    }
    
    // 返回缓存内容
    size_t remain = lastKmpDirContent.size() - lastKmpDirOffset;
    size_t toCopy = min(remain, nNumberOfBytesToRead);
    memcpy(lpBuffer, lastKmpDirContent.data() + lastKmpDirOffset, toCopy);
    lastKmpDirOffset += toCopy;
    *lpNumberOfBytesRead = (DWORD)toCopy;
    
    if (lastKmpDirOffset >= lastKmpDirContent.size()) {
        // 读取完毕, 清理
        lastKmpDirContent.clear();
        lastKmpDirOffset = 0;
    }
    
    return TRUE;
}
```

## 4. 共享内存扩展

需要在 `SharedData` 中新增字段传递当前游戏包名:

```cpp
struct SharedData {
    // ... 现有字段 ...
    DWORD  magic;                  // 0x4B4D5053
    char   targetPath[1024];       // 目标 .kmp 路径
    DWORD  flags;                  // bit0=CFW, bit1=CALL
    // === 新增字段 ===
    char   gamePackageName[256];   // 当前游戏包名 (如 "com.activision.callofduty.shooter")
    DWORD  maxKeymapCount;         // 允许的最大按键数量 (默认 2)
    DWORD  reserved[8];            // 预留扩展
};
```

## 5. 验证步骤

### 5.1 C1 快速验证 (10 分钟)

```bash
# 1. 复制 2 个 .kmp 到 customizeConfigs
cp "D:/LD_DEV/LDPlayer_Auto_Input_Switcher/games/CODM/keymaps/CODM((walk).kmp" \
   "F:/LDPlayer/LDPlayer9/vms/customizeConfigs/"
cp "D:/LD_DEV/LDPlayer_Auto_Input_Switcher/games/CODM/keymaps/CODM((car_drive_1).kmp" \
   "F:/LDPlayer/LDPlayer9/vms/customizeConfigs/"

# 2. 启动 LDPlayer → CODM → Ctrl+F
# 3. 观察: 是循环 2 个方案还是显示 8 个 (6+2)?
```

### 5.2 dir_kmps.dir 重载验证 (5 分钟)

```bash
# 1. LDPplayer 启动, CODM 运行中
# 2. 修改 customizeConfigs 下某个 CODM .kmp 的名称
# 3. 重启 CODM (关闭游戏再打开, 不重启 LDPlayer)
# 4. 按 Ctrl+F → 观察按键列表是否更新
#    更新 = 每次进入游戏重新加载 = C2 可行
#    不更新 = 仅启动加载 = 需要 C3
```

### 5.3 C2 概念验证 (1 小时)

1. 在现有 `keymap_hook.dll` 中添加 `ReadFile` hook
2. 检测到 `dir_kmps.dir` 句柄 → 拦截内容 → 过滤 CODM 条目 → 只保留 2 个
3. 注入测试

## 6. 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| customizeConfigs 不能覆盖推荐条目 | 🟡 中 | 接 C2 方案 |
| dir_kmps.dir 仅启动时加载一次 | 🟡 中 | 接 C3 (FindFirstFileW hook) 或要求用户重启 |
| JSON 修改后被 LDPlayer 校验拒绝 | 🟢 低 | JSON 格式完全合法, 只是少了几条 |
| 其他游戏也受影响 | 🟢 低 | 只过滤"匹配当前包名"的条目, 其他游戏不动 |
| ReadFile hook 的线程安全问题 | 🟡 中 | 同现有 CFW hook 的 "恢复-调用-重装" 模式 |

## 7. 优先行动项

| 步骤 | 优先级 | 预计耗时 |
|---|---|---|
| 验证 C1: customizeConfigs 是否覆盖推荐条目 | **P0** | 10 分钟 |
| 验证 dir_kmps.dir 重载时机 | **P0** | 5 分钟 |
| 扩展 CFW hook 拦截 dir_kmps.dir 读取 | P1 | 2-4 小时 |
| 实现 JSON 过滤逻辑 | P1 | 1-2 小时 |
| 共享内存新增 gamePackageName 字段 | P2 | 30 分钟 |
| Python 端 set_game_package() 调用 | P2 | 30 分钟 |
| 端到端测试: CODM 启动 → 仅 2 个按键循环 → CFW redirect 正常工作 | P2 | 1 小时 |
