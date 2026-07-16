# LDPlayer Auto Input Switcher

> *[中文版](README_zh_CN.md)*

Automatically switch LDPlayer emulator keymap schemes based on in-game state detection via OpenCV template matching.

![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![License](https://img.shields.io/badge/License-LGPL%20v3-green)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![LDPlayer](https://img.shields.io/badge/LDPlayer-9%20%7C%2014%20(Overseas)-orange)

## Features

- **Auto Detection** — OpenCV template matching recognizes game states (walking/driving/flying, etc.)
- **Seamless Switching** — DLL injection + inline hook, switches keymaps without any popups
- **System Tray** — Runs silently in background, right-click to start/stop
- **Multi-Game Support** — Unified `game.json` config; add new games with zero code changes
- **Multi-Language** — Chinese / English, auto-detects system language on first launch
- **Zero Setup** — PyInstaller single-file EXE, unzip and run, no environment required
- **No-Match Handling** — Optional "release mouse on no match" (none_state)
- **KMP Auto-Sync** — Automatically copies game keymap files to LDPlayer directory on start

## Quick Start

### Requirements

- Windows 10/11
- LDPlayer 9 or LDPlayer 14 (Overseas version)
- No Python / OpenCV / Visual Studio installation needed

### Usage

1. Download and extract the release package
2. Launch LDPlayer and open your game
3. Double-click `AutoInputSwitcher.exe`
4. Select a game → click **Start Monitor**
5. Keymap schemes switch automatically as game state changes

### First Launch

The tool automatically:
- Detects system language (Chinese → zh_CN, others → en_US)
- Scans `games/` directory for all game configurations
- Auto-detects LDPlayer installation path and version
- Checks and syncs .kmp files when starting the monitor

## Supported Games

| Game | Status | Detection Modes |
|---|---|---|
| GTA: San Andreas | ✅ | Walk / Drive |
| Black Russia | ✅ | Walk / Drive |
| CODM | ✅ | Walk / Drive |

### Adding New Games

See `games/_template/` and [GAME_CONFIG.md](GAME_CONFIG.md):

1. Copy `games/_template/` → rename to `games/<game_name>/`
2. Edit `game.json`: name / package / states / regions / detection
3. Place screenshot templates in `templates/`
4. Export LDPlayer keymap `.kmp` files to `keymaps/`
5. Restart the tool

## Directory Structure

```
├── AutoInputSwitcher.exe    # Main program (PyInstaller)
├── dist/                    # Pre-compiled C++ injection components
│   ├── keymap_hook.dll      #   Hook DLL (x86)
│   └── keymap_injector.exe  #   Injector (x86)
├── games/                   # Game data (updatable without re-packaging)
│   ├── gtasa/               #   GTA: San Andreas
│   ├── _template/           #   Template for new games
│   └── ...
├── config/                  # Global configuration
│   ├── settings.json        #   User settings
│   └── ldplayer_versions.json  # LDPlayer version offset table
├── locales/                 # Translations
│   ├── zh_CN.json
│   └── en_US.json
├── src/                     # Source code (Python + C++)
└── README.md
```

## Tech Stack

| Layer | Technology |
|---|---|
| GUI | PySide6 (Qt for Python) |
| Image Recognition | OpenCV (TM_CCOEFF_NORMED + feature mask) |
| Screen Capture | RenderWindow child window / dxcam ClientRect fallback |
| Injection | C++ x86 DLL inject + inline CALL hook + CFW redirect |
| Packaging | PyInstaller --onefile |

## FAQ

### Antivirus warnings

DLL injection techniques may be flagged by Windows Defender. Add the install directory to Defender's exclusion list.

### Toast shows wrong keymap name

The tool uses a custom semi-transparent Toast overlay for status notifications, enabled by default. Can be disabled in Settings.

### How to get .kmp keymap files from LDPlayer

Set up your keymap in LDPlayer → go to `<LDPlayer path>/vms/customizeConfigs/` → find the `.kmp` file for your game.

## License

LGPL v3
