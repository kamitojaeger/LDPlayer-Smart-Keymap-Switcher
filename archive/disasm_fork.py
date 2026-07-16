"""Disassemble the AAA/BBB fork point at dnplayer+0x229735 (base=0x7E0000)."""
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplayer.exe"
pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)

# Runtime base = 0x007E0000 (ImageBase 0x400000 + ASLR slide 0x3E0000)
BASE = 0x007E0000

# Key addresses from call stack comparison:
# Fork point:  00A09735 → RVA 0x229735
# AAA path:    00A05431 → RVA 0x225431
# BBB path:    00A05D55 → RVA 0x225D55
# Caller:      009D34CA → RVA 0x1F34CA

addrs = {
    0x229735: "FORK POINT (decides AAA vs BBB)",
    0x225431: "AAA PATH (read current scheme)",
    0x225D55: "BBB PATH (read next scheme)",
    0x1F34CA: "CALLER of fork point",
}

for rva, label in addrs.items():
    print(f"\n{'='*70}")
    print(f"dnplayer+0x{rva:05X} — {label}")
    print(f"{'='*70}")
    # Read 120 bytes before and 40 after
    start = max(0, rva - 120)
    size = 160
    data = pe.get_data(start, size)
    for insn in md.disasm(data, BASE + start):
        insn_rva = insn.address - BASE
        ann = ""
        if insn.mnemonic == 'call':
            ann = "  ; CALL"
        if insn.mnemonic == 'ret':
            ann = "  ; RET"
        if insn.mnemonic in ('je', 'jne', 'jz', 'jnz', 'jmp', 'jl', 'jg', 'jle', 'jge', 'jb', 'ja'):
            ann = f"  ; {insn.mnemonic.upper()}"
        if insn.address == BASE + rva:
            ann += "  <<< TARGET"
        print(f"  {insn_rva:05X}  {insn.bytes.hex():24s} {insn.mnemonic:8s} {insn.op_str}{ann}")
        if insn_rva > rva + 20:
            break
