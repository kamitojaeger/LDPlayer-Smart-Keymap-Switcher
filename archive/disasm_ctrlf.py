"""Disassemble Ctrl+F handler around 0x20100-0x201A0 to find 'next' decision."""
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplycore.dll"
pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase

# Disassemble 0x200F0 to 0x201B0 (Ctrl+F handler)
print("="*70)
print("Ctrl+F HANDLER (dnplycore+0x200F0 to 0x201B0)")
print("="*70)
data = pe.get_data(0x200F0, 0xC0)
for insn in md.disasm(data, IB + 0x200F0):
    rva = insn.address - IB
    ann = ""
    if insn.mnemonic == 'call':
        ann = "  ; call"
    if insn.mnemonic == 'push':
        # Check if pushing a string address
        try:
            val = int(insn.op_str, 16)
            if 0x10000000 <= val < 0x10100000:
                # Try to read string at this address
                str_rva = val - IB
                try:
                    s = pe.get_data(str_rva, 80)
                    # Try ANSI
                    ansi = s.split(b'\x00')[0].decode('ascii', errors='replace')
                    if len(ansi) > 3 and all(32 <= ord(c) < 127 for c in ansii if c) if False else len(ansi) > 3:
                        ann = f"  ; push \"{ansi}\""
                except:
                    pass
        except:
            pass
    if 0x20190 <= rva <= 0x2019C:
        ann += "  <<< Ctrl+F 'next' decision area"
    if rva == 0x2019C:
        ann = "  <<< call setKeyboardConfig"
    print(f"  {rva:05X}  {insn.bytes.hex():30s} {insn.mnemonic:8s} {insn.op_str}{ann}")

# Also disassemble around 0x20150-0x20160 (just before the call chain)
print(f"\n{'='*70}")
print("WIDER CONTEXT (dnplycore+0x20100 to 0x201A0)")
print("="*70)
data2 = pe.get_data(0x20100, 0xA0)
for insn in md.disasm(data2, IB + 0x20100):
    rva = insn.address - IB
    ann = ""
    if rva == 0x20190:
        ann = "  <<< push 0 (arg for setKeyboardConfig)"
    if rva == 0x2019C:
        ann = "  <<< call setKeyboardConfig"
    print(f"  {rva:05X}  {insn.mnemonic:8s} {insn.op_str}{ann}")
