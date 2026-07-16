#!/usr/bin/env python3
"""Find the actual screenshot capture function by tracing UI strings.
Search dnplayer.exe for 'screenshot_tip' and 'screenshot_saved_notice' xrefs.
"""

import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXE = r"F:\LDPlayer\LDPlayer14\dnplayer.exe"
pe = pefile.PE(EXE)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase

with open(EXE, 'rb') as f:
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

# Find the code section
text = sections.get('.text')
if not text:
    for s in pe.sections:
        if s.Characteristics & 0x20000000:  # executable
            text = {'vaddr': s.VirtualAddress, 'vsize': s.Misc_VirtualSize,
                    'raddr': s.PointerToRawData, 'rsize': s.SizeOfRawData}
            break

print(f"Code section: vaddr=0x{text['vaddr']:X}, vsize=0x{text['vsize']:X}")
text_data = data[text['raddr']:text['raddr'] + text['rsize']]
text_va = text['vaddr']

# Search for key strings that indicate screenshot flow
key_strings = [
    'screenshot_tip',
    'screenshot_saved_notice', 
    'capture_tip',
    'CaptureStart',
    'CaptureStop',
    'ScreenShotWindow',
]

for ks in key_strings:
    ksb = ks.encode('ascii')
    idx = data.find(ksb)
    if idx == -1:
        continue
    
    for name, s in sections.items():
        if s['raddr'] <= idx < s['raddr'] + s['rsize']:
            str_rva = idx - s['raddr'] + s['vaddr']
            str_addr = IB + str_rva
            print(f"\nString '{ks}' @ RVA 0x{str_rva:05X} (addr 0x{str_addr:08X}), section={name}")
            
            # Find references in code
            str_bytes = struct.pack('<I', str_addr)
            
            # Search for push with this address
            for i in range(len(text_data) - 5):
                if text_data[i] == 0x68 and text_data[i+1:i+5] == str_bytes:
                    caller_rva = text_va + i
                    print(f"  push ref @ RVA 0x{caller_rva:05X}")
                    # Disassemble context
                    ctx_start = max(0, i - 80)
                    ctx_data = text_data[ctx_start:i + 40]
                    print(f"    Function context:")
                    for insn in md.disasm(ctx_data, IB + text_va + ctx_start):
                        rva2 = insn.address - IB
                        mark = " <-- push" if rva2 == caller_rva else ""
                        if caller_rva - 80 <= rva2 <= caller_rva + 35:
                            print(f"      0x{rva2:05X}: {insn.mnemonic:8s} {insn.op_str}{mark}")
                    print()
                
            # Search for LEA with this address  
            for i in range(len(text_data) - 6):
                if text_data[i] == 0x8D:
                    modrm = text_data[i+1]
                    mod = (modrm >> 6) & 3
                    rm = modrm & 7
                    if mod == 0 and rm == 5:  # [disp32]
                        disp = struct.unpack_from('<i', text_data, i+2)[0]
                        target = (text_va + i + 6 + disp) & 0xFFFFFFFF
                        if target == str_addr:
                            reg_names = ['eax','ecx','edx','ebx','esp','ebp','esi','edi']
                            reg = reg_names[(modrm >> 3) & 7]
                            caller_rva = text_va + i
                            print(f"  LEA {reg}, ref @ RVA 0x{caller_rva:05X}")
            break

print("\nDone.")
