"""Find callers of 0x503D0 (the wchar_t* read-only file open)."""
import pefile, struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer9\dnplycore.dll"
pe = pefile.PE(DLL, fast_load=True)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase
text = pe.sections[0]
text_data = pe.get_data(text.VirtualAddress, text.Misc_VirtualSize)

# Find all callers of 0x503D0
print("="*60)
print("CALLERS OF 0x503D0 (wchar_t* read-only file open)")
print("="*60)
callers = []
for pos in range(len(text_data) - 5):
    if text_data[pos] == 0xE8:
        rel = struct.unpack('<i', text_data[pos+1:pos+5])[0]
        call_rva = text.VirtualAddress + pos
        dest = call_rva + 5 + rel
        if dest == 0x503D0:
            callers.append(call_rva)

print(f"Found {len(callers)} caller(s)")
for call_rva in callers:
    # Disassemble 100 bytes before and 10 after the call
    ctx_start = max(0, call_rva - text.VirtualAddress - 100)
    ctx_size = 110
    ctx_data = text_data[ctx_start:ctx_start + ctx_size]
    print(f"\n{'='*60}")
    print(f"Caller at dnplycore+0x{call_rva:05X}")
    print(f"{'='*60}")
    for insn in md.disasm(ctx_data, IB + text.VirtualAddress + ctx_start):
        rva = insn.address - IB
        m = " <-- CALL 0x503D0" if rva == call_rva else ""
        print(f"  {rva:05X}  {insn.mnemonic:8s} {insn.op_str}{m}")
        if rva > call_rva + 5:
            break

# Also check what string is at 0xE111C (referenced in 0xB8B51)
print(f"\n{'='*60}")
print("STRING at RVA 0xE111C")
print(f"{'='*60}")
try:
    s = pe.get_data(0xE111C, 32)
    # Try ANSI
    ansi = s.split(b'\x00')[0].decode(errors='replace')
    print(f"  ANSI: {ansi!r}")
    # Try Unicode
    wstr = s.decode('utf-16-le', errors='replace').split('\x00')[0]
    print(f"  WCHAR: {wstr!r}")
    print(f"  Hex: {s[:20].hex()}")
except:
    print("  (could not read)")
