"""Disassemble the .kmp read function and its caller."""
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplycore.dll"
pe = pefile.PE(DLL, fast_load=True)
pe.parse_data_directories()
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase  # 0x10000000

# CreateFileW IAT RVA
CFW_IAT_RVA = 0xC710C

def disasm_range(rva_start, size, label=""):
    data = pe.get_data(rva_start, size)
    if label:
        print(f"\n{'='*60}")
        print(f"{label}")
        print(f"{'='*60}")
    for insn in md.disasm(data, IB + rva_start):
        rva = insn.address - IB
        ann = ""
        if insn.mnemonic == 'call':
            # Check if call target is CreateFileW IAT
            if insn.op_str.startswith('dword ptr [0x'):
                target = int(insn.op_str.replace('dword ptr [','').replace(']',''), 16) - IB
                if target == CFW_IAT_RVA:
                    ann = "  ; >>> CreateFileW <<<"
                else:
                    ann = f"  ; call [IAT 0x{target:X}]"
            else:
                ann = f"  ; call"
        if insn.mnemonic == 'ret':
            ann += f"  ; RET"
        print(f"  {rva:05X}  {insn.bytes.hex():24s} {insn.mnemonic:8s} {insn.op_str}{ann}")

# 1. Caller context: 0x510B3 is the return address after call to 0x52500
# Disassemble 0x51060 to 0x510E0 to see the call and surrounding logic
disasm_range(0x51060, 0x80, "CALLER CONTEXT (around 0x510B3)")

# 2. The function at 0x52500 — full body
disasm_range(0x52500, 0x124, "FUNCTION 0x52500 (full body to ret)")

# 3. Search for all calls to CreateFileW IAT in the .text section
print(f"\n{'='*60}")
print(f"CALLS TO CreateFileW (IAT RVA 0x{CFW_IAT_RVA:X})")
print(f"{'='*60}")
text = pe.sections[0]
text_data = pe.get_data(text.VirtualAddress, text.Misc_VirtualSize)
# Search for "ff 15" (call dword ptr [imm32]) patterns targeting CFW_IAT
import struct
cfw_va = struct.pack('<I', IB + CFW_IAT_RVA)
pos = 0
while True:
    idx = text_data.find(b'\xff\x15' + cfw_va, pos)
    if idx < 0:
        break
    call_rva = text.VirtualAddress + idx
    # Disassemble a few instructions before the call for context
    ctx_start = max(0, idx - 40)
    ctx_data = text_data[ctx_start:idx + 6]
    print(f"\n  call CreateFileW at dnplycore+0x{call_rva:05X}")
    for insn in md.disasm(ctx_data, IB + text.VirtualAddress + ctx_start):
        rva = insn.address - IB
        marker = " <-- CALL CreateFileW" if rva == call_rva else ""
        print(f"    {rva:05X}  {insn.mnemonic:8s} {insn.op_str}{marker}")
    pos = idx + 6
