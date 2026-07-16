"""Verify --gui switch: dump CInputMgr before and after switch, compare.

If the --gui switch actually applies the keymap via pipe I/O,
the CInputMgr internal state should change.
"""
import ctypes, struct, subprocess, time, sys, os

DNPLYCORE_BASE = 0x79C10000
SAVED_INSTANCE = 0x07858620
INJECTOR = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\dist\keymap_injector.exe"
WALK_KMP = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\games\gtasa\keymaps\GTASA(walk mode).kmp"
DRIVE_KMP = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\games\gtasa\keymaps\GTASA(Drive mode).kmp"

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

def find_pid():
    r = subprocess.run(["tasklist", "/fi", "IMAGENAME eq dnplayer.exe", "/fo", "csv", "/nh"],
                       capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        if "dnplayer.exe" in line.lower():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 2:
                return int(parts[1].strip())
    return 0

def read_mem(hProc, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
    return buf.raw[:br.value] if ok else b""

def dump_cinputmgr(label, hProc):
    data = read_mem(hProc, SAVED_INSTANCE, 512)
    print(f"\n--- {label} ---")
    if not data:
        print("  [read failed]")
        return None
    # Show first 256 bytes with DWORD annotations
    changed_fields = []
    for row in range(0, 256, 16):
        addr = SAVED_INSTANCE + row
        line = data[row:row+16]
        hx = " ".join(f"{b:02X}" for b in line)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in line)
        print(f"  +0x{row:03X}: {hx:48s} |{asc}|")
    return data

def dump_diff(before, after, label=""):
    if not before or not after:
        print(f"\n[{label}] Cannot diff - missing data")
        return
    print(f"\n=== DIFF: {label} ===")
    changes = 0
    for i in range(0, min(len(before), len(after)), 4):
        old = struct.unpack("<I", before[i:i+4])[0] if i+4 <= len(before) else 0
        new = struct.unpack("<I", after[i:i+4])[0] if i+4 <= len(after) else 0
        if old != new:
            print(f"  +0x{i:03X}: 0x{old:08X} -> 0x{new:08X}")
            changes += 1
    if changes == 0:
        print("  [NO CHANGES]")
    else:
        print(f"  Total: {changes} DWORD(s) changed")

pid = find_pid()
print(f"PID: {pid}")
hProc = kernel32.OpenProcess(0x10, False, pid)
assert hProc

# 1. Dump BEFORE
before = dump_cinputmgr("BEFORE --gui switch (current state)", hProc)

# 2. Run --gui switch to Drive mode
print(f"\n>>> Running: keymap_injector.exe --gui Drive mode")
result = subprocess.run([INJECTOR, "--gui", DRIVE_KMP], capture_output=True, text=True, timeout=15)
print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)

time.sleep(1)

# 3. Dump AFTER
after = dump_cinputmgr("AFTER --gui switch to Drive mode", hProc)

# 4. Diff
dump_diff(before, after, "Drive mode switch")

# 5. Switch back to walk mode
print(f"\n>>> Running: keymap_injector.exe --gui Walk mode")
result = subprocess.run([INJECTOR, "--gui", WALK_KMP], capture_output=True, text=True, timeout=15)
print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)

time.sleep(1)

after2 = dump_cinputmgr("AFTER --gui switch back to Walk mode", hProc)
dump_diff(after, after2, "Walk mode switch back")

kernel32.CloseHandle(hProc)
