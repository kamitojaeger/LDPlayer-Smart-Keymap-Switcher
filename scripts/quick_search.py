"""Quick memory search for walk.kmp feature values in dnplayer.exe."""
import ctypes, struct
from ctypes import wintypes

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
        ('AllocationProtect', wintypes.DWORD), ('RegionSize', ctypes.c_size_t),
        ('State', wintypes.DWORD), ('Protect', wintypes.DWORD), ('Type', wintypes.DWORD),
    ]

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
PID = 46392
handle = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, PID)
assert handle, f'OpenProcess failed: {ctypes.get_last_error()}'

def search_pattern(handle, pattern_bytes, label, max_hits=10):
    hits = []
    CHUNK = 1024 * 1024
    addr = 0; regions = 0; total = 0
    
    while True:
        mbi = MEMORY_BASIC_INFORMATION()
        result = kernel32.VirtualQueryEx(handle, ctypes.c_void_p(addr),
                                         ctypes.byref(mbi), ctypes.sizeof(mbi))
        if result == 0:
            break
        
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        protect = mbi.Protect
        if base is None:
            addr = 0x7FFFFFFF  # force exit
            continue
        
        if (mbi.State == 0x1000 and size >= 4096 and protect != 0x01 and
            (protect & (0x02|0x04|0x08|0x20|0x40|0x80))):
            regions += 1
            offset = 0
            while offset < size and len(hits) < max_hits:
                chunk_sz = min(CHUNK, size - offset)
                buf = ctypes.create_string_buffer(chunk_sz)
                br = ctypes.c_size_t(0)
                if not kernel32.ReadProcessMemory(handle, ctypes.c_void_p(base + offset),
                                                   buf, chunk_sz, ctypes.byref(br)):
                    break
                data = buf.raw[:br.value]; total += len(data)
                pos = 0
                while True:
                    idx = data.find(pattern_bytes, pos)
                    if idx == -1: break
                    hits.append(base + offset + idx)
                    pos = idx + 1
                offset += chunk_sz
        
        addr = base + size
    
    print(f'[{label}] {len(hits)} hits (searched {regions} regions, {total:,} bytes)')
    for addr in hits:
        ctx_start = max(0, addr - 32)
        ctx = ctypes.create_string_buffer(128)
        br = ctypes.c_size_t(0)
        kernel32.ReadProcessMemory(handle, ctypes.c_void_p(ctx_start), ctx, 128, ctypes.byref(br))
        data = ctx.raw[:br.value]
        hex_str = ' '.join(f'{b:02X}' for b in data)
        phex = ' '.join(f'{b:02X}' for b in pattern_bytes)
        hex_str = hex_str.replace(phex, '[' + phex + ']')
        print(f'  0x{addr:08X}: {hex_str}')
    return hits

# Search: A(65) W(87) D(68) S(83) consecutive int32
print('=== Search: A(65) W(87) D(68) S(83) ===')
hits1 = search_pattern(handle, struct.pack('<4i', 65, 87, 68, 83), 'A_W_D_S')

# Search: origin (1824, 8413) consecutive
print('\n=== Search: origin (1824, 8413) ===')
hits2 = search_pattern(handle, struct.pack('<2i', 1824, 8413), 'origin')

# Search: radius=773
print('\n=== Search: radius=773 ===')
hits3 = search_pattern(handle, struct.pack('<i', 773), 'radius')

# Search: ClassMouseDrag origin (6086, 3156) from walk.kmp
print('\n=== Search: MouseDrag origin (6086, 3156) ===')
hits4 = search_pattern(handle, struct.pack('<2i', 6086, 3156), 'mousedrag')

kernel32.CloseHandle(handle)
