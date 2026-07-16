# LDPlayer 按键切换工具 v5（preInit + OpenCV 状态检测器）

## 相比 v4 的增量

| 维度 | v4 (backup_v4_preInit) | v5 (当前版本) |
|---|---|---|
| **按键注入** | keymap_injector init + 切换 | 不变 |
| **状态检测** | 无 | screenshot_ldplayer.py: dxcam 截图 + OpenCV 模板匹配 |
| **自动化** | 手动执行切换命令 | 循环监控 → 检测 walk/drive 变化 → 自动调用 keymap_injector |
| **调试图** | 无 | 红框(搜索区) + 绿框(匹配位) + 匹配率 标注 |

## 支持的模拟器版本

| 版本 | 安装路径示例 | 进程名 | dnplycore.dll 偏移 |
|---|---|---|---|
| LDPlayer9 海外版 | `F:\LDPlayer\LDPlayer9` | dnplayer.exe | HOOK=0x2019C, FUNC=0x9CA10, RTRN=0x201A1 |
| LDPlayer14 海外版 | `F:\LDPlayer\LDPlayer14` | dnplayer.exe | HOOK=0x1DD33, FUNC=0x959F0, RTRN=0x1DD38 |

DLL 在 DllMain 中自动检测 dnplycore.dll 版本，循环尝试 2 组偏移，选择匹配的一组。

## 文件清单

| 文件 | 说明 |
|---|---|
| **keymap_hook.dll** | Hook DLL（注入到 dnplayer.exe） |
| **keymap_injector.exe** | 注入器 + 命令行工具 |
| keymap_hook.cpp | Hook DLL 源码（CALL hook + CFW hook + DllMain） |
| keymap_injector.cpp | 注入器源码（DLL 注入 + Ctrl+F 发送 + 命令行接口） |
| hook_stub.asm | CALL hook 汇编跳板 |
| build.ps1 | PowerShell 编译脚本 |
| build.bat | 批处理编译脚本 |
| version.rc | 版本信息资源 |
| **screenshot_ldplayer.py** | 🆕 Python 截图 + OpenCV 状态检测 + 自动切换 |
| requirements.txt | Python 依赖（dxcam, pywin32, pillow, numpy, opencv-python-headless） |
| driveSample.png | 🆕 驾驶模式样本图标（178×176，参考分辨率 1920×1080 游戏区） |
| walkSample.png | 🆕 行走模式样本图标（180×178，参考分辨率 1920×1080 游戏区） |

## 调用方法

### keymap_injector（手动控制）

```bash
# 预初始化（启动 LDPlayer 后执行一次，约2秒）
keymap_injector.exe init

# 切换到指定按键方案（快速，无等待）
keymap_injector.exe "F:\LDPlayer\LDPlayer14\vms\customizeConfigs\com.rockstargames.gtasa_1920x1080(Drive mode).kmp"

# 查看诊断状态
keymap_injector.exe --status
```

### screenshot_ldplayer.py（自动检测 + 切换）

```bash
# 安装依赖
pip install -r requirements.txt

# 一键启动：init → 循环监控 → 自动切换
python screenshot_ldplayer.py

# 对已有图片做离线匹配测试
python screenshot_ldplayer.py --match testScreenShots/screenshot.png

# 只列出窗口不截图
python screenshot_ldplayer.py --list
```

运行时流程：
1. 实例守卫 — 确认只有一个 dnplayer.exe
2. `keymap_injector.exe init` — 预注入 DLL
3. 进入循环（每 0.5 秒）：
   - dxcam 截图 dnplayer 客户端区域
   - OpenCV 右下角模板匹配（带 mask，排除灰色背景噪声）
   - 检测 walk ↔ drive 状态变化
   - 变化时自动调用 `keymap_injector.exe "<对应.kmp>"`
   - Ctrl+C 停止

## screenshot_ldplayer.py 技术细节

### 模板匹配坐标系

