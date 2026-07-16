"""
LDPlayer Keymap Switcher
========================
Researched and designed based on reverse engineering analysis of dnplycore.dll.

Key findings:
- CInputMgr::setKeyboardConfig applies a .kmp to the running VM
- IPC uses named pipes: ld-winpipe-read/write-{PID}
- IPC also uses shared memory (FileMapping) + semaphores
- Ctrl+F cycles through .kmp files in filename order (order set at startup)
- .smp files store per-app keymap selection (keyboardId field)

This tool provides multiple strategies to switch keymaps.
"""

import json
import os
import glob
import time
import sys
import ctypes
import ctypes.wintypes
from typing import Optional

# ── LDPlayer paths ─────────────────────────────────────────────
LDP_9_DIR = r"F:\leidian\LDPlayer9"
LDCONSOLE = os.path.join(LDP_9_DIR, "ldconsole.exe")
VMS_DIR = os.path.join(LDP_9_DIR, "vms")
CUSTOMIZE_CONFIGS = os.path.join(VMS_DIR, "customizeConfigs")
RECOMMEND_CONFIGS = os.path.join(VMS_DIR, "recommendConfigs")
CONFIG_DIR = os.path.join(VMS_DIR, "config")

# ── Helper: find LDPlayer window ───────────────────────────────

user32 = ctypes.windll.user32

def find_ldplayer_window() -> Optional[int]:
    """Find the LDPlayer main window handle."""
    target_hwnd = None
    
    def enum_cb(hwnd, lparam):
        nonlocal target_hwnd
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value == "LDPlayer":
            target_hwnd = hwnd
        return 1  # continue enumeration
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int)
    cb = WNDENUMPROC(enum_cb)
    user32.EnumWindows(cb, 0)
    return target_hwnd


# ── Strategy 1: SendInput (simulate Ctrl+F) ────────────────────

def send_key_combination(modifiers: int, key: int):
    """
    Send keyboard input using SendInput API.
    
    Args:
        modifiers: MOD_ALT=1, MOD_CONTROL=2, MOD_SHIFT=4, MOD_WIN=8
        key: Virtual key code (e.g., 0x46 for 'F')
    """
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    
    # Actually use KEYBDINPUT structure with WM_KEYDOWN simulation
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.wintypes.WORD),
                    ("wScan", ctypes.wintypes.WORD),
                    ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.c_void_p)]
    
    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]
    
    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong),
                    ("u", INPUT_UNION)]
    
    # Ctrl down
    ctrl_down = INPUT(INPUT_KEYBOARD)
    ctrl_down.u.ki = KEYBDINPUT(0x11, 0, 0, 0, 0)
    
    # F down
    f_down = INPUT(INPUT_KEYBOARD)
    f_down.u.ki = KEYBDINPUT(key, 0, 0, 0, 0)
    
    # F up
    f_up = INPUT(INPUT_KEYBOARD)
    f_up.u.ki = KEYBDINPUT(key, 0, KEYEVENTF_KEYUP, 0, 0)
    
    # Ctrl up
    ctrl_up = INPUT(INPUT_KEYBOARD)
    ctrl_up.u.ki = KEYBDINPUT(0x11, 0, KEYEVENTF_KEYUP, 0, 0)
    
    # Send all
    inputs = (INPUT * 4)(ctrl_down, f_down, f_up, ctrl_up)
    sent = user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    return sent


def switch_keymap_ctrlf_window(hwnd: int, presses: int = 1):
    """
    Strategy 1: Send Ctrl+F to LDPlayer window via SendInput.
    Cycles through keymaps in filename order.
    """
    # Bring window to foreground
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    
    for i in range(presses):
        send_key_combination(2, 0x46)  # Ctrl+F
        time.sleep(0.1)
    
    print(f"Sent Ctrl+F {presses} time(s)")


# ── Strategy 2: .smp modification + LDConsole app restart ─────

def list_available_keymaps(package_name: str) -> list:
    """
    List all .kmp files available for a given package.
    Scans both customizeConfigs and recommendConfigs.
    """
    kmp_files = []
    
    # Check customizeConfigs
    if os.path.exists(CUSTOMIZE_CONFIGS):
        for f in os.listdir(CUSTOMIZE_CONFIGS):
            if f.endswith(".kmp") and package_name in f:
                kmp_files.append(os.path.join(CUSTOMIZE_CONFIGS, f))
    
    # Check recommendConfigs
    if os.path.exists(RECOMMEND_CONFIGS):
        for f in os.listdir(RECOMMEND_CONFIGS):
            if f.endswith(".kmp") and package_name in f:
                kmp_files.append(os.path.join(RECOMMEND_CONFIGS, f))
    
    return sorted(kmp_files, key=lambda x: os.path.basename(x).lower())


