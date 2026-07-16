import ctypes
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
h = kernel32.OpenFileMappingW(0x0004, False, "LDKeymapSwitch_Mem")
print(f"1 h={h:X}")
p = kernel32.MapViewOfFile(h, 0x0004, 0, 0, 0)
print(f"2 p=0x{p:X}")
if p:
    # Just read first 4 bytes as raw int
    val = ctypes.cast(p, ctypes.POINTER(ctypes.c_uint32)).contents.value
    print(f"3 val=0x{val:08X}")
    kernel32.UnmapViewOfFile(p)
kernel32.CloseHandle(h)
print("4 OK")
