"""Static analysis of setKeyboardConfig (RVA 0x96130) in dnplycore.dll.

Goal: Find the thread-safety check and identify the internal sub-function
that actually applies keymap data, bypassing the check.
"""
import ctypes, struct
from ctypes import wintypes
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

PID = 16948
FUNC_RVA = 0x96130
FUNC_SIZE = 0x2000  # read 8KB — generous for function + sub-functions

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

# ── Get dnplycore base ──
TH32CS_SNAPMODULE = 0x8 | 0x10
snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, PID)
assert snap != -1

buf = ctypes.create_string_buffer(1080)
ctypes.c_uint32.from_address(ctypes.addressof(buf)).value = 1080
dnplycore = 0
if kernel32.Module32FirstW(snap, buf):
    while True:
        name = ctypes.c_wchar_p(ctypes.addressof(buf) + 48).value
        if name and name.lower() == "dnplycore.dll":
            dnplycore = ctypes.c_uint32.from_address(ctypes.addressof(buf) + 24).value
            break
        ctypes.c_uint32.from_address(ctypes.addressof(buf)).value = 1080
        if not kernel32.Module32NextW(snap, buf):
            break
kernel32.CloseHandle(snap)
print(f"dnplycore.dll base: 0x{dnplycore:08X}")

# ── Read function bytes ──
hProc = kernel32.OpenProcess(0x10 | 0x400, False, PID)
assert hProc

func_addr = dnplycore + FUNC_RVA
raw = ctypes.create_string_buffer(FUNC_SIZE)
br = ctypes.c_size_t(0)
kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(func_addr), raw, FUNC_SIZE, ctypes.byref(br))
code = raw.raw[:br.value]
kernel32.CloseHandle(hProc)
print(f"Read {len(code)} bytes from 0x{func_addr:08X}")

# ── Disassemble ──
print(f"\n{'='*70}")
print(f"setKeyboardConfig @ RVA 0x{FUNC_RVA:05X}")
print(f"{'='*70}")

instructions = list(md.disasm(code, func_addr))
call_targets = []  # (address, target_rva, instruction)
jump_targets = []
thread_checks = []
interesting_calls = []

for insn in instructions:
    rva = insn.address - dnplycore
    
    # Format instruction
    mnem = insn.mnemonic
    ops = insn.op_str
    
    # Highlight CALL instructions
    marker = ""
    if mnem == "call":
        try:
            target = int(ops, 16) if ops.startswith("0x") else None
            if target:
                target_rva = target - dnplycore
                call_targets.append((insn.address, target_rva, ops))
                marker = f"  ← CALL → RVA 0x{target_rva:05X}"
        except:
            pass
    
    # Look for thread check patterns
    if "dword ptr [fs:0x18]" in ops or "gs:" in ops:  # TEB access
        marker += "  ← TEB (thread check?)"
        thread_checks.append((rva, insn))
    
    if mnem == "call" and "GetCurrentThreadId" in ops:
        marker += "  ← GetCurrentThreadId!"
        thread_checks.append((rva, insn))
    
    line = f"  0x{rva:05X}:  {mnem:8s} {ops:30s}{marker}"
    print(line)

# ── Summary ──
print(f"\n{'='*70}")
print(f"Summary: {len(instructions)} instructions")
print(f"Function size: ~{instructions[-1].address - func_addr + instructions[-1].size} bytes")
print(f"CALL targets: {len(call_targets)}")
for addr, target_rva, ops in call_targets:
    local_rva = addr - dnplycore
    print(f"  @ 0x{local_rva:05X}: call 0x{target_rva:05X}")
