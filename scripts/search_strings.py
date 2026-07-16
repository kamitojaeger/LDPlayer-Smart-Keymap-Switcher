"""Search for keymap file paths in dnplayer.exe memory.

The hypothesis is that LDPlayer stores the currently loaded .kmp filename
somewhere in CInputMgr, and the keyboard mapping data is stored nearby.
"""
import ctypes, struct
from ctypes import wintypes, c_void_p
import sys

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BaseAddress', ctypes.c_void_p),
        ('AllocationBase', ctypes.c_void_p),
        ('AllocationProtect', wintypes.DWORD),
        ('RegionSize', ctypes.c_size_t),
        ('State', wintypes.DWORD),
        ('Protect', wintypes.DWORD),
        ('Type', wintypes.DWORD),
    ]

def search_string(handle, target: bytes, label: str, max_hits=8):
    """Search all committed readable memory for a byte string."""
    hits = []
    CHUNK = 1024 * 1024
    addr = 0
    regions = 0
    total = 0

    while True:
        mbi = MEMORY_BASIC_INFORMATION()
        if not kernel32.VirtualQueryEx(handle, c_void_p(addr),
                                       ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break

        base = mbi.BaseAddress
        if base is None:
            addr += 0x10000
            continue

        base_int = base  # ctypes already handles conversion
        size = mbi.RegionSize
        protect = mbi.Protect

        readable = protect & (0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80)
        if mbi.State == MEM_COMMIT and size >= 4096 and readable and protect != 0x01:
            regions += 1
            offset = 0
            while offset < size and len(hits) < max_hits:
                chunk_sz = min(CHUNK, size - offset)
                buf = ctypes.create_string_buffer(chunk_sz)
                br = ctypes.c_size_t(0)
                if not kernel32.ReadProcessMemory(handle, c_void_p(base_int + offset),
                                                   buf, chunk_sz, ctypes.byref(br)):
                    break
                data = buf.raw[:br.value]
                total += len(data)
                pos = 0
                while True:
                    idx = data.find(target, pos)
                    if idx == -1:
                        break
                    abs_addr = base_int + offset + idx
                    # Read context: 64 bytes before, 192 after
                    ctx_start = max(0, abs_addr - 64)
                    ctx_sz = 256
                    ctx = ctypes.create_string_buffer(ctx_sz)
                    ctx_br = ctypes.c_size_t(0)
                    kernel32.ReadProcessMemory(handle, c_void_p(ctx_start),
                                               ctx, ctx_sz, ctypes.byref(ctx_br))
                    if ctx_br.value > 0:
                        hits.append((abs_addr, ctx.raw[:ctx_br.value]))
                    pos = idx + 1
                offset += chunk_sz

        addr = base_int + size

    print(f'\n[{label}] {len(hits)} hits (regions={regions}, bytes={total:,})')
    for abs_addr, ctx_data in hits:
        # Format hex dump with highlight
        offset_in_ctx = abs_addr - max(0, abs_addr - 64)
        ctx_start = max(0, abs_addr - 64)
        print(f'  0x{abs_addr:08X} (ctx from 0x{ctx_start:08X}):')
        for row in range(0, len(ctx_data), 16):
            line_data = ctx_data[row:row+16]
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line_data)
            hex_part = ' '.join(f'{b:02X}' for b in line_data)
            # Highlight the target if it's in this row
            rel_start = row - offset_in_ctx
            rel_end = rel_start + 16
            if rel_start < len(target) and rel_end > 0:
                marker_start = max(0, -rel_start)
                marker_end = min(len(target), 16 - rel_start)
                # Simple: just mark the row
                print(f'    {hex_part:48s} |{ascii_part}| ***')
            else:
                print(f'    {hex_part:48s} |{ascii_part}|')
    return hits


kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

if len(sys.argv) < 2:
    print("Usage: python search_strings.py <PID>")
    sys.exit(1)

PID = int(sys.argv[1])
handle = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, PID)
assert handle, f'OpenProcess(PID={PID}) failed: {ctypes.get_last_error()}'

# Search targets
targets = [
    (b'GTASA(walk mode).kmp', 'Walk kmp path'),
    (b'GTASA(Drive mode).kmp', 'Drive kmp path'),
    (b'walk mode', 'walk mode substring'),
    (b'customizeConfigs', 'customizeConfigs path'),
    (b'keyboardMappings', 'JSON key: keyboardMappings'),
]

for target, label in targets:
    search_string(handle, target, label)

kernel32.CloseHandle(handle)
print('\nDone.')
