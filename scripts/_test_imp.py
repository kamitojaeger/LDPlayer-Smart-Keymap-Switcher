print("1")
import ctypes
print("2")
from ctypes import wintypes
print("3")
kernel32 = ctypes.WinDLL("kernel32")
print("4")
print("OK")
