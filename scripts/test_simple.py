import ctypes
from ctypes import wintypes
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

print("1")
hMap = kernel32.OpenFileMappingW(0x0004, False, "LDKeymapSwitch_Mem")
print(f"2 hMap=0x{hMap:X} err={ctypes.get_last_error()}")
if not hMap:
    print("NO SHM - exiting")
    exit()

print("3")
p = kernel32.MapViewOfFile(hMap, 0x0004, 0, 0, 0)
kernel32.CloseHandle(hMap)
print(f"4 p=0x{p:X}")

print("5")
inst = ctypes.c_uint32.from_address(p + 0xC08).value
print(f"6 inst=0x{inst:08X}")

kernel32.UnmapViewOfFile(p)
print("7 unmap ok")

h = kernel32.OpenProcess(0x10, False, 2708)
print(f"8 hProc=0x{h:X} err={ctypes.get_last_error()}")

if h:
    buf = ctypes.create_string_buffer(16)
    br = ctypes.c_size_t(0)
    ret = kernel32.ReadProcessMemory(h, ctypes.c_void_p(inst), buf, 16, ctypes.byref(br))
    print(f"9 RPM ret={ret} bytes={br.value}")
    print(f"10 data={' '.join(f'{b:02X}' for b in buf.raw[:br.value])}")
    kernel32.CloseHandle(h)
print("11 DONE")
