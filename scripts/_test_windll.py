import ctypes
k32 = ctypes.windll.kernel32
h = k32.OpenFileMappingW(0x0004, 0, "LDKeymapSwitch_Mem")
print(f"h={h}")
p = k32.MapViewOfFile(h, 0x0004, 0, 0, 0)
print(f"p={p}")  
if p:
    v = ctypes.cast(p, ctypes.POINTER(ctypes.c_uint32)).contents.value
    print(f"magic=0x{v:08X}")
    k32.UnmapViewOfFile(p)
k32.CloseHandle(h)
print("OK")
