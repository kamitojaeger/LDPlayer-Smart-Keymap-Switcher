"""Find callers of the CreateFileW wrapper functions and .kmp string refs."""
import pefile, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplycore.dll"
pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase
text = pe.sections[0]
text_data = pe.get_data(text.VirtualAddress, text.Misc_VirtualSize)

# 1. Search for ".kmp" string in the DLL
print("="*60)
print("STRING '.kmp' REFERENCES")
print("="*60)
kmp_bytes = b'.kmp\x00'
kmp_wbytes = '.kmp\x00'.encode('utf-16-le')
for s in pe.sections:
    sec_data = pe.get_data(s.VirtualAddress, s.Misc_VirtualSize)
    # ANSI
    pos = 0
    while True:
        idx = sec_data.find(kmp_bytes, pos)
        if idx < 0: break
        str_rva = s.VirtualAddress + idx
        # Read more context
        end = sec_data.find(b'\x00', idx)
        full_str = sec_data[idx:end].decode(errors='replace') if end > idx else ""
        if len(full_str) > 2 and len(full_str) < 200:
            print(f"  ANSI str at RVA 0x{str_rva:05X}: {full_str!r}")
        pos = idx + 1
    # Unicode
    pos = 0
    while True:
        idx = sec_data.find(kmp_wbytes, pos)
        if idx < 0: break
        str_rva = s.VirtualAddress + idx
        end = sec_data.find(b'\x00\x00', idx)
        raw = sec_data[idx:end].decode('utf-16-le', errors='replace') if end > idx else ""
        if len(raw) > 2 and len(raw) < 200:
            print(f"  WCHAR str at RVA 0x{str_rva:05X}: {raw!r}")
        pos = idx + 2

# 2. Search for calls to 0xA6870 (the clean read-only wrapper)
print(f"\n{'='*60}")
print("CALLS TO 0xA6870 (read-only file open wrapper)")
print(f"{'='*60}")
target_va = IB + 0xA6870
# E8 rel32 format
for pos in range(len(text_data) - 5):
    if text_data[pos] == 0xE8:
        rel = struct.unpack('<i', text_data[pos+1:pos+5])[0]
        call_rva = text.VirtualAddress + pos
        dest = IB + call_rva + 5 + rel
        if dest == target_va:
            # Disassemble context before the call
            ctx_start = max(0, pos - 60)
            ctx_data = text_data[ctx_start:pos + 5]
            print(f"\n  call 0xA6870 at dnplycore+0x{call_rva:05X}")
            for insn in md.disasm(ctx_data, IB + text.VirtualAddress + ctx_start):
                rva = insn.address - IB
                m = " <-- CALL" if rva == call_rva else ""
                print(f"    {rva:05X}  {insn.mnemonic:8s} {insn.op_str}{m}")

# 3. Search for calls to 0x50419's function — find function start
# 0x50419 is inside a function; find calls that land near it
print(f"\n{'='*60}")
print("CALLS NEAR 0x50419 (the other GENERIC_READ CreateFileW)")
print(f"{'='*60}")
# The function containing 0x50419 likely starts earlier. Search for calls
# that land in range 0x503F0-0x50420
for pos in range(len(text_data) - 5):
    if text_data[pos] == 0xE8:
        rel = struct.unpack('<i', text_data[pos+1:pos+5])[0]
        call_rva = text.VirtualAddress + pos
        dest_rva = call_rva + 5 + rel
        if 0x503E0 <= dest_rva <= 0x50420:
            ctx_start = max(0, pos - 30)
            ctx_data = text_data[ctx_start:pos + 5]
            print(f"\n  call to 0x{dest_rva:05X} from dnplycore+0x{call_rva:05X}")
            for insn in md.disasm(ctx_data, IB + text.VirtualAddress + ctx_start):
                rva = insn.address - IB
                m = " <-- CALL" if rva == call_rva else ""
                print(f"    {rva:05X}  {insn.mnemonic:8s} {insn.op_str}{m}")
