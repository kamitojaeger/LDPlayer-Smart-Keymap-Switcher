import ctypes, struct
from ctypes import wintypes

# Use hardcoded PID from injector --status
PID = 2708
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Get savedInstance from shared memory
hMap = kernel32.OpenFileMappingW(0x0004, False, "LDKeymapSwitch_Mem")
assert hMap, f"OpenFileMapping failed: {ctypes.get_last_error()}"
p = kernel32.MapViewOfFile(hMap, 0x0004, 0, 0, 0)
kernel32.CloseHandle(hMap)
assert p
inst = ctypes.c_uint32.from_address(p + 0xC08).value
print(f"PID={PID} savedInstance=0x{inst:08X}")
kernel32.UnmapViewOfFile(p)

# Open process
h = kernel32.OpenProcess(0x10, False, PID)
assert h, f"OpenProcess failed: {ctypes.get_last_error()}"

# Read 2KB around savedInstance
buf = ctypes.create_string_buffer(2048)
br = ctypes.c_size_t(0)
start = inst - 0x80
kernel32.ReadProcessMemory(h, ctypes.c_void_p(start), buf, 2048, ctypes.byref(br))
data = buf.raw[:br.value]
print(f"Read {len(data)} bytes from 0x{start:08X}")

# Show hex
for row in range(0, len(data), 16):
    addr = start + row
    line = data[row:row+16]
    marker = " <-- savedInstance" if addr <= inst < addr + 16 else ""
    hx = " ".join(f"{b:02X}" for b in line)
    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in line)
    print(f"0x{addr:08X}: {hx:48s} |{asc}|{marker}")

# Extract all possible heap pointers (values 0x03000000-0x21000000) 
# and show what they point to
print("\n=== Heap pointer scan ===")
for offset in range(0, 512, 4):
    val = struct.unpack("<I", data[offset:offset+4])[0]
    if 0x03000000 <= val <= 0x21000000:
        # Try to read what this points to
        ptr_buf = ctypes.create_string_buffer(64)
        ptr_br = ctypes.c_size_t(0)
        if kernel32.ReadProcessMemory(h, ctypes.c_void_p(val), ptr_buf, 64, ctypes.byref(ptr_br)):
            ptr_data = ptr_buf.raw[:ptr_br.value]
            # Try to decode as string or show hex
            try:
                text = ptr_data[:40].decode("ascii", errors="ignore")
                printable = sum(1 for c in text if 32 <= ord(c) < 127)
                if printable > 20:
                    print(f"  +0x{offset:03X} → 0x{val:08X}: STRING \"{text[:40]}\"")
                else:
                    hx = " ".join(f"{b:02X}" for b in ptr_data[:16])
                    print(f"  +0x{offset:03X} → 0x{val:08X}: {hx}")
            except:
                pass

kernel32.CloseHandle(h)
print("\nOK")
