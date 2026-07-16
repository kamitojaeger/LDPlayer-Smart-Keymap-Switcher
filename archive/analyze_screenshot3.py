#!/usr/bin/env python3
"""Phase 3: Find the actual screenshot function and how to call it.

Key strategy:
1. Find xrefs to "start screenshot" string (RVA 0xC64B2) - this is logged at screenshot start
2. Find xrefs to "ScreenShotExInstance" (RVA 0xC4C42)
3. Understand the vtable layout
4. Look for the "screenCut" hotkey handler
"""

import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer14\dnplycore.dll"
pe = pefile.PE(DLL)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase

with open(DLL, 'rb') as f:
    data = f.read()

sections = {}
for s in pe.sections:
    name = s.Name.rstrip(b'\x00').decode('ascii', errors='replace')
    sections[name] = {
        'vaddr': s.VirtualAddress,
        'vsize': s.Misc_VirtualSize,
        'raddr': s.PointerToRawData,
        'rsize': s.SizeOfRawData
    }

def rva_to_file(rva):
    for name, s in sections.items():
        if s['vaddr'] <= rva < s['vaddr'] + s['vsize']:
            return rva - s['vaddr'] + s['raddr']
    return None

def read_rva(rva, size):
    foff = rva_to_file(rva)
    if foff is None:
        return None
    return data[foff:foff+size]

def read_dword(rva):
    d = read_rva(rva, 4)
    if d is None:
        return None
    return struct.unpack('<I', d)[0]

# Get .text or .code section
text_section = sections.get('.text')
if not text_section:
    for name, s in sections.items():
        if 'CODE' in name or 'text' in name.lower():
            text_section = s
            break

if not text_section:
    # Use .rdata or first executable section
    for s in pe.sections:
        if s.Characteristics & 0x20000000:  # IMAGE_SCN_MEM_EXECUTE
            text_section = {'vaddr': s.VirtualAddress, 'vsize': s.Misc_VirtualSize, 
                          'raddr': s.PointerToRawData, 'rsize': s.SizeOfRawData}
            break

print(f"Using section for code search: vaddr=0x{text_section['vaddr']:X}, vsize=0x{text_section['vsize']:X}")

text_data = data[text_section['raddr']:text_section['raddr'] + text_section['rsize']]
text_va = text_section['vaddr']

# === 1. Find xrefs to "start screenshot" string ===
print("\n" + "=" * 70)
print("[1] Finding callers of 'start screenshot' log")
print("=" * 70)

ss_utf16 = 'start screenshot'.encode('utf-16-le')
ss_idx = data.find(ss_utf16)
if ss_idx != -1:
    for name, s in sections.items():
        if s['raddr'] <= ss_idx < s['raddr'] + s['rsize']:
            ss_rva = ss_idx - s['raddr'] + s['vaddr']
            ss_addr = IB + ss_rva
            print(f"  String @ RVA 0x{ss_rva:05X} (addr 0x{ss_addr:08X})")
            break
    
    ss_bytes = struct.pack('<I', ss_addr)
    
    # Search for push with this address
    for i in range(len(text_data) - 5):
        if text_data[i] == 0x68 and text_data[i+1:i+5] == ss_bytes:
            caller_rva = text_va + i
            print(f"\n  push 'start screenshot' @ RVA 0x{caller_rva:05X}")
            # Disassemble 60 bytes before and 30 after
            ctx_start = max(0, i - 60)
            ctx_data = text_data[ctx_start:i + 30]
            func_start = None
            for insn in md.disasm(ctx_data, IB + text_va + ctx_start):
                rva = insn.address - IB
                mark = " <--" if rva == caller_rva else ""
                # Track function prologue
                if insn.mnemonic == 'push' and insn.op_str == 'ebp' and func_start is None:
                    # Check next is mov ebp, esp
                    pass
                print(f"    0x{rva:05X}: {insn.mnemonic:8s} {insn.op_str}{mark}")
                if rva > caller_rva + 15:
                    break

# === 2. Look for the function that references "start screenshot" ===
# Search for LEA with the string address
print("\n" + "=" * 70)
print("[2] Finding LEA references to 'start screenshot'")
print("=" * 70)

