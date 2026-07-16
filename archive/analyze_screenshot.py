#!/usr/bin/env python3
"""Analyze dnplycore.dll to find the screenshot function.

Approach:
1. Find all named pipe references (CapturePipe)
2. Search for PNG/BMP file creation patterns
3. Search for hotkey handler (Ctrl+0 = key 0x30, mod 2)
4. Search for screenCut references
"""

import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL = r"F:\LDPlayer\LDPlayer14\dnplycore.dll"
pe = pefile.PE(DLL)
md = Cs(CS_ARCH_X86, CS_MODE_32)
IB = pe.OPTIONAL_HEADER.ImageBase

# Get section info
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

def file_to_rva(foff):
    for name, s in sections.items():
        if s['raddr'] <= foff < s['raddr'] + s['rsize']:
            return foff - s['raddr'] + s['vaddr']
    return None

# Read the whole DLL
with open(DLL, 'rb') as f:
    data = f.read()

print("=" * 70)
print("dnplycore.dll Analysis for Screenshot Function")
print("=" * 70)

# 1. Search for string references: CapturePipe, screenCut, screenshot, capture
print("\n[1] Searching for key strings...")
search_strings = [
    b'CapturePipe', b'capture', b'screen', b'shot', b'screenshot',
    b'Image', b'.png', b'.bmp', b'Pictures', b'sharedPicture',
    b'screenCut', b'cutScreen', b'takeShot', b'saveShot',
    b'ld-winpipe', b'ScreenShot', b'snap', b'ScreenCapture'
]
string_refs = {}
for sstr in search_strings:
    idx = 0
    while True:
        idx = data.find(sstr, idx)
        if idx == -1:
            break
        rva = file_to_rva(idx)
        if rva:
            string_refs[rva] = sstr.decode('ascii', errors='replace')
        idx += 1

if string_refs:
    for rva, s in sorted(string_refs.items()):
        print(f"  RVA 0x{rva:05X}: '{s}'")
else:
    print("  No direct string matches found in ASCII.")

# 2. Search for UTF-16 LE strings
print("\n[2] Searching for UTF-16 LE strings...")
utf16_strings = []
i = 0
while i < len(data) - 2:
    if data[i:i+2] == b'\x00\x00':
        i += 2
        continue
    # Try to find a UTF-16 string
    end = i
    while end < len(data) - 1:
        ch = struct.unpack_from('<H', data, end)[0]
        if ch == 0:
            break
        if ch > 0x7E and ch < 0xA0:
            break
        if ch > 0xFF:
            break
        end += 2
    if end - i >= 6:  # at least 3 chars
        raw = data[i:end]
        try:
            s = raw.decode('utf-16-le')
            if any(kw in s.lower() for kw in ['screen', 'shot', 'capture', 'snap', 'photo', 'image', 'picture', 'png', 'bmp', 'save']):
                rva = file_to_rva(i)
                if rva:
                    utf16_strings.append((rva, s))
        except:
            pass
        i = end + 2
    else:
        i += 2

for rva, s in sorted(utf16_strings):
    print(f"  RVA 0x{rva:05X}: '{s}'")

# 3. Look at the export table
print("\n[3] Export symbols (if any)...")
if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
    for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        name = exp.name.decode() if exp.name else f"ord_{exp.ordinal}"
        if any(kw in name.lower() for kw in ['screen', 'shot', 'capture', 'snap', 'photo', 'image', 'picture', 'png', 'bmp', 'save']):
            print(f"  {name} @ RVA 0x{exp.address:X}")

# 4. Find IAT entries for file operations (CreateFileW, WriteFile)
print("\n[4] Searching IAT for file operations...")
iat_funcs = {}
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    dll_name = entry.dll.decode()
    for imp in entry.imports:
        name = imp.name.decode() if imp.name else f"ord_{imp.ordinal}"
        iat_funcs[imp.address] = (dll_name, name)

# Get the .text section
text_section = sections.get('.text', sections.get('CODE', None))
if not text_section:
    print("ERROR: Cannot find .text section")
    exit()

text_data = data[text_section['raddr']:text_section['raddr'] + text_section['rsize']]
text_va = text_section['vaddr']

# 5. Find callers of CreateFileW (looking for PNG saves)
print("\n[5] Searching for CreateFileW callers...")
createfile_iat = None
for addr, (dll, name) in iat_funcs.items():
    if name == 'CreateFileW':
        createfile_iat = addr
        break

if createfile_iat:
    print(f"  CreateFileW IAT @ 0x{createfile_iat:X}")
    # Find all calls to CreateFileW in .text
    # call [addr] is FF 15 <addr>
    target_bytes = struct.pack('<I', IB + createfile_iat)
    call_pattern = b'\xff\x15' + target_bytes
    
    idx = 0
    callers = []
    while True:
        idx = text_data.find(call_pattern, idx)
        if idx == -1:
            break
        caller_rva = text_va + idx
        callers.append(caller_rva)
        idx += 1
    
    print(f"  Found {len(callers)} call(s) to CreateFileW:")
    for c in callers:
        print(f"    @ RVA 0x{c:05X}")
