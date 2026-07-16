"""Plan B — Full heap diff: load walk vs drive, find changed memory pages.

Strategy: hash every committed MEM_PRIVATE page, compare before/after keymap switch.
"""
import ctypes, struct, hashlib, subprocess, time, sys
from ctypes import wintypes

INJECTOR = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\dist\keymap_injector.exe"
WALK = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\games\gtasa\keymaps\GTASA(walk mode).kmp"
DRIVE = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\games\gtasa\keymaps\GTASA(Drive mode).kmp"

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_SIZE = 4096

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD), ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD), ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD),
    ]


def find_pid():
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if snap == -1: return 0
    class PE(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_ulonglong),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260),
        ]
    pe = PE(); pe.dwSize = ctypes.sizeof(PE)
    pid = 0
    if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
        while True:
            if pe.szExeFile.lower() == "dnplayer.exe": pid = pe.th32ProcessID; break
            if not kernel32.Process32NextW(snap, ctypes.byref(pe)): break
    kernel32.CloseHandle(snap)
    return pid


def snapshot_heap(pid):
    """Hash every committed MEM_PRIVATE page. Returns {base_addr: md5_hex}."""
    h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h: raise OSError(f"OpenProcess({pid}) failed")
    
    pages = {}
    addr = 0
    region_count = 0
    total_kb = 0
    
    while True:
        mbi = MEMORY_BASIC_INFORMATION()
        if not kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        protect = mbi.Protect
        
        # Only committed private memory (heap)
        if (mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and
            protect not in (0x01, 0x100, 0x80) and  # skip PAGE_NOACCESS, PAGE_GUARD, PAGE_EXECUTE_WRITECOPY
            size >= PAGE_SIZE):
            
            region_count += 1
            # Hash each 4KB page in this region
            for offset in range(0, size, PAGE_SIZE):
                page_addr = base + offset
                buf = ctypes.create_string_buffer(PAGE_SIZE)
                br = ctypes.c_size_t(0)
                if kernel32.ReadProcessMemory(h, ctypes.c_void_p(page_addr), buf, PAGE_SIZE, ctypes.byref(br)):
                    total_kb += br.value // 1024
                    md5 = hashlib.md5(buf.raw[:br.value]).hexdigest()
                    pages[page_addr] = md5
                else:
                    # Page not fully readable, skip
                    pass
        
        addr = base + size
    
    kernel32.CloseHandle(h)
    print(f"  Snapshot: {region_count} regions, {len(pages)} pages ({total_kb//1024} MB)")
    return pages


def diff_snapshots(snap_a, snap_b):
    """Find pages whose hash changed between two snapshots."""
    changed = []
    all_addrs = set(snap_a.keys()) | set(snap_b.keys())
    
    for addr in sorted(all_addrs):
        ha = snap_a.get(addr, "")
        hb = snap_b.get(addr, "")
        if ha != hb:
            changed.append(addr)
    
    return changed


def load_keymap(kmp_path):
    """Load a .kmp via injector default mode."""
    r = subprocess.run([INJECTOR, kmp_path], capture_output=True, text=True)
    return "SUCCESS" in r.stdout


def main():
    pid = find_pid()
    if not pid: print("ERROR: dnplayer not running!"); return 1
    print(f"PID={pid}")
    
    # Step 1: Load walk mode and snapshot
    print("\n--- Loading WALK mode ---")
    load_keymap(WALK)
    time.sleep(0.5)
    
    print("Snapshot A (walk)...")
    snap_a = snapshot_heap(pid)
    
    # Step 2: Load drive mode and snapshot
    print("\n--- Loading DRIVE mode ---")
    load_keymap(DRIVE)
    time.sleep(0.5)
    
    print("Snapshot B (drive)...")
    snap_b = snapshot_heap(pid)
    
    # Step 3: Diff
    print(f"\n--- Diffing {len(snap_a)} vs {len(snap_b)} pages ---")
    changed = diff_snapshots(snap_a, snap_b)
    
    # Filter noise: skip pages that change all the time (timer, network, etc.)
    # A typical keymap switch should change 10-100 pages at most
    print(f"Changed pages: {len(changed)}")
    
    if len(changed) > 500:
        print("Too many changed pages (>500), likely includes runtime noise.")
        print("Re-running with focused diff...")
        # Second pass: re-snapshot walk, re-snapshot drive, only keep intersection
        load_keymap(WALK); time.sleep(0.3)
        snap_a2 = snapshot_heap(pid)
        load_keymap(DRIVE); time.sleep(0.3)
        snap_b2 = snapshot_heap(pid)
        changed2 = set(diff_snapshots(snap_a, snap_b))
        changed3 = set(diff_snapshots(snap_a2, snap_b2))
        changed = list(changed2 & changed3)  # intersection = consistent changes
        print(f"After intersection: {len(changed)} consistently changed pages")
    
    if not changed:
        print("\nNO changed pages found! The keymap data might be:")
        print("  - In MEM_IMAGE (code section) — handled by setKeyboardConfig internally")
        print("  - In MEM_MAPPED (file mapping) — not private memory")
        print("  - The switch might not have applied (check game behavior)")
        return 1
    
    # Step 4: Show details of changed pages
    print(f"\n{'='*70}")
    print(f"Consistently changed pages ({len(changed)}):")
    print(f"{'='*70}")
    
    h = kernel32.OpenProcess(PROCESS_VM_READ, False, pid)
    
    for addr in changed[:30]:  # show first 30
        # Read page content
        buf = ctypes.create_string_buffer(PAGE_SIZE)
        br = ctypes.c_size_t(0)
        kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, PAGE_SIZE, ctypes.byref(br))
        data = buf.raw[:br.value]
        
        # Show first 128 bytes as hex
        hex_str = " ".join(f"{b:02X}" for b in data[:64])
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data[:64])
        print(f"\n  0x{addr:08X}:")
        print(f"    {hex_str}")
        print(f"    {ascii_str}")
        
        # Check for JSON-like content
        try:
            text = data[:128].decode("ascii", errors="ignore")
            if "keyboard" in text.lower() or "keyMapping" in text or '{' in text:
                print(f"    *** JSON/STRUCT candidate!")
        except:
            pass
    
    kernel32.CloseHandle(h)
    
    # Step 5: Look for structured data patterns
    print(f"\n{'='*70}")
    print("Analyzing changed pages for int32 arrays (potential keymap structs)...")
    print(f"{'='*70}")
    
    h = kernel32.OpenProcess(PROCESS_VM_READ, False, pid)
    for addr in changed[:10]:
        buf = ctypes.create_string_buffer(PAGE_SIZE)
        kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, PAGE_SIZE, ctypes.byref(buf))
        data = buf.raw
        
        # Look for sequences of small positive integers (like virtual key codes)
        ints = struct.unpack(f"<{len(data)//4}I", data[:len(data)//4*4])
        
        # Find sequences of values that look like key codes (0-255) or coordinates
        key_like = [i for i in range(len(ints)) if 0 < ints[i] < 256]
        coord_like = [i for i in range(len(ints)) if 100 < ints[i] < 20000]
        
        if len(key_like) > 3 or len(coord_like) > 2:
            print(f"\n  0x{addr:08X}: {len(key_like)} key-like values, {len(coord_like)} coord-like values")
            # Show context around the first few key-like values
            for ki in key_like[:5]:
                start = max(0, ki - 4)
                end = min(len(ints), ki + 8)
                vals = ints[start:end]
                print(f"    @+{ki*4:04X}: {vals}")
    
    kernel32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
