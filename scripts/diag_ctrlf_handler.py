"""Disassemble the Ctrl+F handler preamble before the CALL site.

CALL site: RVA 0x1DA53 (call setKeyboardConfig)
Return:   RVA 0x1DA58

Dump 256 bytes BEFORE the call site to find the function that does
the .kmp file reading and calls the vtable getter.
"""
import ctypes, struct, subprocess
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# Use values from current --status
DNPLYCORE_BASE = 0x79C10000  # will be updated from --status
CALL_RVA = 0x1DA53
DUMP_BEFORE = 512  # bytes before call site

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

def find_pid():
    r = subprocess.run(["tasklist", "/fi", "IMAGENAME eq dnplayer.exe", "/fo", "csv", "/nh"],
                       capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        if "dnplayer.exe" in line.lower():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 2: return int(parts[1].strip())
    return 0

def read_mem(hProc, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
    return buf.raw[:br.value] if ok else b""

def get_dnplycore_base():
    hMap = kernel32.OpenFileMappingW(0x0004, False, "LDKeymapSwitch_Mem")
    if not hMap: return 0
    p = kernel32.MapViewOfFile(hMap, 0x0004, 0, 0, 0)
    kernel32.CloseHandle(hMap)
    if not p: return 0
    func_addr = ctypes.c_uint32.from_address(p + 0xC0C).value  # funcAddress
    kernel32.UnmapViewOfFile(p)
    if func_addr: return func_addr - 0x96130  # FUNC_RVA
    return 0

pid = find_pid()
base = 0x79C10000  # from --status: FuncAddress(0x79CA6130) - FUNC_RVA(0x96130)
print(f"PID: {pid}, dnplycore base: 0x{base:08X}")

hProc = kernel32.OpenProcess(0x10, False, pid)
assert hProc

# Read bytes around the CALL site
call_addr = base + CALL_RVA
start = call_addr - DUMP_BEFORE
total = DUMP_BEFORE + 16  # include a few bytes after CALL
code = read_mem(hProc, start, total)

print(f"\n{'='*70}")
print(f"Ctrl+F handler region: 0x{start:08X} - 0x{start+total:08X}")
print(f"CALL site: 0x{call_addr:08X} (RVA 0x{CALL_RVA:05X})")
print(f"{'='*70}")

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

instructions = list(md.disasm(code, start))
calls = []
file_ops = []

for insn in instructions:
    rva = insn.address - base
    mnem = insn.mnemonic
    ops = insn.op_str

    marker = ""
    if insn.address == call_addr:
        marker = "  <<<< SETKEYBOARDCONFIG CALL SITE (hooked)"
    elif mnem == "call":
        calls.append((rva, ops))
        marker = "  << CALL"
    elif mnem in ("jz", "jnz", "je", "jne", "jmp", "ret"):
        marker = f"  << {mnem.upper()}"
    elif "fs:" in ops or "gs:" in ops:
        marker = "  << TEB/TEB access"

    # Highlight CreateFile-like patterns
    if "0x79ccd" in ops and mnem == "call":
        marker += " (IAT)"

    print(f"  0x{rva:05X}:  {mnem:8s} {ops:40s}{marker}")

print(f"\n{'='*70}")
print(f"Calls found: {len(calls)}")
for rva, ops in calls:
    print(f"  @0x{rva:05X}: call {ops}")

kernel32.CloseHandle(hProc)
