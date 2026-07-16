"""Plan B PoC — Direct SwitchKeymap call (no Ctrl+F, no ctypes Structure).

Simplified: uses raw p+offset for shared memory, avoids PROCESSENTRY32W alignment issues.
"""
import ctypes, json, os, sys, tempfile, shutil, subprocess
from ctypes import wintypes

# Paths
KMP_DIR = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\games\gtasa\keymaps"
DRIVE_KMP = os.path.join(KMP_DIR, "GTASA(Drive mode).kmp")
INJECTOR = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\dist\keymap_injector.exe"
RVA_CALL_SWITCH_KEYMAP = 0x01200

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def dword(p, offset=0):
    """Read DWORD at p+offset."""
    return ctypes.c_uint32.from_address(p + offset).value


def set_dword(p, offset, value):
    ctypes.c_uint32.from_address(p + offset).value = value


def write_str(p, offset, text, wide=False):
    """Write string to offset."""
    if wide:
        enc = text.encode("utf-16-le")
        sz = 2048
    else:
        enc = text.encode("ascii", errors="ignore")
        sz = 1024
    ctypes.memset(p + offset, 0, sz)
    ctypes.memmove(p + offset, enc, len(enc))


def find_pid(name="dnplayer.exe"):
    """Find process by name using tasklist."""
    r = subprocess.run(["tasklist", "/fi", f"IMAGENAME eq {name}", "/fo", "csv", "/nh"],
                       capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        if name.lower() in line.lower():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 2:
                try:
                    return int(parts[1].strip())
                except:
                    pass
    return 0


def find_dll_base(pid, modname="keymap_hook.dll"):
    """Enumerate modules using Toolhelp32. x64 offsets: base@24, name@48."""
    TH32CS_SNAPMODULE = 0x8 | 0x10
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    if snap == -1:
        return 0

    buf = ctypes.create_string_buffer(1080)
    ctypes.c_uint32.from_address(ctypes.addressof(buf)).value = 1080

    if kernel32.Module32FirstW(snap, buf):
        while True:
            base = ctypes.c_uint32.from_address(ctypes.addressof(buf) + 24).value
            name = ctypes.c_wchar_p(ctypes.addressof(buf) + 48).value
            if name and name.lower() == modname.lower():
                kernel32.CloseHandle(snap)
                return base
            ctypes.c_uint32.from_address(ctypes.addressof(buf)).value = 1080
            if not kernel32.Module32NextW(snap, buf):
                break

    kernel32.CloseHandle(snap)
    return 0


def modify_kmp(src, mods):
    """Modify .kmp JSON fields, return temp file path."""
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    for m in data.get("keyboardMappings", []):
        d = m.get("data", {})
        for key, (old, new) in mods.items():
            if key in d and d[key] == old:
                d[key] = new
                print(f"  {m['class']}.{key}: {old} → {new}")
    tmpdir = tempfile.mkdtemp(prefix="kmp_")
    tmp = os.path.join(tmpdir, os.path.basename(src))
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    return tmp


def main():
    print("=== Plan B PoC: Direct SwitchKeymap ===")

    # 1. Find process and DLL
    pid = find_pid()
    if not pid:
        print("ERROR: dnplayer.exe not running!")
        sys.exit(1)
    print(f"PID={pid}")

    dll_base = find_dll_base(pid)
    if not dll_base:
        print("ERROR: keymap_hook.dll not found in dnplayer!")
        sys.exit(1)
    print(f"DLL base=0x{dll_base:08X}")

    # 2. Open shared memory
    hMap = kernel32.OpenFileMappingW(0x000F001F, False, "LDKeymapSwitch_Mem")
    if not hMap:
        print("ERROR: Shared memory not found. DLL not injected.")
        sys.exit(1)
    p = kernel32.MapViewOfFile(hMap, 0x000F001F, 0, 0, 0)
    kernel32.CloseHandle(hMap)
    if not p:
        print("ERROR: MapViewOfFile failed")
        sys.exit(1)

    inst = dword(p, 0xC08)
    func = dword(p, 0xC0C)
    status = dword(p, 0xC10)
    hc = dword(p, 0xC14)
    print(f"  instance=0x{inst:08X} func=0x{func:08X} status=0x{status:X} hookCount={hc}")

    if not inst or not func:
        print("ERROR: CALL hook never fired. Prime it first with:")
        print(f"  {INJECTOR} \"{KMP_DIR}\\GTASA(walk mode).kmp\"")
        kernel32.UnmapViewOfFile(p)
        sys.exit(1)

    kernel32.UnmapViewOfFile(p)

    # 3. Modify keymap
    mods = {"leftKey": (65, 87), "upKey": (87, 65)}  # swap A↔W
    print(f"\n--- Modifying drive.kmp: A↔W swap ---")
    tmp = modify_kmp(DRIVE_KMP, mods)
    if not tmp:
        print("ERROR: modification failed")
        sys.exit(1)

    # 4. Write to shared memory
    p = kernel32.MapViewOfFile(hMap := kernel32.OpenFileMappingW(0x000F001F, False, "LDKeymapSwitch_Mem"),
                               0x000F001F, 0, 0, 0)
    kernel32.CloseHandle(hMap)

    basename = os.path.basename(DRIVE_KMP)
    write_str(p, 0x004, basename)           # targetPath (ANSI)
    write_str(p, 0x408, tmp, wide=True)     # fullPath (wide)
    set_dword(p, 0x404, 3)                   # modeFlags
    set_dword(p, 0x000, 0x4B4D5053)          # magic
    print(f"  targetPath={basename}")
    print(f"  fullPath={tmp}")

    kernel32.UnmapViewOfFile(p)

    # 5. Call SwitchKeymap
    print("\n--- Calling SwitchKeymap... ---")
    target = dll_base + RVA_CALL_SWITCH_KEYMAP
    print(f"  target=0x{target:08X}")

    hProc = kernel32.OpenProcess(0x1F0FFF, False, pid)
    if not hProc:
        print(f"OpenProcess failed: {ctypes.get_last_error()}")
        sys.exit(1)

    hThread = kernel32.CreateRemoteThread(hProc, None, 0, ctypes.c_void_p(target), None, 0, None)
    if not hThread:
        print(f"CreateRemoteThread failed: {ctypes.get_last_error()}")
        kernel32.CloseHandle(hProc)
        sys.exit(1)

    wr = kernel32.WaitForSingleObject(hThread, 5000)
    if wr == 0:
        ec = wintypes.DWORD()
        kernel32.GetExitCodeThread(hThread, ctypes.byref(ec))
        print(f"  ✓ SwitchKeymap returned {ec.value}")
    else:
        print(f"  ✗ WaitForSingleObject={wr}")

    kernel32.CloseHandle(hThread)
    kernel32.CloseHandle(hProc)

    # 6. Verify
    p = kernel32.MapViewOfFile(hMap := kernel32.OpenFileMappingW(0x000F001F, False, "LDKeymapSwitch_Mem"),
                               0x000F001F, 0, 0, 0)
    kernel32.CloseHandle(hMap)
    if p:
        print(f"\nPost-switch: hookCount={dword(p,0xC14)} cfwKmp={dword(p,0xC2C)} redirects={dword(p,0xC30)}")
        kernel32.UnmapViewOfFile(p)

    shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    print("\n✓ PoC complete!")
    print("  Verify: A key should now act as W (up), W should act as A (left) in GTASA.")


if __name__ == "__main__":
    main()
