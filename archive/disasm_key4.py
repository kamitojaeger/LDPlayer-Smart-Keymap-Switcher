"""Find callers of 0xB8A90 and disassemble the .kmp read function at 0x503xx."""
import pefile, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplycore.dll"
pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase
text = pe.sections[0]
text_data = pe.get_data(text.VirtualAddress, text.Misc_VirtualSize)

# 1. Find callers of 0xB8A90
print("="*60)
print("CALLERS OF 0xB8A90 (file-open wrapper caller)")
print("="*60)
for pos in range(len(text_data) - 5):
    if text_data[pos] == 0xE8:
        rel = struct.unpack('<i', text_data[pos+1:pos+5])[0]
        call_rva = text.VirtualAddress + pos
        dest = call_rva + 5 + rel
        if dest == 0xB8A90:
            ctx_start = max(0, pos - 80)
            ctx_data = text_data[ctx_start:pos + 5]
            print(f"\n  call 0xB8A90 at dnplycore+0x{call_rva:05X}")
            for insn in md.disasm(ctx_data, IB + text.VirtualAddress + ctx_start):
                rva = insn.address - IB
                m = " <-- CALL" if rva == call_rva else ""
                print(f"    {rva:05X}  {insn.mnemonic:8s} {insn.op_str}{m}")

# 2. Disassemble the function containing 0x50419 (the other GENERIC_READ)
# Search backwards for function prologue (push ebp; mov ebp, esp)
print(f"\n{'='*60}")
print("FUNCTION CONTAINING 0x50419 (GENERIC_READ CreateFileW)")
print(f"{'='*60}")
# Scan backwards from 0x50419 for 'cc cc' (int3 padding) or 'push ebp'
for offset in range(0x50419 - text.VirtualAddress, 0, -1):
    if text_data[offset] == 0xCC and text_data[offset-1] == 0xCC:
        func_start_rva = text.VirtualAddress + offset + 1
        break
else:
    func_start_rva = 0x50380

# Disassemble from func_start to past 0x50419
end_rva = 0x50460
data = pe.get_data(func_start_rva, end_rva - func_start_rva)
print(f"Function starts at dnplycore+0x{func_start_rva:05X}")
for insn in md.disasm(data, IB + func_start_rva):
    rva = insn.address - IB
    ann = ""
    if insn.mnemonic == 'call':
        if '0x100c710c' in insn.op_str:
            ann = "  ; >>> CreateFileW <<<"
        else:
            ann = "  ; call"
    if insn.mnemonic == 'ret':
        ann = "  ; RET"
    print(f"  {rva:05X}  {insn.bytes.hex():24s} {insn.mnemonic:8s} {insn.op_str}{ann}")
    if rva >= 0x50430:
        break
