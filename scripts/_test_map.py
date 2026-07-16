import ctypes
from ctypes import wintypes
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
h = kernel32.OpenFileMappingW(0x0004, False, "LDKeymapSwitch_Mem")
assert h
print("1")
p = kernel32.MapViewOfFile(h, 0x0004, 0, 0, 0)
print(f"2 p=0x{p:X}")
kernel32.CloseHandle(h)
print("3")
val = ctypes.c_uint32.from_address(p + 0xC08).value
print(f"4 val=0x{val:08X}")
kernel32.UnmapViewOfFile(p)
print("5 OK")
