"""Deep analysis of setKeyboardConfig internals.
Focus: sub-function @ RVA 0x036F0, large function @ 0x961F0, 
and exported functions in the IAT.
"""
import ctypes, struct
from ctypes import wintypes
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

PID = 16948
dnplycore = 0x6BD10000  # from previous run

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

hProc = kernel32.OpenProcess(0x10 | 0x400, False, PID)
assert hProc

def read_code(rva, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    addr = dnplycore + rva
    kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
    return buf.raw[:br.value]

def disasm(rva, size, label=""):
    code = read_code(rva, size)
    print(f"\n{'='*70}")
    print(f"{label} @ RVA 0x{rva:05X} ({len(code)} bytes)")
    print(f"{'='*70}")
    instructions = list(md.disasm(code, dnplycore + rva))
    
    calls = []
    for insn in instructions:
        local_rva = insn.address - dnplycore
        mnem = insn.mnemonic
        ops = insn.op_str
        marker = ""
        
        if mnem == "call":
            try:
                target = int(ops, 16) if ops.startswith("0x") else None
                if target:
                    trva = target - dnplycore
                    calls.append((local_rva, trva))
                    marker = f"  ← call 0x{trva:05X}"
            except:
                marker = f"  ← call {ops}"
        
        if mnem == "ret":
            marker += "  ← RETURN"
        
        # Highlight thread-related
        if "fs:0x18" in ops or "TEB" in str(insn):
            marker += "  ← TEB"
        if "GetCurrentThreadId" in str(insn):
            marker += "  ← THREAD CHECK"
        
        print(f"  0x{local_rva:05X}:  {mnem:8s} {ops:35s}{marker}")
    
    print(f"\n  → {len(instructions)} instructions, {len(calls)} calls")
    return calls

# 1. Sub-function 0x036F0
disasm(0x036F0, 0x400, "Sub-function @ 0x036F0 (called by setKeyboardConfig)")

# 2. Large function 0x961F0 (right after setKeyboardConfig)
disasm(0x961F0, 0x1000, "Large function @ 0x961F0 (adjacent)")

# 3. Also check what CALLs to 0x961F0 in the whole DLL
print(f"\n{'='*70}")
print("Searching for CALLs to large function 0x961F0...")
print(f"{'='*70}")
# Read a portion of the text section to find CALL targets
for search_start, search_size in [(0x1000, 0x80000), (0x90000, 0x8000)]:
    code = read_code(search_start, search_size)
    for i in range(len(code) - 5):
        if code[i] == 0xE8:  # CALL rel32
            rel = struct.unpack('<i', code[i+1:i+5])[0]
            call_rva = search_start + i
            target_rva = call_rva + 5 + rel
            if target_rva == 0x961F0:
                print(f"  CALL @ 0x{call_rva:05X} → 0x961F0")

kernel32.CloseHandle(hProc)
