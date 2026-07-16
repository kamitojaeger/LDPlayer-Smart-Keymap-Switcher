"""Phase 3.1: CInputMgr memory diff — walk vs drive keymaps.

Loads walk.kmp, dumps CInputMgr memory, loads drive.kmp, dumps again, compares.
"""
import ctypes, struct, subprocess, sys, os, json, hashlib
from ctypes import wintypes

INJECTOR = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\dist\keymap_injector.exe"
KMP_DIR = r"D:\LD_DEV\LDPlayer_Auto_Input_Switcher\games\gtasa\keymaps"
WALK_KMP = os.path.join(KMP_DIR, "GTASA(walk mode).kmp")
DRIVE_KMP = os.path.join(KMP_DIR, "GTASA(Drive mode).kmp")

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
        ('AllocationProtect', wintypes.DWORD), ('RegionSize', ctypes.c_size_t),
        ('State', wintypes.DWORD), ('Protect', wintypes.DWORD), ('Type', wintypes.DWORD),
    ]


def load_keymap(kmp_path):
    """Use injector to load a .kmp into LDPlayer."""
    result = subprocess.run([INJECTOR, kmp_path], capture_output=True, text=True)
    success = "SUCCESS" in result.stdout
    print(result.stdout[-200:] if result.stdout else "no output")
    return success


def get_pid():
    """Find dnplayer.exe PID."""
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if snapshot == -1:
        return 0
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.POINTER(wintypes.ULONG)),
            ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260),
        ]
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    pid = 0
    if kernel32.Process32FirstW(snapshot, ctypes.byref(pe)):
        while True:
            if pe.szExeFile.lower() == 'dnplayer.exe':
                pid = pe.th32ProcessID
                break
            if not kernel32.Process32NextW(snapshot, ctypes.byref(pe)):
                break
    kernel32.CloseHandle(snapshot)
    return pid


class MemoryDumper:
    def __init__(self, pid):
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.handle = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.handle:
            raise OSError(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}")

    def read(self, addr, size):
        buf = ctypes.create_string_buffer(size)
        br = ctypes.c_size_t(0)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
        return buf.raw[:br.value]

    def close(self):
        if self.handle:
            ctypes.WinDLL('kernel32').CloseHandle(self.handle)
            self.handle = None

    def is_readable_heap(self, addr):
        """Check if an address points to readable committed memory."""
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        mbi = MEMORY_BASIC_INFORMATION()
        if not kernel32.VirtualQueryEx(self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            return False
        readable = mbi.Protect & (0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80)
        return mbi.State == 0x1000 and readable and mbi.RegionSize >= 16

    def dump_object_tree(self, root_addr, depth=1, max_depth=2, visited=None):
        """Recursively dump an object and its heap pointers."""
        if visited is None:
            visited = set()
        if root_addr in visited or root_addr == 0 or depth > max_depth:
            return {}
        visited.add(root_addr)

        data = self.read(root_addr, 512)
        result = {root_addr: data}

        # Find heap pointers
        for offset in range(0, min(512, len(data)), 4):
            val = struct.unpack('<I', data[offset:offset+4])[0]
            if 0x03000000 <= val <= 0x21000000 and val not in visited:
                if self.is_readable_heap(val):
                    child = self.dump_object_tree(val, depth + 1, max_depth, visited)
                    result.update(child)

        return result


def hexdump_compact(data, base_addr):
    """Generate compact hex dump with ASCII."""
    lines = []
    for row in range(0, len(data), 16):
        line = data[row:row+16]
        hex_str = ' '.join(f'{b:02X}' for b in line)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
        lines.append(f'  0x{base_addr + row:08X}: {hex_str:48s} |{ascii_str}|')
    return '\n'.join(lines)


def diff_dumps(dump_a, dump_b):
    """Compare two memory dumps and return changed addresses."""
    changes = []
    for addr in sorted(dump_a.keys() | dump_b.keys()):
        data_a = dump_a.get(addr, b'')
        data_b = dump_b.get(addr, b'')
        if data_a != data_b:
            # Show only the differing bytes
            for offset in range(0, min(len(data_a), len(data_b)), 16):
                chunk_a = data_a[offset:offset+16]
                chunk_b = data_b[offset:offset+16]
                if chunk_a != chunk_b:
                    changes.append((addr, offset, chunk_a, chunk_b))
    return changes


def main():
    print("=== Phase 3.1: CInputMgr Memory Diff ===")

    # Get PID
    pid = get_pid()
    if not pid:
        print("ERROR: dnplayer.exe not running!")
        sys.exit(1)
    print(f"PID: {pid}")

    dumper = MemoryDumper(pid)

    try:
        # Step 1: Load walk.kmp
        print("\n--- Loading WALK mode ---")
        if not load_keymap(WALK_KMP):
            print("WARNING: Walk load may have failed, continuing...")

        # Step 2: Dump CInputMgr
        CINPUTMGR = 0x051E8CB0
        print(f"\n--- Dumping CInputMgr (walk) @ 0x{CINPUTMGR:08X} ---")
        dump_walk = dumper.dump_object_tree(CINPUTMGR, max_depth=2)
        print(f"Dumped {len(dump_walk)} objects")

        # Save walk dump
        walk_hashes = {addr: hashlib.md5(data).hexdigest() for addr, data in dump_walk.items()}
        print(f"Walk dump hashes: {len(walk_hashes)} objects")

        # Step 3: Load drive.kmp
        print("\n--- Loading DRIVE mode ---")
        if not load_keymap(DRIVE_KMP):
            print("WARNING: Drive load may have failed, continuing...")
        import time; time.sleep(0.5)

        # Step 4: Dump CInputMgr again
        print(f"\n--- Dumping CInputMgr (drive) @ 0x{CINPUTMGR:08X} ---")
        dump_drive = dumper.dump_object_tree(CINPUTMGR, max_depth=2)
        print(f"Dumped {len(dump_drive)} objects")

        # Step 5: Diff
        print("\n=== DIFF RESULTS ===")
        changes = diff_dumps(dump_walk, dump_drive)
        if not changes:
            print("No differences found! The dumps are identical.")
            print("This means either the keymap data is elsewhere, or the switch didn't actually happen.")
            print("\nWalk dump (first 64 bytes of root):")
            print(hexdump_compact(dump_walk.get(CINPUTMGR, b'')[:64], CINPUTMGR))
        else:
            print(f"Found {len(changes)} changed regions:")
            for addr, offset, a, b in changes:
                abs_addr = addr + offset
                hex_a = ' '.join(f'{x:02X}' for x in a)
                hex_b = ' '.join(f'{x:02X}' for x in b)
                print(f"  0x{abs_addr:08X}:")
                print(f"    WALK:  {hex_a}")
                print(f"    DRIVE: {hex_b}")
                print()

        # Also dump key interesting objects
        print("\n=== Interesting objects (drive) ===")
        for addr in sorted(dump_drive.keys()):
            data = dump_drive[addr]
            # Check if it contains JSON-like content
            try:
                text = data[:128].decode('ascii', errors='ignore')
                if '{' in text or 'keyboard' in text.lower() or 'kmp' in text.lower():
                    print(f"\n  0x{addr:08X} (JSON-like):")
                    print(hexdump_compact(data[:128], addr))
            except:
                pass

            # Show first 64 bytes of each object
            if addr != CINPUTMGR:
                print(f"\n  0x{addr:08X}:")
                print(hexdump_compact(data[:64], addr))

    finally:
        dumper.close()


if __name__ == "__main__":
    main()