def read_smp_config(package_name: str) -> Optional[dict]:
    """Read the .smp config for a given game package."""
    smp_path = os.path.join(CUSTOMIZE_CONFIGS, f"{package_name}.smp")
    if not os.path.exists(smp_path):
        print(f"No .smp found for {package_name}")
        return None
    
    try:
        with open(smp_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading .smp: {e}")
        return None


def write_smp_config(package_name: str, config: dict) -> bool:
    """Write the .smp config for a given game package."""
    smp_path = os.path.join(CUSTOMIZE_CONFIGS, f"{package_name}.smp")
    try:
        # Atomic write
        tmp = smp_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        os.replace(tmp, smp_path)
        return True
    except Exception as e:
        print(f"Error writing .smp: {e}")
        return False


def set_keyboard_id(package_name: str, resolution: str, kmp_filename: str) -> bool:
    """
    Modify the .smp file to point to a different .kmp file.
    
    Args:
        package_name: Android package name (e.g., "com.example.game")
        resolution: Resolution string (e.g., "1920x1080")
        kmp_filename: Target .kmp filename (e.g., "game_mode1.kmp")
    """
    config = read_smp_config(package_name)
    if not config:
        return False
    
    if "resolutionRelatives" not in config:
        print("Warning: No resolutionRelatives in .smp")
        return False
    
    if resolution not in config["resolutionRelatives"]:
        print(f"Warning: Resolution '{resolution}' not found in .smp")
        return False
    
    old_id = config["resolutionRelatives"][resolution].get("keyboardId", "")
    config["resolutionRelatives"][resolution]["keyboardId"] = kmp_filename
    
    if write_smp_config(package_name, config):
        print(f"Updated keyboardId: '{old_id}' -> '{kmp_filename}'")
        return True
    return False


def restart_app(package_name: str, vm_index: int = 0):
    """
    Restart an app in LDPlayer using ldconsole.
    This forces LDPlayer to re-read the .smp file and apply the new keymap.
    """
    import subprocess
    
    # Kill the app
    result = subprocess.run(
        [LDCONSOLE, "killapp", "--index", str(vm_index), "--packagename", package_name],
        capture_output=True, text=True, timeout=10
    )
    print(f"killapp: {result.stdout.strip()}")
    time.sleep(0.5)
    
    # Launch the app
    result = subprocess.run(
        [LDCONSOLE, "runapp", "--index", str(vm_index), "--packagename", package_name],
        capture_output=True, text=True, timeout=10
    )
    print(f"runapp: {result.stdout.strip()}")


# ── Strategy 3: DLL injection to call setKeyboardConfig (advanced) ──
# Note: This requires finding the actual address of 
#       vbox::CInputMgr::setKeyboardConfig at runtime
#       and the correct calling convention.

def strategy_inject_call_setkeyboardconfig():
    """
    Strategy 3: [Theoretical - requires further x32dbg analysis]
    
    Steps needed:
    1. Attach x32dbg to dnplayer.exe
    2. Breakpoint on ReadFile when .smp is read
    3. Trace back to the function that calls CInputMgr::setKeyboardConfig
    4. Get the function address in the loaded DLL
    5. Create a DLL that calls it with a new .kmp path
    6. Inject into dnplayer.exe
    
    This is the most direct approach but requires deeper RE work.
    """
    raise NotImplementedError(
        "DLL injection strategy requires finding setKeyboardConfig address in dnplycore.dll. "
        "Use x32dbg to: 1) Find the function at runtime, "
        "2) Create a DLL to call it, 3) Inject via CreateRemoteThread + LoadLibrary."
    )


# ── Strategy 4: Named pipe IPC (theoretical) ──────────────────

def strategy_named_pipe_ipc():
    """
    Strategy 4: [Theoretical - requires protocol RE]
    
    dnplycore.dll communicates with Ld9BoxHeadless via named pipes:
        \\.\pipe\ld-winpipe-read-{PID}
        \\.\pipe\ld-winpipe-write-{PID}
    
    If we can reverse the protocol (using CWinPipe::SendRaw pattern),
    we can send a command to reload/switch keymaps directly.
    
    Look for message types in the DLL:
    - Look at functions that call CWinPipe::SendRaw near setKeyboardConfig
    - Protocol is likely: [4-byte len][4-byte type][payload]
    """
    raise NotImplementedError(
        "Named pipe IPC requires protocol RE of CWinPipe::SendRaw/RecvRaw. "
        "Set breakpoints on WriteFile/ReadFile on the pipe handles."
    )


# ── Main ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LDPlayer Keymap Switcher")
    parser.add_argument("--package", help="Android package name")
    parser.add_argument("--kmp", help="Target .kmp filename to switch to")
    parser.add_argument("--resolution", default="1920x1080", 
                       help="Screen resolution (default: 1920x1080)")
    parser.add_argument("--vm-index", type=int, default=0,
                       help="VM index (default: 0)")
    parser.add_argument("--strategy", type=int, default=1,
                       help="Switching strategy: 1=SendInput, 2=RestartApp, 3=Inject (WIP)")
    parser.add_argument("--list-keymaps", action="store_true",
                       help="List available keymaps for a package")
    parser.add_argument("--read-smp", action="store_true",
                       help="Read current .smp config")
    parser.add_argument("--ctrl-f-count", type=int, default=1,
                       help="Number of Ctrl+F presses (strategy 1)")
    
    args = parser.parse_args()
    
    if args.list_keymaps and args.package:
        kmps = list_available_keymaps(args.package)
        print(f"Available keymaps for '{args.package}':")
        for i, k in enumerate(kmps):
            name = os.path.basename(k)
            print(f"  {i}: {name}")
        sys.exit(0)
    
    if args.read_smp and args.package:
        config = read_smp_config(args.package)
        if config:
            print(json.dumps(config, indent=2, ensure_ascii=False))
        sys.exit(0)
    
    if args.strategy == 1:
        # Strategy 1: SendInput Ctrl+F
        hwnd = find_ldplayer_window()
        if not hwnd:
            print("LDPlayer window not found!")
            sys.exit(1)
        print(f"Found LDPlayer window: HWND={hwnd}")
        switch_keymap_ctrlf_window(hwnd, args.ctrl_f_count)
        
    elif args.strategy == 2:
        # Strategy 2: Modify .smp + restart app
        if not args.package:
            print("--package is required for strategy 2")
            sys.exit(1)
        if args.kmp:
            set_keyboard_id(args.package, args.resolution, args.kmp)
        restart_app(args.package, args.vm_index)
        
    else:
        print(f"Strategy {args.strategy} not implemented yet")
