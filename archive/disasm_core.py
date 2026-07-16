"""Disassemble the core keymap function at 0x03C60."""
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplycore.dll"
pe = pefile.PE(DLL, fast_load=True)
pe.parse_data_directories()
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase
CFW_IAT_RVA = 0xC710C

# Find function end by looking for ret + int3 padding
data = pe.get_data(0x03C60, 0x800)  # read up to 2KB

print("="*70)
print("CORE FUNCTION at dnplycore+0x03C60 (the real keymap switch engine)")
print("="*70)

# Disassemble and look for key patterns
import struct
text_data = pe.get_data(pe.sections[0].VirtualAddress, pe.sections[0].Misc_VirtualSize)

for insn in md.disasm(data, IB + 0x03C60):
    rva = insn.address - IB
    ann = ""
    if insn.mnemonic == 'call':
        # Check IAT calls
        if '0x100c710c' in insn.op_str:
            ann = "  ; >>> CreateFileW <<<"
        elif 'dword ptr [0x100' in insn.op_str:
            try:
                val = int(insn.op_str.split('[')[1].split(']')[0], 16) - IB
                ann = f"  ; call [IAT 0x{val:X}]"
            except:
                ann = "  ; call"
        else:
            ann = "  ; call"
    if insn.mnemonic == 'ret':
        ann = "  ; RET (function end)"
    if insn.mnemonic in ('inc', 'dec', 'add') and 'esi' in insn.op_str:
        ann += "  ; <<< INDEX CHANGE?"
    if insn.mnemonic == 'cmp':
        ann += "  ; compare"
    print(f"  {rva:05X}  {insn.bytes.hex():30s} {insn.mnemonic:8s} {insn.op_str}{ann}")
    # Stop at function end (ret followed by int3 padding)
    if insn.mnemonic == 'ret' and rva > 0x03C80:
        # Check if next bytes are int3 (0xCC)
        next_off = rva - 0x03C60 + insn.size
        if next_off < len(data) and data[next_off] == 0xCC:
            print(f"  (function ends at 0x{rva:05X})")
            break
