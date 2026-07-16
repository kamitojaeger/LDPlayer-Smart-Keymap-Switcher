# 开发者指南

> *[English](DEV_GUIDE.md)*

## 项目结构

```
LDPlayer_Auto_Input_Switcher/
├── main.py                         # 入口：GUI + CLI 双模式
├── requirements.txt                # Python 依赖
├── src/
│   ├── core/                       # C++ x86 注入核心
│   │   ├── keymap_hook.cpp         #   Hook DLL 源码
│   │   ├── keymap_injector.cpp     #   注入器源码
│   │   ├── hook_stub.asm           #   CALL hook 汇编跳板
│   │   ├── version.rc              #   版本资源
│   │   ├── build.bat / build.ps1   #   编译脚本
│   ├── detector/                   # Python 检测引擎
│   │   ├── capture.py              #   截图 (dxcam + RenderWindow)
│   │   ├── matcher.py              #   OpenCV 模板匹配 + feature mask
│   │   ├── state_machine.py        #   状态机 + 去抖
│   │   ├── overlay.py              #   Toast 覆盖层
│   │   └── monitor.py              #   监控主循环 + MonitorThread(QThread)
│   ├── gui/                        # PySide6 图形界面
│   │   ├── app.py                  #   QApplication + 单例
│   │   ├── main_window.py          #   主窗口
│   │   ├── game_panel.py           #   游戏面板
│   │   ├── system_tray.py          #   系统托盘
│   │   ├── settings_dialog.py      #   设置对话框
│   │   └── about_dialog.py         #   关于对话框
│   └── shared/                     # 共享工具
│       ├── config.py               #   GameConfig + AppSettings
│       ├── ldplayer.py             #   LDPlayer 检测
│       ├── injector.py             #   Injector 封装
│       └── i18n.py                 #   多语言
├── games/                          # 游戏数据 (纯数据，无代码)
│   ├── gtasa/                      #   GTA: San Andreas
│   │   ├── game.json               #     游戏配置
│   │   ├── templates/              #     模板截图
│   │   └── keymaps/                #     按键方案 .kmp
│   └── _template/                  #   新游戏模板
├── config/                         # 全局配置
│   ├── settings.json               #   用户设置
│   └── ldplayer_versions.json      #   版本偏移表
├── dist/                           # C++ 编译产物 (随发布包)
├── locales/                        # 翻译文件
│   ├── zh_CN.json
│   └── en_US.json
├── docs/                           # 本文档
└── scripts/                        # 辅助脚本
    └── templateDebugger.py         #   模板匹配调试工具
```

## 模块职责

### 检测引擎 (`src/detector/`)

| 模块 | 职责 |
|---|---|
| `capture.py` | 枚举 LDPlayer 窗口，获取 RenderWindow 或 ClientRect 截图区域，dxcam 捕获 |
| `matcher.py` | OpenCV 模板匹配 + feature mask 生成，支持多模板批量匹配 |
| `state_machine.py` | 状态机，N 帧去抖，仅在连续相同状态时触发切换 |
| `overlay.py` | 自定义 Toast，显示切换提示 |
| `monitor.py` | 监控主循环，串联上述模块；MonitorThread(QThread) 驱动 GUI |

### 数据流

```
用户点击"启动" → MonitorThread.start()
  → 每 333ms: capture.py 截图
  → matcher.py: 模板匹配
  → state_machine.py: 去抖 + 变化检测
  → 若变化: injector.py 调用 keymap_injector.exe
  → 发送 mouse_drag_key (如需要)
  → 信号 → GUI 更新
```

## 如何添加新游戏

1. **复制模板**
   ```bash
   cp -r games/_template games/my_game
   ```

2. **编辑 `game.json`**
   ```json
   {
     "name": "My Game",
     "package": "com.example.mygame",
     "states": [
       {"id": "state_a", "name": "状态A", "template": "templates/state_a.png",
        "keymap": "keymaps/state_a.kmp", "mouse_drag_key": null},
       {"id": "state_b", "name": "状态B", "template": "templates/state_b.png",
        "keymap": "keymaps/state_b.kmp", "mouse_drag_key": 17}
     ]
   }
   ```

3. **准备素材**
   - 截取游戏内各状态的代表性图标，存入 `templates/`
   - 从 LDPlayer 导出对应按键方案 `.kmp`，存入 `keymaps/`

4. **验证**
   ```bash
   python main.py --cli --game my_game
   ```
   确保各状态匹配率 > 0.75。

5. **模板截图建议**
   - 选择独特、不随游戏内容变化的 UI 元素（如右下角状态图标）
   - PNG 格式，约 180×178 像素
   - 分辨率与游戏设置一致

## 编译 C++ 组件

需要 Visual Studio 2022 Community + Windows SDK 10.x。

```bash
# 在 src/core/ 目录下
build.bat
```

产物：`keymap_hook.dll` + `keymap_injector.exe`（均为 x86）。

手动复制到 `dist/`。

## 配置格式

详见 [GAME_CONFIG.md](../GAME_CONFIG.md)。

## 注意事项

1. **C++ 编译目标必须为 x86**：dnplayer.exe 是 32 位进程
2. **仅支持 LDPlayer 海外版** (9 / 14)：国内版 Ctrl+F 机制不同
3. **CFW hook 非线程安全**：当前使用"恢复-调用-重装"模式
