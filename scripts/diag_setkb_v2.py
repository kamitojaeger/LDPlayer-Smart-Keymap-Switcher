"""Diagnostic v2: disassemble setKeyboardConfig + dump CInputMgr state.

Avoids MODULEENTRY32W alignment crash by using known offsets from --status.
"""
import ctypes, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# Known values from injector --status output
# FuncAddress = dnplycore_base + FUNC_RVA
# 0x79CA6130 - 0x96130 = 0x79C10000 (NOT 0x79C13000 — careful with hex subtraction!)
DNPLYCORE_BASE = 0x79C10000
SAVED_INSTANCE = 0x07858620   # CInputMgr this pointer (from shared mem savedInstance)
FUNC_RVA = 0x96130
FUNC_SIZE = 512

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

def read_mem(hProc, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
    return buf.raw[:br.value] if ok else b""

def find_pid():
    import subprocess
    r = subprocess.run(["tasklist", "/fi", "IMAGENAME eq dnplayer.exe", "/fo", "csv", "/nh"],
                       capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        if "dnplayer.exe" in line.lower():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 2:
                return int(parts[1].strip())
    return 0

pid = find_pid()
print(f"dnplayer PID: {pid}")
print(f"dnplycore.dll base: 0x{DNPLYCORE_BASE:08X}")
print(f"savedInstance (CInputMgr): 0x{SAVED_INSTANCE:08X}")

hProc = kernel32.OpenProcess(0x10, False, pid)  # PROCESS_VM_READ
assert hProc, f"OpenProcess failed: {ctypes.get_last_error()}"

# ── 1. Disassemble setKeyboardConfig ──
func_addr = DNPLYCORE_BASE + FUNC_RVA
code = read_mem(hProc, func_addr, FUNC_SIZE)
print(f"\n{'='*70}")
print(f"setKeyboardConfig @ 0x{func_addr:08X} (RVA 0x{FUNC_RVA:05X})")
print(f"Read {len(code)} bytes")
print(f"{'='*70}")

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

calls = []
branches = []
early_returns = []

for insn in md.disasm(code, func_addr):
    rva = insn.address - DNPLYCORE_BASE
    mnem = insn.mnemonic
    ops = insn.op_str

    marker = ""
    if mnem == "call":
        calls.append((rva, ops))
        marker = "  << CALL"
    elif mnem in ("jz", "jnz", "je", "jne", "jmp", "jl", "jle", "jg", "jge", "jb", "jbe", "ja", "jae"):
        branches.append((rva, mnem, ops))
        marker = f"  << {mnem.upper()}"
    elif mnem == "ret":
        early_returns.append((rva, "ret"))
        marker = "  << RETURN"

    # Stop at next function prologue (push ebp; mov ebp,esp) after some instructions
    func_offset = rva - FUNC_RVA  # offset from function start
    if func_offset > 0x40 and mnem == "push" and ops == "ebp":
        print(f"  [next function at +0x{func_offset:X} (RVA 0x{rva:05X}), stopping]")
        break

    print(f"  0x{rva:05X}:  {mnem:8s} {ops:35s}{marker}")

print(f"\n{'='*70}")
print(f"Summary: {len(calls)} calls, {len(branches)} branches, {len(early_returns)} returns")
print(f"\nCalls:")
for rva, ops in calls:
    print(f"  @0x{rva:05X}: call {ops}")
print(f"\nBranches:")
for rva, mnem, ops in branches:
    print(f"  @0x{rva:05X}: {mnem} {ops}")

# ── 2. Dump CInputMgr object ──
print(f"\n{'='*70}")
print(f"CInputMgr @ 0x{SAVED_INSTANCE:08X} (first 512 bytes)")
print(f"{'='*70}")

obj = read_mem(hProc, SAVED_INSTANCE, 512)
if obj:
    for row in range(0, min(len(obj), 512), 16):
        addr = SAVED_INSTANCE + row
        line = obj[row:row+16]
        hx = " ".join(f"{b:02X}" for b in line)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in line)
        dwords = []
        for i in range(0, min(16, len(line)), 4):
            if i + 4 <= len(line):
                val = struct.unpack("<I", line[i:i+4])[0]
                if 0x03000000 <= val <= 0x21000000:
                    dwords.append(f" [+0x{row+i:03X}]=0x{val:08X}(HEAP)")
                elif val != 0 and val < 0x1000:
                    dwords.append(f" [+0x{row+i:03X}]={val}")
        dstr = "".join(dwords)
        print(f"  0x{addr:08X} (+0x{row:03X}): {hx:48s} |{asc}|{dstr}")
else:
    print("  [read failed]")

kernel32.CloseHandle(hProc)