else:
    print("  CreateFileW not found in IAT")

# 6. Find calls to WriteFile
print("\n[6] Searching for WriteFile callers...")
writefile_iat = None
for addr, (dll, name) in iat_funcs.items():
    if name == 'WriteFile':
        writefile_iat = addr
        break

if writefile_iat:
    target_bytes = struct.pack('<I', IB + writefile_iat)
    call_pattern = b'\xff\x15' + target_bytes
    idx = 0
    callers = []
    while True:
        idx = text_data.find(call_pattern, idx)
        if idx == -1:
            break
        caller_rva = text_va + idx
        callers.append(caller_rva)
        idx += 1
    print(f"  Found {len(callers)} call(s) to WriteFile")
    for c in callers:
        print(f"    @ RVA 0x{c:05X}")
else:
    print("  WriteFile not found in IAT")

# 7. Search for the known functions from the existing RE work
print("\n[7] Known function references from previous RE...")
known = {
    0x9CA10: "setKeyboardConfig (v9)",
    0x959F0: "setKeyboardConfig (v14)",
    0x2019C: "CALL to setKeyboardConfig (v9)",
    0x1DD33: "CALL to setKeyboardConfig (v14)",
}
# Check which match our DLL
for rva, desc in known.items():
    try:
        foff = rva_to_file(rva)
        if foff:
            print(f"  RVA 0x{rva:05X}: {desc} (exists in this DLL)")
    except:
        pass

# 8. Look for hotkey checking code (key=0x30, modifier testing)
print("\n[8] Disassembling potential hotkey handlers...")
# Search for cmp with 0x30 (key '0') near modifier checks
# Modifier 2 = MOD_CONTROL, typically tested with test or and
# Look for patterns like: cmp eax, 0x30 (3D 30 00 00 00) near test/and with 2
for i in range(len(text_data) - 10):
    # cmp eax/r32, 0x30
    if text_data[i] == 0x3D and struct.unpack_from('<I', text_data, i+1)[0] == 0x30:
        rva = text_va + i
        # Look back 20 bytes for modifier check
        ctx = text_data[max(0, i-20):i+10]
        has_mod_check = b'\x02' in ctx[-20:]  # rough check for mod=2
        if has_mod_check:
            print(f"  Potential hotkey check @ RVA 0x{rva:05X}: cmp eax, 0x30 (key='0')")
            # Disassemble context
            disasm_start = max(0, i-30)
            for insn in md.disasm(text_data[disasm_start:disasm_start+80], IB + text_va + disasm_start):
                insn_rva = insn.address - IB
                if insn_rva < rva - 30 or insn_rva > rva + 50:
                    continue
                print(f"    0x{insn_rva:05X}: {insn.mnemonic:8s} {insn.op_str}")

# 9. Look for Named Pipe creation
print("\n[9] Named pipe operations...")
for name, (dll, func) in iat_funcs.items():
    if 'pipe' in func.lower():
        print(f"  {func} IAT @ 0x{name:X} ({dll})")

# 10. Find references to GDI+ image saving (GdipSaveImageToFile, etc.)
print("\n[10] GDI+ image operations...")
gdi_ops = ['GdipCreateBitmapFrom', 'GdipSaveImageToFile', 'GdipCreateBitmapFromHBITMAP',
           'GdipGetImageEncoders', 'GdipDisposeImage', 'CreateDIBSection']
for name, (dll, func) in iat_funcs.items():
    if any(g in func for g in gdi_ops):
        print(f"  {func} IAT @ 0x{name:X} ({dll})")

# 11. Look at class RTTI for screenshot-related classes
print("\n[11] Searching for screenshot-related class RTTI...")
rtti_patterns = [b'ScreenShot', b'Capture', b'Screen', b'Snap', b'Photo', b'Picture', b'ImageSave']
for pat in rtti_patterns:
    idx = 0
    while True:
        idx = data.find(pat, idx)
        if idx == -1:
            break
        end = data.find(b'\x00', idx)
        if end == -1:
            end = idx + len(pat)
        full = data[idx:end]
        try:
            s = full.decode('ascii', errors='replace')
            rva = file_to_rva(idx)
            if rva:
                print(f"  RVA 0x{rva:05X}: '{s}'")
        except:
            pass
        idx += len(pat)

# 12. Look for the capture pipe name pattern more broadly
print("\n[12] Broad pipe name search...")
for pipe_pattern in [b'CapturePipe', b'capture', b'Capture', b'CAPTURE', b'screen-pipe', b'pic-pipe']:
    idx = data.find(pipe_pattern)
    if idx != -1:
        end = data.find(b'\x00', idx)
        name = data[idx:end].decode('ascii', errors='replace')
        rva = file_to_rva(idx)
        print(f"  Found: '{name}' @ RVA 0x{rva:05X}")

print("\n" + "=" * 70)
print("Analysis complete.")
print("=" * 70)