# LEA reg, [addr] can use various addressing modes
# Common pattern: 8D 0D <disp32> = LEA ECX, [addr]
for i in range(len(text_data) - 6):
    if text_data[i] == 0x8D:
        modrm = text_data[i+1]
        mod = (modrm >> 6) & 3
        rm = modrm & 7
        if mod == 0 and rm == 5:  # [disp32]
            disp = struct.unpack_from('<i', text_data, i+2)[0]
            target = (text_va + i + 6 + disp) & 0xFFFFFFFF
            if target == ss_addr:
                caller_rva = text_va + i
                reg_names = ['eax','ecx','edx','ebx','esp','ebp','esi','edi']
                reg = reg_names[(modrm >> 3) & 7]
                print(f"  LEA {reg}, ['start screenshot'] @ RVA 0x{caller_rva:05X}")
                # Disassemble context
                ctx_start = max(0, i - 80)
                ctx_data = text_data[ctx_start:i + 40]
                for insn in md.disasm(ctx_data, IB + text_va + ctx_start):
                    rva = insn.address - IB
                    mark = " <-- LEA" if rva == caller_rva else ""
                    print(f"    0x{rva:05X}: {insn.mnemonic:8s} {insn.op_str}{mark}")
                    if rva > caller_rva + 30:
                        break
                print()

# === 3. Analyze IScreenShotClass vtable properly ===
print("=" * 70)
print("[3] IScreenShotClass / IScreenShotExClass vtable raw data")
print("=" * 70)

for name, vtable_rva in [("IScreenShotClass", 0xC4C88), ("IScreenShotExClass", 0xC4C78)]:
    print(f"\n{name} vtable @ 0x{vtable_rva:05X}:")
    for i in range(10):
        entry_rva = vtable_rva + i * 4
        val = read_dword(entry_rva)
        if val is None:
            break
        is_func = (IB <= val <= IB + 0x200000)
        if is_func:
            func_rva = val - IB
            print(f"  [{i}] 0x{val:08X} → RVA 0x{func_rva:05X}")
        else:
            print(f"  [{i}] 0x{val:08X} (not code addr)")

# === 4. Look for CreateFile/WriteFile IAT calls (file writing) ===
print("\n" + "=" * 70)
print("[4] Scanning for file write operations (searching all sections)")
print("=" * 70)

# Get IAT addresses
iat_entries = {}
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    for imp in entry.imports:
        name = imp.name.decode() if imp.name else f"ord_{imp.ordinal}"
        iat_entries[IB + imp.address] = name

# Search for call [IAT] patterns in .text
call_iat_pattern = b'\xff\x15'  # call [mem32]
for i in range(0, len(text_data) - 6, 1):
    if text_data[i:i+2] == call_iat_pattern:
        target = struct.unpack_from('<I', text_data, i+2)[0]
        if target in iat_entries:
            func_name = iat_entries[target]
            if any(kw in func_name for kw in ['CreateFile', 'WriteFile', 'CloseHandle', 'DeleteFile']):
                caller_rva = text_va + i
                print(f"  call [{func_name}] @ RVA 0x{caller_rva:05X}")

# === 5. Look at what functions reference the vtable (ctor calls IScreenShotClass) ===
print("\n" + "=" * 70)
print("[5] Finding references to IScreenShotClass vtable (0xC4C88)")
print("=" * 70)

vt_addr = IB + 0xC4C88
vt_bytes = struct.pack('<I', vt_addr)

# Search for MOV [ecx], vtable (constructor pattern: C7 01 <vtable>)
# or MOV dword ptr [reg], vtable
for i in range(len(text_data) - 7):
    # mov dword ptr [ecx], imm32 = C7 01 <imm32>
    if text_data[i] == 0xC7 and text_data[i+1] == 0x01 and struct.unpack_from('<I', text_data, i+2)[0] == vt_addr:
        caller_rva = text_va + i
        print(f"  mov [ecx], 0x{vt_addr:08X} (ctor init) @ RVA 0x{caller_rva:05X}")
        ctx_start = max(0, i - 30)
        ctx_data = text_data[ctx_start:i + 30]
        for insn in md.disasm(ctx_data, IB + text_va + ctx_start):
            rva = insn.address - IB
            mark = " <-- vtable" if rva == caller_rva else ""
            print(f"    0x{rva:05X}: {insn.mnemonic:8s} {insn.op_str}{mark}")
            if rva > caller_rva + 25:
                break
        print()

# Also search for mov [reg+offset], vtable
for i in range(len(text_data) - 8):
    if text_data[i] == 0xC7:
        modrm = text_data[i+1]
        mod = (modrm >> 6) & 3
        # mod=01 (reg+disp8) or mod=10 (reg+disp32) 
        if mod in (1, 2):
            val_offset = i + 6 if mod == 2 else i + 3
            val = struct.unpack_from('<I', text_data, val_offset)[0]
            if val == vt_addr:
                caller_rva = text_va + i
                disp = text_data[i+2] if mod == 1 else struct.unpack_from('<I', text_data, i+2)[0]
                print(f"  mov [reg+0x{disp:X}], vtable @ RVA 0x{caller_rva:05X}")

print("\nDone.")
