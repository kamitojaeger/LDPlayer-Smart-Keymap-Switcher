"""
Memory Scanner — search dnplayer.exe memory for probe .kmp feature values.
Used for Phase 3.1: locating keyboard mapping data structure in memory.

Feature values to search:
  probe_disc.kmp:  origin.x=1111 (0x0457), origin.y=2222 (0x08AE), radius=3333 (0x0D05)
  probe_all_types.kmp: additional unique values 4444,5555,6666,7777,8888,9999,1010,2020
"""

import ctypes
from ctypes import wintypes
import struct
import sys

# Windows API constants
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_IMAGE = 0x1000000
PAGE_READABLE = (0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80)  # READONLY|READWRITE|WRITECOPY|EXECUTE_READ|EXECUTE_READWRITE|EXECUTE_WRITECOPY


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


class MemoryScanner:
    def __init__(self, pid: int):
        self.pid = pid
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        # OpenProcess
        self._OpenProcess = kernel32.OpenProcess
        self._OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._OpenProcess.restype = wintypes.HANDLE

        # VirtualQueryEx
        self._VirtualQueryEx = kernel32.VirtualQueryEx
        self._VirtualQueryEx.argtypes = [
            wintypes.HANDLE, wintypes.LPCVOID,
            ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t
        ]
        self._VirtualQueryEx.restype = ctypes.c_size_t

        # ReadProcessMemory
        self._ReadProcessMemory = kernel32.ReadProcessMemory
        self._ReadProcessMemory.argtypes = [
            wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID,
            ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)
        ]
        self._ReadProcessMemory.restype = wintypes.BOOL

        # CloseHandle
        self._CloseHandle = kernel32.CloseHandle
        self._CloseHandle.argtypes = [wintypes.HANDLE]
        self._CloseHandle.restype = wintypes.BOOL

        self.handle = self._OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, self.pid
        )
        if not self.handle:
            raise OSError(f"Failed to open process {pid}. Run as Administrator?")

    def close(self):
        if self.handle:
            self._CloseHandle(self.handle)
            self.handle = None

    def _read_memory(self, address: int, size: int) -> bytes:
        """Read memory from target process."""
        buf = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t(0)
        success = self._ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(bytes_read)
        )
        if not success or bytes_read.value == 0:
            return b""
        return buf.raw[:bytes_read.value]

    def enumerate_regions(self, min_size: int = 4096):
        """Yield (base_address, size, protect) for readable committed regions."""
        addr = 0
        mbi = MEMORY_BASIC_INFORMATION()
        while True:
            result = self._VirtualQueryEx(
                self.handle, ctypes.c_void_p(addr),
                ctypes.byref(mbi), ctypes.sizeof(mbi)
            )
            if result == 0:
                break
            if (mbi.State == MEM_COMMIT and
                mbi.RegionSize >= min_size and
                (mbi.Protect & PAGE_READABLE) and
                mbi.Protect != 0x01):  # skip PAGE_NOACCESS
                yield mbi.BaseAddress, mbi.RegionSize, mbi.Protect, mbi.Type
            addr = mbi.BaseAddress + mbi.RegionSize

    def search_pattern(self, pattern: bytes, max_hits: int = 50):
        """
        Search all committed readable memory for a byte pattern.
        Returns list of (address, surrounding_hex).
        """
        hits = []
        regions_searched = 0
        total_bytes = 0

        CHUNK = 256 * 1024  # 256KB chunks

        for base, size, protect, mem_type in self.enumerate_regions():
            regions_searched += 1
            offset = 0
            while offset < size:
                chunk_size = min(CHUNK, size - offset)
                data = self._read_memory(base + offset, chunk_size)
                if not data:
                    break
                total_bytes += len(data)

                # Search for pattern in this chunk
                pos = 0
                while True:
                    idx = data.find(pattern, pos)
                    if idx == -1:
                        break
                    abs_addr = base + offset + idx
                    # Read surrounding bytes for context (64 bytes before, 128 after)
                    context_start = max(0, abs_addr - 64)
                    context_size = min(256, abs_addr + 128 - context_start)
                    context_data = self._read_memory(context_start, context_size)
                    hits.append((abs_addr, context_data.hex(' '), context_start))
                    pos = idx + 1
                    if len(hits) >= max_hits:
                        break
                offset += chunk_size
                if len(hits) >= max_hits:
                    break
            if len(hits) >= max_hits:
                break

        print(f"Regions searched: {regions_searched}, total bytes: {total_bytes:,}")
        return hits

    def search_int32(self, value: int, max_hits: int = 20):
        """Search for a 4-byte little-endian int32 value."""
        pattern = struct.pack('<i', value)
        return self.search_pattern(pattern, max_hits)

    def search_int32_sequence(self, values: list[int], max_hits: int = 20):
        """Search for consecutive int32 values in memory."""
        pattern = b''.join(struct.pack('<i', v) for v in values)
        return self.search_pattern(pattern, max_hits)


