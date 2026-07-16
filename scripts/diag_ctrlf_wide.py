"""Disassemble a wider region around the Ctrl+F handler to find the .kmp
file listing / counting logic that decides cycle vs dropdown.

We know the CALL site is at RVA 0x1DA53. The handler starts somewhere
before. Let's dump 4KB before the call site to find the function entry
and any directory scanning / file counting code.
"""
import ctypes, struct, subprocess
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DNPLYCORE_BASE = 0x79C10000
CALL_RVA = 0x1DA53
DUMP_BEFORE = 8192  # 8KB before call site

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

pid = find_pid()
hProc = kernel32.OpenProcess(0x10, False, pid)
assert hProc

call_addr = DNPLYCORE_BASE + CALL_RVA
start = call_addr - DUMP_BEFORE
code = read_mem(hProc, start, DUMP_BEFORE + 32)

print(f"PID: {pid}")
print(f"Searching 8KB before CALL site (0x{call_addr:08X}) for directory/file operations...")

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

instructions = list(md.disasm(code, start))

# Look for function prologues (push ebp; mov ebp, esp) to find function boundaries
prologues = []
for i, insn in enumerate(instructions):
    rva = insn.address - DNPLYCORE_BASE
    if (insn.mnemonic == "push" and insn.op_str == "ebp" and
        i + 1 < len(instructions) and instructions[i+1].mnemonic == "mov" and
        instructions[i+1].op_str == "ebp, esp"):
        prologues.append((rva, insn.address))

print(f"\nFunction prologues found in 8KB window: {len(prologues)}")
for rva, addr in prologues:
    print(f"  0x{rva:05X} (0x{addr:08X})")

# The Ctrl+F handler function likely starts at one of these prologues.
# Find the closest one before the CALL site.
closest_prologue = None
for rva, addr in prologues:
    if addr < call_addr:
        closest_prologue = (rva, addr)

if closest_prologue:
    func_start_rva, func_start_addr = closest_prologue
    print(f"\nClosest function start before CALL: 0x{func_start_rva:05X}")
    print(f"Function size: ~{call_addr - func_start_addr} bytes")

# Now scan ALL calls and IAT references in this region for file/dir operations
print(f"\n{'='*70}")
print("All CALL instructions in the Ctrl+F handler region")
print(f"{'='*70}")

call_targets = {}  # target_addr -> count
for insn in instructions:
    rva = insn.address - DNPLYCORE_BASE
    if insn.mnemonic == "call":
        # Parse call target
        ops = insn.op_str
        if ops.startswith("0x"):
            try:
                target = int(ops, 16)
                target_rva = target - DNPLYCORE_BASE
                call_targets[target_rva] = call_targets.get(target_rva, 0) + 1
            except:
                pass
        elif "dword ptr [0x79ccd" in ops:
            # IAT call
            try:
                iat_addr = int(ops.replace("dword ptr [", "").replace("]", ""), 16)
                call_targets[iat_addr] = call_targets.get(iat_addr, 0) + 1
            except:
                pass

print(f"\nUnique call targets: {len(call_targets)}")
for target, count in sorted(call_targets.items()):
    label = ""
    if 0x79ccd0000 <= target <= 0x79ccdffff:
        label = " (IAT)"
    print(f"  0x{target:08X}: {count} call(s){label}")

kernel32.CloseHandle(hProc)
