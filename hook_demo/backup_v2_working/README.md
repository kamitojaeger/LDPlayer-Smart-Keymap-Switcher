# Backup: v2_working (2026-07-07 14:12)

## 状态：核心需求已满足

- ✅ 切换到指定按键（实际键位 = 目标 CCC）
- ✅ 不影响其他按键（bit0 清除后 Ctrl+F/F12 正常）
- ⚠️ 提示显示 BBB（内部索引），实际键位 CCC（重定向内容）— 不一致

## 工作原理（策略 v2）

Ctrl+F 触发 3 次 .kmp 读取：
```
[0] AAA.kmp              ← 当前方案，不重定向（让 LDPlayer 正确识别当前位置）
[1] BBB.kmp → CCC.kmp    ← "下一个"方案内容，重定向到目标
[2] BBB.kmp → CCC.kmp    ← "下一个"再次读取，重定向到目标
```

LDPlayer 的"应用"步骤使用读取的 .kmp **内容**，所以实际键位变成 CCC。
但"下一个"的**决定**基于列表索引（AAA→BBB），提示和 .smp 记录 BBB。

## 关键文件

| 文件 | 说明 |
|---|---|
| keymap_hook.cpp | CFW hook（策略 v2：idx>=1 重定向，不清除 bit0） |
| hook_stub.asm | CALL hook（栈布局已修复，但参数替换对切换无实际作用，保留诊断） |
| keymap_injector.cpp | injector v3（TriggerOnceAndVerify 验证后清除 bit0） |
| build.ps1 | PowerShell 编译脚本（无需 cmd） |

## 编译产物

- keymap_hook.dll (85504 bytes) — 注入到 dnplayer.exe
- keymap_injector.exe (134144 bytes) — 设置目标 + 触发 Ctrl+F

## 使用方法

```
keymap_injector.exe "F:\LDPlayer\LDPlayer9\vms\customizeConfigs\<target>.kmp"
```

## 诊断发现历史

1. HookStub 栈布局 bug（jmp 无返回地址）→ 已修复
2. CFW 诊断盲区（bit0 清除后不计数）→ 已修复
3. setKeyboardConfig 参数替换无效（77A33C60 不用 targetPath 读文件）→ 放弃参数替换
4. 重定向 [0]（当前方案）无效 → 改为重定向 [1]/[2]（下一个方案内容）→ 成功
5. bit0 不清除导致后续切换受影响 → injector 验证后清除 bit0 → 已修复

## 待解决

提示不一致：Ctrl+F 提示 BBB，实际 CCC。需要 hook "决定下一个方案"的代码，
或修改内部循环索引，让"下一个"直接是 CCC。
