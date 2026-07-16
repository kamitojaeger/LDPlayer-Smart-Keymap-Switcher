"""Plan B — Deep pointer chase from CInputMgr savedInstance.

Build a complete object graph by following all valid heap pointers
recursively. Then compare walk vs drive to find the keymap data.
"""
import ctypes, struct, hashlib, subprocess, time, sys
from ctypes import wintypes

INJECTOR = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\dist\keymap_injector.exe"
WALK = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\games\gtasa\keymaps\GTASA(walk mode).kmp"
DRIVE = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\games\gtasa\keymaps\GTASA(Drive mode).kmp"

PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000

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

def get_saved_instance(pid):
    """Read savedInstance from shared memory."""
    hMap = kernel32.OpenFileMappingW(0x0004, False, "LDKeymapSwitch_Mem")
    if not hMap: return 0
    p = kernel32.MapViewOfFile(hMap, 0x0004, 0, 0, 0)
    kernel32.CloseHandle(hMap)
    if not p: return 0
    inst = ctypes.c_uint32.from_address(p + 0xC08).value
    kernel32.UnmapViewOfFile(p)
    return inst

class HeapExplorer:
    def __init__(self, pid):
        self.pid = pid
        self.h = kernel32.OpenProcess(PROCESS_VM_READ, False, pid)
        assert self.h
        
        # Cache valid heap regions for fast pointer validation
        self.heap_regions = []
        self._cache_heap_regions()
    
    def _cache_heap_regions(self):
        addr = 0
        while True:
            mbi = MEMORY_BASIC_INFORMATION()
            if not kernel32.VirtualQueryEx(self.h, ctypes.c_void_p(addr),
                                           ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            if (mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and
                mbi.RegionSize >= 16 and mbi.Protect not in (0x01, 0x100)):
                self.heap_regions.append((mbi.BaseAddress, mbi.RegionSize))
            addr = mbi.BaseAddress + mbi.RegionSize
    
    def is_valid_heap_ptr(self, addr):
        """Check if addr points to readable committed private memory."""
        if addr < 0x03000000 or addr > 0x21000000:
            return False
        # Binary search in cached regions
        lo, hi = 0, len(self.heap_regions) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            base, size = self.heap_regions[mid]
            if addr < base:
                hi = mid - 1
            elif addr >= base + size:
                lo = mid + 1
            else:
                return True
        return False
    
    def read(self, addr, size):
        buf = ctypes.create_string_buffer(size)
        br = ctypes.c_size_t(0)
        kernel32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
        return buf.raw[:br.value]
    
    def chase_pointers(self, root_addr, max_depth=5, max_objects=5000):
        """Recursively follow all heap pointers from root_addr.
        Returns dict {addr: (size, md5_hash)} for all found objects."""
        visited = {}
        queue = [(root_addr, 0)]  # (addr, depth)
        
        while queue and len(visited) < max_objects:
            addr, depth = queue.pop(0)
            if addr in visited or depth > max_depth:
                continue
            
            # Read a chunk (512 bytes for small objects, 4096 for large)
            chunk = self.read(addr, 512)
            if not chunk:
                continue
            
            visited[addr] = (len(chunk), hashlib.md5(chunk).hexdigest())
            
            if depth >= max_depth:
                continue
            
            # Scan for valid heap pointers (every 4 bytes, aligned)
            for offset in range(0, len(chunk) - 3, 4):
                val = struct.unpack("<I", chunk[offset:offset+4])[0]
                if self.is_valid_heap_ptr(val) and val not in visited:
                    queue.append((val, depth + 1))
        
        return visited
    
    def close(self):
        if self.h:
            kernel32.CloseHandle(self.h)

def load_keymap(kmp):
    subprocess.run([INJECTOR, kmp], capture_output=True, timeout=15)

def main():
    pid = find_pid()
    if not pid: print("ERROR"); return 1
    print(f"PID={pid}")
    
    inst = get_saved_instance(pid)
    if not inst: print("ERROR: no savedInstance"); return 1
    print(f"savedInstance=0x{inst:08X}")
    
    # Explore
    explorer = HeapExplorer(pid)
    print(f"Cached {len(explorer.heap_regions)} heap regions")
    
    # Walk mode
    print("\n--- Exploring WALK mode object graph ---")
    load_keymap(WALK)
    time.sleep(0.5)
    walk_graph = explorer.chase_pointers(inst, max_depth=4, max_objects=2000)
    print(f"Walk graph: {len(walk_graph)} objects")
    
    # Drive mode
    print("\n--- Exploring DRIVE mode object graph ---")
    load_keymap(DRIVE)
    time.sleep(0.5)
    drive_graph = explorer.chase_pointers(inst, max_depth=4, max_objects=2000)
    print(f"Drive graph: {len(drive_graph)} objects")
    
    # Diff
    print("\n--- Diff ---")
    all_addrs = set(walk_graph.keys()) | set(drive_graph.keys())
    changed = []
    only_walk = []
    only_drive = []
    
    for addr in sorted(all_addrs):
        w = walk_graph.get(addr)
        d = drive_graph.get(addr)
        if w and d and w[1] != d[1]:
            changed.append(addr)
        elif w and not d:
            only_walk.append(addr)
        elif d and not w:
            only_drive.append(addr)
    
    print(f"Changed: {len(changed)}")
    print(f"Only in walk: {len(only_walk)}")
    print(f"Only in drive: {len(only_drive)}")
    
    if changed:
        print(f"\n--- Top changed objects ---")
        for addr in changed[:20]:
            size_w, hash_w = walk_graph[addr]
            size_d, hash_d = drive_graph[addr]
            # Read current content
            data = explorer.read(addr, min(128, size_d))
            hex_str = " ".join(f"{b:02X}" for b in data[:64])
            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data[:64])
            print(f"\n  0x{addr:08X} (size: {size_w}→{size_d})")
            print(f"    Walk hash: {hash_w}")
            print(f"    Drive hash: {hash_d}")
            print(f"    Content: {hex_str}")
            print(f"             {ascii_str}")
    
    explorer.close()

if __name__ == "__main__":
    main()
