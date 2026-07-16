import ctypes
from ctypes import wintypes
print("1")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
print("2")
h = kernel32.OpenFileMappingW(0x0004, False, "LDKeymapSwitch_Mem")
print(f"3 h={h} err={ctypes.get_last_error()}")
if h:
    kernel32.CloseHandle(h)
print("4 OK")
