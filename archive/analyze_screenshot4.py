#!/usr/bin/env python3
"""Find the ScreenShotExInstance global variable and trace its usage.
Also search for the actual screenshot function code flow.
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

# Find the actual data section where ScreenShotExInstance lives
rdata = sections.get('.rdata')
print(f".rdata: vaddr=0x{rdata['vaddr']:X}, vsize=0x{rdata['vsize']:X}")
rdata_file_off = rdata['raddr']

# ScreenShotExInstance is at RVA 0xC4C42
instance_rva = 0xC4C42
print(f"\nScreenShotExInstance @ RVA 0x{instance_rva:05X}")
# Read the bytes around it
instance_data = read_rva(instance_rva, 64)
print(f"Raw bytes: {instance_data[:64].hex()}")

# It might be a pointer to the actual instance or the instance itself
# Look for the IScreenShotExClass vtable pattern nearby
vtable_addr = IB + 0xC4C78  # IScreenShotExClass vtable
for offset in range(0, 64, 4):
    val = struct.unpack_from('<I', instance_data, offset)[0]
    if val == vtable_addr:
        print(f"  Found vtable ref at offset +{offset}: 0x{val:08X}")

# Also search .data section for the instance pointer
data_section = sections.get('.data')
if data_section:
    print(f"\n.data: vaddr=0x{data_section['vaddr']:X}, vsize=0x{data_section['vsize']:X}")
    data_section_data = data[data_section['raddr']:data_section['raddr'] + data_section['rsize']]
    # Search for vtable address in .data (these would be instantiated objects)
    vt_bytes = struct.pack('<I', vtable_addr)
    idx = 0
    while True:
        idx = data_section_data.find(vt_bytes, idx)
        if idx == -1:
            break
        obj_rva = data_section['vaddr'] + idx
        print(f"  IScreenShotExClass instance @ RVA 0x{obj_rva:05X}")
        idx += 4

# Disassemble IScreenShotExClass vtable method [0] in full
print("\n" + "=" * 70)
print("Full disassembly of IScreenShotExClass vtable[0] @ 0xFE80")
print("=" * 70)
func_rva = 0xFE80
func_data = read_rva(func_rva, 1024)
if func_data:
    call_targets = []
    for insn in md.disasm(func_data, IB + func_rva):
        rva = insn.address - IB
        ann = ""
        if insn.mnemonic == 'call':
            # Try to resolve call target
            op = insn.op_str
            ann = f"  ; call {op}"
            if '0x100' in op:
                try:
                    target = int(op, 16) - IB
                    call_targets.append(target)
                except:
                    pass
        print(f"  0x{rva:05X}: {insn.mnemonic:8s} {insn.op_str}{ann}")
        if insn.mnemonic == 'ret' and rva > func_rva + 100:
            break
    
    print(f"\n  Call targets (RVA): {[hex(t) for t in call_targets]}")

# Disassemble the first few call targets from vtable[0]
for i, target_rva in enumerate(call_targets[:5]):
    print(f"\n  --- Call target {i}: RVA 0x{target_rva:05X} ---")
    td = read_rva(target_rva, 128)
    if td:
        for insn in md.disasm(td, IB + target_rva):
            rva2 = insn.address - IB
            print(f"    0x{rva2:05X}: {insn.mnemonic:8s} {insn.op_str}")
            if rva2 > target_rva + 50:
                break

# Also disassemble IScreenShotClass vtable[0] @ 0xFDA0 (base class method)
print("\n" + "=" * 70)
print("Full disassembly of IScreenShotClass vtable[0] @ 0xFDA0")
print("=" * 70)
func_rva2 = 0xFDA0
func_data2 = read_rva(func_rva2, 1024)
if func_data2:
    call_targets2 = []
    for insn in md.disasm(func_data2, IB + func_rva2):
        rva = insn.address - IB
        ann = ""
        if insn.mnemonic == 'call':
            op = insn.op_str
            ann = f"  ; call {op}"
            if '0x100' in op:
                try:
                    target = int(op, 16) - IB
                    call_targets2.append(target)
                except:
                    pass
        print(f"  0x{rva:05X}: {insn.mnemonic:8s} {insn.op_str}{ann}")
        if insn.mnemonic == 'ret' and rva > func_rva2 + 100:
            break
    print(f"\n  Call targets (RVA): {[hex(t) for t in call_targets2]}")

print("\nDone.")
