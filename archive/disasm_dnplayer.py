"""Disassemble dnplayer.exe key addresses from the call stack."""
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplayer.exe"
pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase

print(f"dnplayer.exe ImageBase: 0x{IB:08X}")
print(f"Size of code: 0x{pe.OPTIONAL_HEADER.SizeOfCode:X}")

# Runtime addresses from x32dbg call stack
# Need to figure out the runtime base. The PE ImageBase may differ from runtime.
# From the call stack, dnplayer addresses are 0x0092xxxx-0x00B5xxxx
# If ImageBase=0x400000, RVAs would be 0x52xxxx-0x75xxxx
runtime_addrs = [0x0092E3AF, 0x0092E5AA, 0x0092F5FA, 0x009D34CA, 0x00A09735]

# Try to find the runtime base by checking which base makes these addresses
# fall within the .text section
for section in pe.sections:
    print(f"  Section {section.Name.strip(b'\\x00').decode():8s} VA=0x{section.VirtualAddress:08X} Size=0x{section.Misc_VirtualSize:08X} Raw=0x{section.PointerToRawData:08X}")

# The most likely scenario: ASLR is enabled, runtime base = ImageBase + slide
# But for analysis, we can compute RVA = runtime_addr - runtime_base
# Let's try: if the PE has ImageBase=0x400000, and the code section starts at 0x1000
# then runtime RVA = runtime_addr - runtime_base
# We need to find runtime_base. From x32dbg, we could read it, but let's try
# assuming the base is such that 0x0092E3AF falls in .text

# Let's try different bases
text_section = pe.sections[0]
text_rva_start = text_section.VirtualAddress
text_rva_end = text_section.VirtualAddress + text_section.Misc_VirtualSize

# Try: runtime_base = 0x00400000 (default)
for base_try in [0x00400000, 0x00500000, 0x00600000, 0x00700000, 0x00800000, 0x00900000, 0x003F0000, 0x00410000]:
    rva = 0x0092E3AF - base_try
    if text_rva_start <= rva < text_rva_end:
        print(f"\n*** Likely runtime base: 0x{base_try:08X} (RVA of 0x0092E3AF = 0x{rva:05X}) ***")
        runtime_base = base_try
        break
else:
    # Try to compute from the PE's preferred base
    print(f"\nCould not auto-detect runtime base. Using ImageBase 0x{IB:08X}")
    runtime_base = IB

# Now disassemble each address
for addr in runtime_addrs:
    rva = addr - runtime_base
    if rva < 0 or rva >= text_rva_end:
        print(f"\nAddress 0x{addr:08X}: RVA 0x{rva:X} out of range, trying ImageBase")
        rva = addr - IB
        runtime_base = IB

    if rva < 0:
        continue

    print(f"\n{'='*60}")
    print(f"dnplayer+0x{rva:05X} (runtime 0x{addr:08X})")
    print(f"{'='*60}")

    # Read 100 bytes before and 50 after
    start_rva = max(0, rva - 80)
    size = 130
    try:
        data = pe.get_data(start_rva, size)
    except:
        print("  (could not read data)")
        continue

    for insn in md.disasm(data, runtime_base + start_rva):
        insn_rva = insn.address - runtime_base
        ann = ""
        if insn.mnemonic == 'call':
            ann = "  ; call"
        if insn.mnemonic == 'ret':
            ann = "  ; RET"
        if insn.address == addr:
            ann += "  <<< FROM CALL STACK"
        print(f"  {insn_rva:05X}  {insn.bytes.hex():24s} {insn.mnemonic:8s} {insn.op_str}{ann}")
        if insn_rva > rva + 20:
            break
