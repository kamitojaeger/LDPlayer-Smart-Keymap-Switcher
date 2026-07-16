import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# CORRECT PROCESSENTRY32W — all fields 32-bit safe
class PE(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", wintypes.ULONG),  # ULONG_PTR → ULONG for 32-bit compat
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]

# Test: list first 5 processes
snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
print(f"snap={snap}")
if snap != -1:
    pe = PE()
    pe.dwSize = ctypes.sizeof(PE)
    print(f"struct size={ctypes.sizeof(PE)}")
    count = 0
    if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
        while count < 5:
            print(f"  PID={pe.th32ProcessID:6d} {pe.szExeFile}")
            count += 1
            if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                break
    kernel32.CloseHandle(snap)

print("OK - no crash")
