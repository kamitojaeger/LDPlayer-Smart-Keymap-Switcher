"""Diagnostic: disassemble setKeyboardConfig + dump CInputMgr state.

Reads:
1. Function bytes at dnplycore.dll + 0x96130 (~512 bytes)
2. CInputMgr object at savedInstance (~512 bytes)
"""
import ctypes, struct, subprocess
from ctypes import wintypes
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

FUNC_RVA = 0x96130
FUNC_SIZE = 512

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

def find_pid():
    r = subprocess.run(["tasklist", "/fi", "IMAGENAME eq dnplayer.exe", "/fo", "csv", "/nh"],
                       capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        if "dnplayer.exe" in line.lower():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 2:
                return int(parts[1].strip())
    return 0

def find_module_base(pid, modname):
    TH32CS = 0x8 | 0x10
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS, pid)
    if snap == ctypes.c_void_p(-1).value: return 0
    buf = ctypes.create_string_buffer(1080)
    ctypes.c_uint32.from_address(ctypes.addressof(buf)).value = 1080
    base = 0
    if kernel32.Module32FirstW(snap, buf):
        while True:
            name = ctypes.c_wchar_p(ctypes.addressof(buf) + 48).value
            if name and name.lower() == modname.lower():
                base = ctypes.c_uint32.from_address(ctypes.addressof(buf) + 24).value
                break
            ctypes.c_uint32.from_address(ctypes.addressof(buf)).value = 1080
            if not kernel32.Module32NextW(snap, buf): break
    kernel32.CloseHandle(snap)
    return base

def get_saved_instance():
    hMap = kernel32.OpenFileMappingW(0x0004, False, "LDKeymapSwitch_Mem")
    if not hMap: return 0
    p = kernel32.MapViewOfFile(hMap, 0x0004, 0, 0, 0)
    kernel32.CloseHandle(hMap)
    if not p: return 0
    inst = ctypes.c_uint32.from_address(p + 0xC08).value
    kernel32.UnmapViewOfFile(p)
    return inst

def read_mem(hProc, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
    return buf.raw[:br.value] if ok else b""

pid = find_pid()
print(f"dnplayer PID: {pid}")
inst = get_saved_instance()
print(f"savedInstance: 0x{inst:08X}")
dnplycore = find_module_base(pid, "dnplycore.dll")
print(f"dnplycore.dll base: 0x{dnplycore:08X}")

hProc = kernel32.OpenProcess(0x10, False, pid)
assert hProc

# ── 1. Disassemble setKeyboardConfig ──
func_addr = dnplycore + FUNC_RVA
code = read_mem(hProc, func_addr, FUNC_SIZE)
print(f"\n{'='*70}")
print(f"setKeyboardConfig @ 0x{func_addr:08X} (RVA 0x{FUNC_RVA:05X})")
print(f"{'='*70}")

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

calls = []
branches = []

for insn in md.disasm(code, func_addr):
    rva = insn.address - dnplycore
    mnem = insn.mnemonic
    ops = insn.op_str

    marker = ""
    if mnem == "call":
        calls.append((rva, ops))
        marker = "  << CALL"
    elif mnem in ("jz", "jnz", "je", "jne", "jmp", "jl", "jle", "jg", "jge", "jb", "jbe", "ja", "jae"):
        branches.append((rva, mnem, ops))
        marker = f"  << {mnem.upper()}"

    # Stop at next function prologue (push ebp; mov ebp,esp) after some instructions
    if rva > 0x50 and mnem == "push" and ops == "ebp":
        print(f"  [stop: next function prologue at 0x{rva:05X}]")
        break

    print(f"  0x{rva:05X}:  {mnem:8s} {ops:35s}{marker}")

print(f"\n{'='*70}")
print(f"Calls: {len(calls)}")
for rva, ops in calls:
    print(f"  @0x{rva:05X}: call {ops}")

print(f"\nConditional branches: {len(branches)}")
for rva, mnem, ops in branches:
    print(f"  @0x{rva:05X}: {mnem} {ops}")

# ── 2. Dump CInputMgr object ──
print(f"\n{'='*70}")
print(f"CInputMgr @ 0x{inst:08X} (first 256 bytes)")
print(f"{'='*70}")

obj = read_mem(hProc, inst, 256)
if obj:
    for row in range(0, min(len(obj), 256), 16):
        addr = inst + row
        line = obj[row:row+16]
        hx = " ".join(f"{b:02X}" for b in line)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in line)
        # Annotate DWORD values
        dwords = []
        for i in range(0, min(16, len(line)), 4):
            if i + 4 <= len(line):
                val = struct.unpack("<I", line[i:i+4])[0]
                if 0x03000000 <= val <= 0x21000000:
                    dwords.append(f" [+0x{row+i:03X}]=0x{val:08X}(ptr?)")
        dstr = "".join(dwords)
        print(f"  0x{addr:08X} (+0x{row:03X}): {hx:48s} |{asc}|{dstr}")
else:
    print("  [read failed]")

kernel32.CloseHandle(hProc)
