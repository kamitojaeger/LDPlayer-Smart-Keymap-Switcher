"""Diagnostic v3: check IAT entries + disassemble sub-function 0x036F0.

IAT entries used by setKeyboardConfig:
  [0x79ccd1f8] - call at 0x9619D
  [0x79ccd1ec] - call at 0x961C7

Also disassemble sub-function 0x036F0 (called twice by setKeyboardConfig)
to find if it uses CreateFileW or CreateFileA.
"""
import ctypes, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DNPLYCORE_BASE = 0x79C10000
SAVED_INSTANCE = 0x07858620
FUNC_RVA = 0x96130
SUBFUNC_RVA = 0x036F0

# IAT entries referenced in setKeyboardConfig
IAT_ENTRIES = [
    (0x79ccd1f8, "IAT call #1 (0x9619D) - main body"),
    (0x79ccd1ec, "IAT call #2 (0x961C7) - cleanup"),
    (0x79ccd1f4, "IAT entry mentioned in dev plan"),
]

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

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

def read_mem(hProc, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
    return buf.raw[:br.value] if ok else b""

pid = find_pid()
hProc = kernel32.OpenProcess(0x10, False, pid)
assert hProc

# ── 1. Read IAT entry values ──
print("="*60)
print("IAT entries (pointers to imported functions)")
print("="*60)
for iat_addr, desc in IAT_ENTRIES:
    data = read_mem(hProc, iat_addr, 4)
    if data and len(data) == 4:
        func_addr = struct.unpack("<I", data)[0]
        print(f"  [{iat_addr:08X}] -> 0x{func_addr:08X}  ({desc})")

        # Try to identify the function by reading nearby bytes
        # Look for the function's DLL module
        # Read first 16 bytes of the target function
        fbytes = read_mem(hProc, func_addr, 32)
        if fbytes:
            hx = " ".join(f"{b:02X}" for b in fbytes[:16])
            print(f"    first bytes: {hx}")
    else:
        print(f"  [{iat_addr:08X}] - read failed ({desc})")

# ── 2. Disassemble sub-function 0x036F0 ──
print(f"\n{'='*60}")
print(f"Sub-function @ RVA 0x{SUBFUNC_RVA:05X} (0x{DNPLYCORE_BASE + SUBFUNC_RVA:08X})")
print(f"{'='*60}")

sub_addr = DNPLYCORE_BASE + SUBFUNC_RVA
code = read_mem(hProc, sub_addr, 1024)

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

calls_in_sub = []
createfile_found = False

for insn in md.disasm(code, sub_addr):
    rva = insn.address - DNPLYCORE_BASE
    func_offset = rva - SUBFUNC_RVA
    mnem = insn.mnemonic
    ops = insn.op_str

    marker = ""
    if mnem == "call":
        calls_in_sub.append((rva, ops))
        marker = "  << CALL"
    elif mnem in ("jz", "jnz", "je", "jne", "jmp", "ret"):
        marker = f"  << {mnem.upper()}"

    # Stop at next function prologue
    if func_offset > 0x40 and mnem == "push" and ops == "ebp":
        print(f"  [next function at +0x{func_offset:X}, stopping]")
        break

    # Stop at ret followed by int3 padding
    if mnem == "ret" and func_offset > 0x10:
        print(f"  0x{rva:05X}:  {mnem:8s} {ops:35s}{marker}")
        # Check if next bytes are int3 (padding)
        next_offset = insn.address + insn.size - sub_addr
        if next_offset < len(code) and code[next_offset] == 0xCC:
            print(f"  [function end at +0x{func_offset:X}]")
            break

    print(f"  0x{rva:05X}:  {mnem:8s} {ops:35s}{marker}")

print(f"\nCalls in sub-function: {len(calls_in_sub)}")
for rva, ops in calls_in_sub:
    print(f"  @0x{rva:05X}: call {ops}")

kernel32.CloseHandle(hProc)
