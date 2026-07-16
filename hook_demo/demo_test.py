"""
LDPlayer Keymap Switch - Demo test script
==========================================
Flow:
1. Modifies the .smp file's keyboardId
2. Sets the target .kmp in shared memory for the hook DLL
3. Sends Ctrl+F to trigger switching

Requirements:
- keymap_hook.dll injected into dnplayer.exe
- LDPlayer running with a game open
"""

import os
import json
import subprocess
import sys
import ctypes
import time

# ── Paths ──────────────────────────────────────────────────
LDP9_DIR = r"F:\leidian\LDPlayer9"
CUSTOMIZE_CONFIGS = os.path.join(LDP9_DIR, "vms", "customizeConfigs")
RECOMMEND_CONFIGS = os.path.join(LDP9_DIR, "vms", "recommendConfigs")
INJECTOR_PATH = os.path.join(os.path.dirname(__file__), "keymap_injector.exe")
HOOK_DLL_PATH = os.path.join(os.path.dirname(__file__), "keymap_hook.dll")

def find_smp_for_game(game_package: str) -> str:
    """Find the .smp file for a given game package."""
    path = os.path.join(CUSTOMIZE_CONFIGS, f"{game_package}.smp")
    if os.path.exists(path):
        return path
    # Search for partial match
    for f in os.listdir(CUSTOMIZE_CONFIGS):
        if f.endswith(".smp") and game_package in f:
            return os.path.join(CUSTOMIZE_CONFIGS, f)
    return None

def read_smp(smp_path: str) -> dict:
    with open(smp_path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_smp(smp_path: str, config: dict):
    tmp = smp_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    os.replace(tmp, smp_path)

def set_keyboard_id(smp_path: str, resolution: str, kmp_name: str) -> bool:
    """Modify the keyboardId in .smp to the target kmp."""
    config = read_smp(smp_path)
    if resolution not in config.get("resolutionRelatives", {}):
        # Use first available resolution
        resolution = list(config["resolutionRelatives"].keys())[0]
    old_id = config["resolutionRelatives"][resolution].get("keyboardId", "")
    config["resolutionRelatives"][resolution]["keyboardId"] = kmp_name
    write_smp(smp_path, config)
    print(f"[OK] keyboardId: '{old_id}' -> '{kmp_name}'")
    return True

def inject_and_trigger(kmp_path: str) -> bool:
    """Inject DLL and set the target .kmp path."""
    if not os.path.exists(INJECTOR_PATH):
        print(f"[ERR] Injector not found: {INJECTOR_PATH}")
        return False
    
    if not os.path.exists(kmp_path):
        print(f"[ERR] .kmp file not found: {kmp_path}")
        return False
    
    result = subprocess.run([INJECTOR_PATH, kmp_path], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"[ERR] Injection failed: {result.stderr}")
        return False
    return True

def user_send_ctrl_f():
    """Prompt user to press Ctrl+F."""
    input("\n🔔 Press Ctrl+F in LDPlayer now, then press Enter to continue...")

def list_games():
    """List available game configs."""
    print("Available games:")
    for f in sorted(os.listdir(CUSTOMIZE_CONFIGS)):
        if f.endswith(".smp"):
            name = f[:-4]
            print(f"  {name}")

def list_keymaps(game_package: str):
    """List available .kmp files for a game."""
    kmps = []
    for d in [CUSTOMIZE_CONFIGS, RECOMMEND_CONFIGS]:
        for f in os.listdir(d):
            if f.endswith(".kmp") and (game_package in f):
                kmps.append(os.path.join(d, f))
    kmps.sort()
    print(f"Keymaps for '{game_package}':")
    for i, k in enumerate(kmps):
        print(f"  {i}: {os.path.basename(k)}")
    return kmps

# ── Main ───────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("LDPlayer Keymap Switch Demo")
    print("=" * 60)
    
    # Step 1: List games
    list_games()
    
    # Step 2: Select game
    game = input("\nEnter game package name (e.g., com.activision.callofduty.shooter): ").strip()
    
    smp_path = find_smp_for_game(game)
    if not smp_path:
        print(f"[ERR] No .smp found for '{game}'")
        sys.exit(1)
    print(f"[OK] Found .smp: {smp_path}")
    
    # Step 3: Read current config
    config = read_smp(smp_path)
    res = list(config["resolutionRelatives"].keys())[0]
    print(f"[OK] Resolution: {res}")
    print(f"[OK] Current keyboardId: {config['resolutionRelatives'][res].get('keyboardId', '')}")
    
    # Step 4: List available keymaps
    kmps = list_keymaps(game)
    if not kmps:
        print("[WARN] No .kmp files found. Create one first in LDPlayer keymapping UI.")
        sys.exit(1)
    
    # Step 5: Select target keymap
    choice = input("\nSelect target keymap number (or 'q' to quit): ").strip()
    if choice.lower() == 'q':
        sys.exit(0)
    
    try:
        idx = int(choice)
        target_kmp = kmps[idx]
    except:
        print("[ERR] Invalid choice")
        sys.exit(1)
    
    kmp_name = os.path.basename(target_kmp)
    print(f"\nTarget: {target_kmp}")
    
    # Step 6: Update .smp
    set_keyboard_id(smp_path, res, kmp_name)
    
    # Step 7: Inject and set target
    inject_and_trigger(target_kmp)
    
    # Step 8: Prompt user to press Ctrl+F
    print("\n" + "-" * 60)
    print("LDPlayer will now read the .kmp file when you press Ctrl+F.")
    print("The hook DLL will redirect the .kmp read to your target file.")
    print("-" * 60)
    
    user_send_ctrl_f()
    
    print("\n[Done] Check if the keymap switched successfully.")
    print("If it did, the approach works! Now we can refine to call")
    print("setKeyboardConfig directly (no Ctrl+F needed).")
