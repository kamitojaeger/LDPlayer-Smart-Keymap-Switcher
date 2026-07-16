#!/usr/bin/env python3
"""Deep analysis of IScreenShotClass and IScreenShotExClass in dnplycore.dll.

Find the vtable methods and understand how to call screenshot programmatically.
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

# VTable addresses
VTABLE_SS = 0xC4C88  # IScreenShotClass
VTABLE_SSEX = 0xC4C78  # IScreenShotExClass

print("=" * 70)
print("IScreenShotClass / IScreenShotExClass Deep Analysis")
print("=" * 70)

# Read vtables
print(f"\n[1] IScreenShotClass vtable @ RVA 0x{VTABLE_SS:05X}")
print(f"    IScreenShotExClass vtable @ RVA 0x{VTABLE_SSEX:05X}")

# Read vtable entries (function pointers)
# A vtable is an array of function pointers (each 4 bytes)
# Read until we hit non-code addresses
print("\n[2] VTable method analysis...")

for vtable_name, vtable_rva in [("IScreenShotClass", VTABLE_SS), ("IScreenShotExClass", VTABLE_SSEX)]:
    print(f"\n--- {vtable_name} vtable @ 0x{vtable_rva:05X} ---")
    for i in range(20):  # Read up to 20 vtable entries
        entry_rva = vtable_rva + i * 4
        func_rva_val = read_dword(entry_rva)
        if func_rva_val is None:
            break
        # Function pointers are absolute addresses like 0x100XXXXX
        # or ImageBase-relative
        if func_rva_val < IB or func_rva_val > IB + 0x200000:
            break  # Not a valid code address
        func_rva = func_rva_val - IB
        # Disassemble the first few instructions of each method
        func_data = read_rva(func_rva, 64)
        if func_data is None:
            print(f"  [{i}] RVA 0x{func_rva:05X} (addr 0x{func_rva_val:08X}) - CANNOT READ")
            continue
        
        # Print first few instructions
        print(f"  [{i}] RVA 0x{func_rva:05X} (addr 0x{func_rva_val:08X}):")
        insn_count = 0
        for insn in md.disasm(func_data, IB + func_rva):
            if insn_count >= 5:
                break
            print(f"       0x{insn.address - IB:05X}: {insn.mnemonic:8s} {insn.op_str}")
            insn_count += 1
            if insn.mnemonic == 'ret':
                break

# 3. Find xrefs to ScreenShotExInstance
print("\n[3] Searching for references to ScreenShotExInstance...")
si_str = b'ScreenShotExInstance'
idx = data.find(si_str)
if idx != -1:
    si_rva = None
    for name, s in sections.items():
        if s['raddr'] <= idx < s['raddr'] + s['rsize']:
            si_rva = idx - s['raddr'] + s['vaddr']
            break
    print(f"  String 'ScreenShotExInstance' @ RVA 0x{si_rva:05X}")
    
    # Now find all references to this string address
    text = sections.get('.text', sections.get('CODE'))
    if text:
        text_data = data[text['raddr']:text['raddr'] + text['rsize']]
        si_addr = IB + si_rva
        si_bytes = struct.pack('<I', si_addr)
        
        # Search for push with this address (0x68 <addr>)
        for i in range(len(text_data) - 5):
            if text_data[i] == 0x68 and text_data[i+1:i+5] == si_bytes:
                caller_rva = text['vaddr'] + i
                print(f"  push ScreenShotExInstance @ RVA 0x{caller_rva:05X}")
                # Disassemble context around this reference
                ctx_start = max(0, i - 30)
                ctx_data = text_data[ctx_start:i + 40]
                print(f"    Context disassembly:")
                for insn in md.disasm(ctx_data, IB + text['vaddr'] + ctx_start):
                    rva = insn.address - IB
                    mark = "  <<<<" if rva == caller_rva else ""
                    print(f"      0x{rva:05X}: {insn.mnemonic:8s} {insn.op_str}{mark}")
                    if rva > caller_rva + 20:
                        break
                print()

# 4. Find xrefs to "start screenshot" string
print("\n[4] Searching for 'start screenshot' string references...")
ss_str = 'start screenshot'.encode('utf-16-le')
idx = data.find(ss_str)
if idx != -1:
    for name, s in sections.items():
        if s['raddr'] <= idx < s['raddr'] + s['rsize']:
            ss_rva = idx - s['raddr'] + s['vaddr']
            print(f"  'start screenshot' @ RVA 0x{ss_rva:05X}")
            break

# 5. Search for CxImage vtable methods - understand the image saving pipeline
print("\n[5] CxImage class analysis...")
# We saw ??_7CxImage@@6B@ @ RVA 0xC63DC (vtable)
CxImage_vtable = 0xC63DC
print(f"  CxImage vtable @ 0x{CxImage_vtable:05X}")
for i in range(25):
    entry_rva = CxImage_vtable + i * 4
    func_rva_val = read_dword(entry_rva)
    if func_rva_val is None or func_rva_val < IB or func_rva_val > IB + 0x200000:
        break
    func_rva = func_rva_val - IB
    func_data = read_rva(func_rva, 48)
    if func_data is None:
        continue
    
    first3 = []
    for insn in md.disasm(func_data, IB + func_rva):
        first3.append(f"{insn.mnemonic} {insn.op_str}")
        if len(first3) >= 2:
            break
    
    print(f"  [{i}] RVA 0x{func_rva:05X}: {'; '.join(first3)}")

# 6. Disassemble IScreenShotClass constructor
print("\n[6] IScreenShotClass constructor (0xFD80)...")
ctor_rva = 0xFD80
ctor_data = read_rva(ctor_rva, 256)
if ctor_data:
    for insn in md.disasm(ctor_data, IB + ctor_rva):
        rva = insn.address - IB
        print(f"    0x{rva:05X}: {insn.mnemonic:8s} {insn.op_str}")
        if insn.mnemonic == 'ret' and rva > ctor_rva + 5:
            break

# 7. Find IScreenShotClass methods by looking at the vtable more carefully
# and tracking calls to "start screenshot" 
print("\n[7] Disassembling first vtable method of IScreenShotClass (likely TakeShot/ScreenShot)...")
func_rva_val = read_dword(VTABLE_SSEX)
if func_rva_val:
    func_rva = func_rva_val - IB
    func_data = read_rva(func_rva, 512)
    if func_data:
        print(f"  IScreenShotExClass[0] @ 0x{func_rva:05X}:")
        for insn in md.disasm(func_data, IB + func_rva):
            rva = insn.address - IB
            # Annotate known calls
            ann = ""
            if insn.mnemonic == 'call':
                target = insn.op_str
                ann = f"  ; call {target}"
            elif insn.mnemonic in ('push', 'lea', 'mov') and '0x' in insn.op_str:
                pass  # skip annotating addresses
            print(f"    0x{rva:05X}: {insn.mnemonic:8s} {insn.op_str}{ann}")
            if insn.mnemonic == 'ret' and rva > func_rva + 20:
                break

print("\n" + "=" * 70)
print("Analysis complete.")