参考截图 = 1980×1140（游戏区 1920×1080 + 上栏 60px + 右侧工具栏 60px）。
sample 图标在参考截图中的右下角位置：距右边约 40+60=100px，距下边约 40px。
脚本按 `scale = 截图高度 / 1140` 缩放 sample 和搜索区域。

### Feature Mask（背景排除）

sample 图标由深色圆形底 + 白色图案 + 灰色背景构成。
使用百分位阈值（22%/82%）自动提取图标特征区，生成 mask；
`cv2.matchTemplate(..., cv2.TM_CCOEFF_NORMED, mask=...)` 只匹配图标形状，灰色背景不参与计算。
使纹理背景下的匹配率保持 0.99+。

### 可调参数（脚本顶部常量）

| 参数 | 默认值 | 说明 |
|---|---|---|
| REF_CAPTURE_W/H | 1980/1140 | 参考截图尺寸 |
| REF_TOOLBAR_W | 60 | 右侧工具栏宽度 |
| REF_TITLEBAR_H | 60 | 上方标题栏高度 |
| REF_MARGIN_BOTTOM/RIGHT | 40 | 图标距游戏区下/右边距 |
| REF_BOTTOM_EXTRA | 13 | 搜索区域上移微调 |
| REF_RIGHT_TRIM | 60 | 搜索区域右侧缩进微调 |
| MATCH_THRESHOLD | 0.75 | 匹配成功阈值 |
| MASK_DARK_PERCENTILE | 22 | mask 深色区域百分位 |
| MASK_BRIGHT_PERCENTILE | 82 | mask 亮色区域百分位 |
| DRIVE_KMP / WALK_KMP | (见脚本) | .kmp 文件路径 |

## 工作原理（同 v4）

### 策略 v2（CFW 重定向）

Ctrl+F 切换按键时，LDPlayer 会读取 .kmp 文件：
1. 第 1 次读取：当前方案 — 不重定向
2. 第 2、3 次读取：下一个方案 — 重定向到目标方案的 .kmp 内容

**效果：** 内部索引记录下一个方案，但实际读取的内容是目标方案 → 实际键位为目标方案

### CALL hook

在 dnplycore.dll 中 `call setKeyboardConfig` 处安装 inline hook（E8→E9），替换参数为目标文件名。

### CFW hook

在 kernelbase.CreateFileW 处安装 inline hook，拦截 .kmp 文件读取并重定向。

## 编译方法

### 依赖

- Visual Studio 2022（MSVC 14.x）
- Windows SDK 10.x
- x86（32 位）目标（dnplayer.exe 是 32 位）

### 编译

```powershell
cd hook_demo
.\build.ps1
```

build.ps1 手动配置 INCLUDE/LIB/PATH 环境变量后调用 cl.exe/ml.exe/rc.exe。

## 已知限制

1. **提示不一致**：默认模式下模拟器内安卓系统弹出"切换到 BBB"但实际键位是 CCC。提示来自安卓系统，无法通过 Windows 层面修改。实际键位正确。
2. **杀毒软件报毒**：因使用 DLL 注入技术可能被 Defender 标记。建议添加排除文件夹或提交白名单。
3. **CFW hook 非线程安全**：使用"恢复-调用-重装"模式，多线程调用 CreateFileW 时可能出问题。
4. **国内版不兼容**：偏移已找到但 Ctrl+F 发送方式在国内版上不生效，用户已放弃。

## 版本历史

- v1: 初始版本，Ctrl+F 参数替换（失败）
- v2: CFW 重定向策略（LDPlayer9 海外版）
- v3: 多版本兼容（LDPlayer9 + LDPlayer14）
- **v4**: 预初始化 init 命令（backup_v4_preInit）
- **v5**: 🆕 集成 OpenCV 状态检测 + 自动切换（当前版本）
  - screenshot_ldplayer.py: dxcam 截图 + OpenCV 模板匹配
  - Feature mask 排除背景噪声
  - 循环监控 + 状态机自动切换按键方案
  - 红框/绿框调试标注图
  - 支持运行时窗口调整（动态 rect 获取）
