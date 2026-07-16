# LDPlayer Auto Input Switcher

LDPlayer 模拟器按键方案自动切换工具。通过 OpenCV 模板匹配识别游戏内状态，自动切换对应的按键方案。

![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![License](https://img.shields.io/badge/License-LGPL%20v3-green)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![LDPlayer](https://img.shields.io/badge/LDPlayer-9%20%7C%2014%20(Overseas)-orange)

## 功能

- **自动检测** — OpenCV 模板匹配识别游戏状态（行走/驾驶/飞行等）
- **一键切换** — DLL 注入 + inline hook，无弹窗切换按键方案
- **系统托盘** — 后台静默运行，右键一键启停
- **多游戏支持** — 统一 `game.json` 配置，添加新游戏零代码改动
- **多语言** — 中文 / English，首次启动跟随系统语言
- **零配置启动** — PyInstaller 打包，解压即用，无需安装任何环境
- **无匹配状态处理** — 可选的"无匹配结果自动释放鼠标"（none_state）
- **KMP 自动同步** — 启动监控时自动将游戏按键文件复制到 LDPlayer 目录

## 快速开始

### 运行环境

- Windows 10/11
- LDPlayer 9 或 LDPlayer 14（海外版）
- 无需安装 Python / OpenCV / Visual Studio

### 使用步骤

1. 下载并解压发布包
2. 启动 LDPlayer，打开目标游戏
3. 双击 `AutoInputSwitcher.exe`
4. 主窗口自动显示（不隐藏到托盘）
5. 选择游戏 → 点 **启动监控**
6. 游戏状态变化时按键方案自动切换

### 首次使用

工具首次启动会自动：
- 检测系统语言（中文系统 → 中文，其他 → English）
- 扫描 `games/` 目录下所有游戏配置
- 自动检测 LDPlayer 安装路径和版本
- 启动监控时检查并同步 .kmp 文件

## 支持的游戏

| 游戏 | 状态 | 识别模式 |
|---|---|---|
| GTA: San Andreas | ✅ | 行走 / 驾驶 |
| Black Russia | 🔧 开发中 | — |
| CODM | 🔧 开发中 | — |

### 添加新游戏

参考 `games/_template/`，详见 [GAME_CONFIG.md](GAME_CONFIG.md)：

1. 复制 `games/_template/` → 重命名为 `games/<游戏名>/`
2. 编辑 `game.json`：name / package / states / regions / detection
3. 放入截图模板到 `templates/`
4. 导出 LDPlayer 按键方案 `.kmp` 到 `keymaps/`
5. 重新启动工具即可

## 目录结构

```
├── AutoInputSwitcher.exe    # 主程序（PyInstaller 打包）
├── dist/                    # C++ 预编译注入组件
│   ├── keymap_hook.dll      #   Hook DLL (x86)
│   └── keymap_injector.exe  #   注入器 (x86)
├── games/                   # 游戏数据（可独立更新，无需重新打包）
│   ├── gtasa/               #   GTA: San Andreas
│   ├── _template/           #   添加新游戏模板
│   └── ...
├── config/                  # 全局配置
│   ├── settings.json        #   用户设置
│   └── ldplayer_versions.json  # LDPlayer 版本偏移表
├── locales/                 # 翻译文件
│   ├── zh_CN.json
│   └── en_US.json
├── src/                     # 源码（Python + C++）
└── README.md
```

## 技术栈

| 层 | 技术 |
|---|---|
| GUI | PySide6 (Qt for Python) |
| 图像识别 | OpenCV (TM_CCOEFF_NORMED + feature mask) |
| 截图 | RenderWindow 子窗口 / dxcam ClientRect 回退 |
| 注入层 | C++ x86 DLL inject + inline CALL hook + CFW redirect |
| 打包 | PyInstaller --onefile |

## 常见问题

### 杀毒软件报警

DLL 注入技术可能被 Windows Defender 标记。将安装目录添加到 Defender 排除列表即可。

### 切换提示与实际按键不符

工具使用自定义 Toast 覆盖层显示切换信息，默认启用。可在设置中关闭。

### 如何获取 LDPlayer 的 .kmp 按键文件

在 LDPlayer 中手动设置好按键 → 进入 `安装路径/vms/customizeConfigs/` → 找到对应游戏的 `.kmp` 文件。

## 许可

LGPL v3
