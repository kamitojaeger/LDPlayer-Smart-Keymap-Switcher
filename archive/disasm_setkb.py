"""Disassemble setKeyboardConfig (0x9CA10) fully to find 'next' index logic."""
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplycore.dll"
pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase

print("="*70)
print("setKeyboardConfig (dnplycore+0x9CA10) — full disassembly")
print("="*70)
# Function is large (sub esp, 0x114). Disassemble 0x9CA10 to 0x9CB20
data = pe.get_data(0x9CA10, 0x110)
for insn in md.disasm(data, IB + 0x9CA10):
    rva = insn.address - IB
    ann = ""
    if insn.mnemonic == 'call':
        ann = "  ; call"
    if insn.mnemonic == 'ret':
        ann = "  ; RET"
    if insn.mnemonic == 'je' or insn.mnemonic == 'jne':
        ann = f"  ; {insn.mnemonic}"
    print(f"  {rva:05X}  {insn.bytes.hex():30s} {insn.mnemonic:8s} {insn.op_str}{ann}")
