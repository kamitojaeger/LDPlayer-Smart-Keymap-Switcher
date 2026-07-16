# Developer Guide

> *[中文版](DEV_GUIDE_zh_CN.md)*

## Project Structure

```
LDPlayer_Auto_Input_Switcher/
├── main.py                         # Entry point: GUI + CLI dual mode
├── requirements.txt                # Python dependencies
├── src/
│   ├── core/                       # C++ x86 injection core
│   │   ├── keymap_hook.cpp         #   Hook DLL source
│   │   ├── keymap_injector.cpp     #   Injector source
│   │   ├── hook_stub.asm           #   CALL hook assembly trampoline
│   │   ├── version.rc              #   Version resource
│   │   ├── build.bat / build.ps1   #   Build scripts
│   ├── detector/                   # Python detection engine
│   │   ├── capture.py              #   Screen capture (dxcam + RenderWindow)
│   │   ├── matcher.py              #   OpenCV template matching + feature mask
│   │   ├── state_machine.py        #   State machine + debounce
│   │   ├── overlay.py              #   Toast overlay
│   │   └── monitor.py              #   Main monitoring loop + MonitorThread (QThread)
│   ├── gui/                        # PySide6 GUI
│   │   ├── app.py                  #   QApplication + singleton
│   │   ├── main_window.py          #   Main window
│   │   ├── game_panel.py           #   Game panel
│   │   ├── system_tray.py          #   System tray
│   │   ├── settings_dialog.py      #   Settings dialog
│   │   └── about_dialog.py         #   About dialog
│   └── shared/                     # Shared utilities
│       ├── config.py               #   GameConfig + AppSettings
│       ├── ldplayer.py             #   LDPlayer detection
│       ├── injector.py             #   Injector wrapper
│       └── i18n.py                 #   Internationalization
├── games/                          # Game data (pure data, no code)
│   ├── gtasa/                      #   GTA: San Andreas
│   │   ├── game.json               #      Game config
│   │   ├── templates/              #      Template screenshots
│   │   └── keymaps/                #      Keymap .kmp files
│   └── _template/                  #   New game template
├── config/                         # Global configuration
│   ├── settings.json               #   User settings
│   └── ldplayer_versions.json      #   Version offset table
├── dist/                           # Pre-compiled C++ (shipped with releases)
├── locales/                        # Translation files
│   ├── zh_CN.json
│   └── en_US.json
├── docs/                           # Documentation
└── scripts/                        # Utility scripts
    └── templateDebugger.py         #   Template matching debug tool
```

## Module Responsibilities

### Detection Engine (`src/detector/`)

| Module | Responsibility |
|---|---|
| `capture.py` | Enumerate LDPlayer windows, locate RenderWindow or ClientRect capture region, dxcam capture |
| `matcher.py` | OpenCV template matching + feature mask generation, supports multi-template batch matching |
| `state_machine.py` | State machine, N-frame debounce, triggers switch only on consecutive identical states |
| `overlay.py` | Custom Toast overlay for switch notifications |
| `monitor.py` | Main monitoring loop, orchestrates above modules; MonitorThread(QThread) drives GUI updates |

### Data Flow

```
User clicks "Start" → MonitorThread.start()
  → Every 333ms: capture.py screenshot
  → matcher.py: template matching
  → state_machine.py: debounce + change detection
  → If changed: injector.py invokes keymap_injector.exe
  → Send mouse_drag_key (if needed)
  → Signal → GUI update
```

## Adding a New Game

1. **Copy template**
   ```bash
   cp -r games/_template games/my_game
   ```

2. **Edit `game.json`**
   ```json
   {
     "name": "My Game",
     "package": "com.example.mygame",
     "states": [
       {"id": "state_a", "name": "State A", "template": "templates/state_a.png",
        "keymap": "keymaps/state_a.kmp", "mouse_drag_key": null},
       {"id": "state_b", "name": "State B", "template": "templates/state_b.png",
        "keymap": "keymaps/state_b.kmp", "mouse_drag_key": 17}
     ]
   }
   ```

3. **Prepare assets**
   - Capture representative UI elements for each game state, save to `templates/`
   - Export corresponding keymap `.kmp` from LDPlayer, save to `keymaps/`

4. **Verify**
   ```bash
   python main.py --cli --game my_game
   ```
   Ensure match rates > 0.75 for all states.

5. **Screenshot tips**
   - Choose distinctive UI elements that don't change with game content (e.g., bottom-right status icons)
   - PNG format, approximately 180×178 pixels
   - Resolution matching game settings

## Building C++ Components

Requires Visual Studio 2022 Community + Windows SDK 10.x.

```bash
# From src/core/ directory
build.bat
```

Output: `keymap_hook.dll` + `keymap_injector.exe` (both x86).

Copy them to `dist/` manually.

## Config Format

See [GAME_CONFIG.md](../GAME_CONFIG.md).

## Important Notes

1. **C++ build target must be x86**: dnplayer.exe is a 32-bit process
2. **LDPlayer Overseas only** (9 / 14): The domestic version has a different Ctrl+F mechanism
3. **CFW hook is not thread-safe**: Currently uses "restore-call-reinstall" pattern