def print_hits(hits: list, label: str = ""):
    """Pretty-print search hits."""
    if not hits:
        print(f"\n{'='*70}\n[{label}] No hits found.\n{'='*70}")
        return

    print(f"\n{'='*70}")
    print(f"[{label}] {len(hits)} hit(s)")
    print(f"{'='*70}")
    for addr, hex_str, context_start in hits:
        print(f"\n  Address: 0x{addr:08X}  (context from 0x{context_start:08X})")
        # Group hex into 4-byte columns
        parts = hex_str.split()
        for i in range(0, len(parts), 8):
            line = parts[i:i+8]
            # Highlight int32 values
            formatted = []
            for j, b in enumerate(line):
                formatted.append(b)
            print(f"    {' '.join(formatted)}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scan dnplayer.exe memory for probe .kmp values")
    parser.add_argument("--pid", type=int, required=True, help="dnplayer.exe PID")
    parser.add_argument("--probe", type=str, default="disc",
                        choices=["disc", "all", "both"],
                        help="Which probe to search for")
    args = parser.parse_args()

    scanner = MemoryScanner(args.pid)
    try:
        if args.probe in ("disc", "both"):
            print("\n>>> Searching for probe_disc.kmp features...")
            # origin.x=1111, origin.y=2222, radius=3333
            hits = scanner.search_int32_sequence([1111, 2222, 3333], max_hits=20)
            print_hits(hits, "probe_disc: [1111, 2222, 3333] consecutive")

            # Also search for origin alone (in case fields aren't contiguous)
            if not hits:
                print("\n  Trying origin.x=1111 alone...")
                hits = scanner.search_int32(1111, max_hits=10)
                print_hits(hits, "probe_disc: origin.x=1111")

        if args.probe in ("all", "both"):
            print("\n>>> Searching for probe_all_types.kmp features...")
            # ClassKeyboardDisc: [1111, 2222, 3333]
            hits = scanner.search_int32_sequence([1111, 2222, 3333], max_hits=10)
            print_hits(hits, "probe_all: Disc [1111, 2222, 3333]")

            # ClassMouseDrag: origin [4444, 5555] + key=17
            hits = scanner.search_int32_sequence([4444, 5555], max_hits=10)
            print_hits(hits, "probe_all: MouseDrag origin [4444, 5555]")

            # ClassKeyboardCurve: [6666, 7777]
            hits = scanner.search_int32_sequence([6666, 7777], max_hits=10)
            print_hits(hits, "probe_all: Curve [6666, 7777]")

            # ClassKeyboardMacros: origin [8888, 9999]
            hits = scanner.search_int32_sequence([8888, 9999], max_hits=10)
            print_hits(hits, "probe_all: Macros origin [8888, 9999]")

            # ClassMouseTrigger: point [1010, 2020]
            hits = scanner.search_int32_sequence([1010, 2020], max_hits=10)
            print_hits(hits, "probe_all: MouseTrigger point [1010, 2020]")

    finally:
        scanner.close()


if __name__ == "__main__":
    main()
