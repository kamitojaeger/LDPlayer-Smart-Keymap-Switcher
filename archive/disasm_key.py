"""Disassemble key dnplycore.dll addresses to understand .kmp read logic."""
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplycore.dll"
RVAS = [0x510B3, 0x5261D, 0xBFD4E, 0x52500]

pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True

def rva_to_offset(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

# Also find CreateFileW IAT entry to identify calls to it
pe.parse_data_directories()
createfile_iat = []
if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dll_name = entry.dll.decode(errors='replace')
        for imp in entry.imports:
            if imp.name and 'CreateFileW' in imp.name.decode(errors='replace'):
                createfile_iat.append((dll_name, imp.name.decode(), imp.address, imp.address - pe.OPTIONAL_HEADER.ImageBase))
                print(f"IAT: {dll_name}!{imp.name.decode()} at VA=0x{imp.address:08X} RVA=0x{imp.address - pe.OPTIONAL_HEADER.ImageBase:05X}")

print(f"\nImageBase: 0x{pe.OPTIONAL_HEADER.ImageBase:08X}")
print(f"Code section: .text RVA=0x{pe.sections[0].VirtualAddress:08X} size=0x{pe.sections[0].Misc_VirtualSize:08X}")

for rva in RVAS:
    off = rva_to_offset(rva)
    if off is None:
        print(f"\n=== RVA 0x{rva:05X}: not in any section ===")
        continue
    print(f"\n=== dnplycore+0x{rva:05X} (file offset 0x{off:X}) ===")
    # Read 64 bytes before and 32 after to see context
    start = max(0, off - 64)
    size = 96
    data = pe.get_data(rva - 64 if rva >= 64 else 0, size)
    base_rva = rva - 64 if rva >= 64 else 0
    for insn in md.disasm(data, pe.OPTIONAL_HEADER.ImageBase + base_rva):
        marker = " <-- RETURN ADDR" if insn.address == pe.OPTIONAL_HEADER.ImageBase + rva else ""
        if insn.mnemonic == 'call':
            # Try to resolve call target
            marker += f"  ; call"
        print(f"  0x{insn.address:08X} ({insn.address - pe.OPTIONAL_HEADER.ImageBase:05X})  {insn.bytes.hex():30s} {insn.mnemonic} {insn.op_str}{marker}")
