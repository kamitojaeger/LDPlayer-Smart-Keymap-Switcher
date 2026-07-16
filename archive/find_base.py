"""Find the correct runtime base of dnplayer.exe by matching call return addresses."""
import pefile, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplayer.exe"
pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase  # 0x400000

text = pe.sections[0]
text_data = pe.get_data(text.VirtualAddress, text.Misc_VirtualSize)

# Target runtime addresses from call stack (return addresses after call)
targets = [0x0092E3AF, 0x0092E5AA, 0x0092F5FA, 0x009D34CA, 0x00A09735]

# For each E8 (call rel32) in .text, the return address = call_addr + 5
# If return_addr + base = target, then base = target - return_addr
# where return_addr = text.VA + offset + 5
# So base = target - (text.VA + offset + 5)

# Scan for E8 calls and compute possible bases
bases = set()
for off in range(len(text_data) - 5):
    if text_data[off] == 0xE8:
        call_rva = text.VirtualAddress + off
        ret_rva = call_rva + 5
        for target in targets:
            base = target - ret_rva
            if 0x400000 <= base <= 0xC00000:  # reasonable range
                bases.add(base)

# Also check FF 15 (call indirect) - 6 bytes
for off in range(len(text_data) - 6):
    if text_data[off] == 0xFF and text_data[off+1] == 0x15:
        call_rva = text.VirtualAddress + off
        ret_rva = call_rva + 6
        for target in targets:
            base = target - ret_rva
            if 0x400000 <= base <= 0xC00000:
                bases.add(base)

print(f"Found {len(bases)} candidate bases")
# Find bases that match ALL targets
valid_bases = []
for base in sorted(bases):
    # Check if all targets have a call instruction before them
    all_match = True
    for target in targets:
        ret_rva = target - base
        if ret_rva < 5 or ret_rva >= len(text_data) + text.VirtualAddress:
            all_match = False
            break
        # Check if 5 bytes before ret_rva is E8 or 6 bytes before is FF 15
        off = ret_rva - text.VirtualAddress - 5
        if off >= 0 and off < len(text_data) and text_data[off] == 0xE8:
            continue  # E8 call
        off2 = ret_rva - text.VirtualAddress - 6
        if off2 >= 0 and off2 < len(text_data) and text_data[off2] == 0xFF and text_data[off2+1] == 0x15:
            continue  # FF 15 call
        all_match = False
        break
    if all_match:
        valid_bases.append(base)
        print(f"  VALID base: 0x{base:08X}")

if not valid_bases:
    print("No base matches ALL targets. Showing bases matching at least 3:")
    for base in sorted(bases):
        count = 0
        for target in targets:
            ret_rva = target - base
            off = ret_rva - text.VirtualAddress - 5
            if off >= 0 and off < len(text_data) and text_data[off] == 0xE8:
                count += 1
            off2 = ret_rva - text.VirtualAddress - 6
            if off2 >= 0 and off2 < len(text_data) and text_data[off2] == 0xFF and text_data[off2+1] == 0x15:
                count += 1
        if count >= 3:
            print(f"  base 0x{base:08X}: {count}/{len(targets)} matches")

# Use the best base to disassemble the fork point
best = valid_bases[0] if valid_bases else None
if not best:
    # Try to find the most common base
    from collections import Counter
    base_counts = Counter()
    for base in bases:
        count = 0
        for target in targets:
            ret_rva = target - base
            off = ret_rva - text.VirtualAddress - 5
            if off >= 0 and off < len(text_data) and text_data[off] == 0xE8:
                count += 1
            off2 = ret_rva - text.VirtualAddress - 6
            if off2 >= 0 and off2 < len(text_data) and text_data[off2] == 0xFF and text_data[off2+1] == 0x15:
                count += 1
        if count >= 2:
            base_counts[base] = count
    if base_counts:
        best = base_counts.most_common(1)[0][0]
        print(f"\nUsing best guess base: 0x{best:08X} ({base_counts[best]} matches)")

if best:
    print(f"\n{'='*70}")
    print(f"Disassembling fork point with base=0x{best:08X}")
    print(f"{'='*70}")
    # 00A09735 is where AAA and BBB paths diverge
    fork_rva = 0x00A09735 - best
    aaa_rva = 0x00A05431 - best
    bbb_rva = 0x00A05D55 - best
    print(f"Fork point RVA: 0x{fork_rva:05X}")
    print(f"AAA path RVA:   0x{aaa_rva:05X}")
    print(f"BBB path RVA:   0x{bbb_rva:05X}")

    for rva, label in [(fork_rva, "FORK POINT"), (aaa_rva, "AAA PATH"), (bbb_rva, "BBB PATH")]:
        print(f"\n--- {label}: dnplayer+0x{rva:05X} ---")
        start = max(0, rva - 60)
        data = pe.get_data(start, 80)
        for insn in md.disasm(data, best + start):
            irva = insn.address - best
            ann = ""
            if insn.mnemonic == 'call': ann = "  ; CALL"
            if insn.mnemonic == 'ret': ann = "  ; RET"
            if insn.mnemonic in ('je','jne','jz','jnz','jmp','jl','jg','jle','jge','jb','ja'):
                ann = f"  ; {insn.mnemonic.upper()}"
            if insn.address == best + rva: ann += "  <<<"
            print(f"  {irva:05X}  {insn.mnemonic:8s} {insn.op_str}{ann}")
            if irva > rva + 15: break
