import struct

with open(r'F:\leidian\LDPlayer9\dnplycore.dll', 'rb') as f:
    data = f.read()

# Check the PE image base
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
image_base = struct.unpack_from('<I', data, e_lfanew + 0x34)[0]
print('Preferred image base: %08X' % image_base)

# Actual runtime base: 77A30000
actual_base = 0x77A30000
delta = actual_base - image_base
print('Relocation delta: %08X' % delta)

# Parse sections
num_sects = struct.unpack_from('<H', data, e_lfanew + 6)[0]
opt_hdr_size = struct.unpack_from('<H', data, e_lfanew + 0x14)[0]
sects_start = e_lfanew + 24 + opt_hdr_size

sections = {}
for i in range(num_sects):
    offset = sects_start + i * 40
    name = data[offset:offset+8].rstrip(b'\x00').decode('ascii', errors='replace')
    vsize = struct.unpack_from('<I', data, offset + 8)[0]
    vaddr = struct.unpack_from('<I', data, offset + 12)[0]
    rsize = struct.unpack_from('<I', data, offset + 16)[0]
    raddr = struct.unpack_from('<I', data, offset + 20)[0]
    sections[name] = {'vaddr': vaddr, 'vsize': vsize, 'raddr': raddr, 'rsize': rsize}
    print('Section %s: VA=%x FileOff=%x Size=%x MemSize=%x' % (name, vaddr, raddr, rsize, vsize))

# The push instruction runtime address = 77A5017A
# RVA = 77A5017A - 77A30000 = 2017A
push_rva = 0x2017A

# .text: VA=1000, FileOff=400
text = sections['.text']
file_off = text['raddr'] + (push_rva - text['vaddr'])
print('\nPush instruction file offset: %x' % file_off)

# Read the memory at that location to verify
# Also check surrounding bytes
print('Bytes at push location:')
for i in range(-20, 30):
    off = file_off + i
    if 0 <= off < len(data):
        marker = ' <-- PUSH?' if i == 0 else ''
        print('  %08X: %02X%s' % (off, data[off], marker))

# Search for 68 XX XX XX XX (push imm32) with the right operand
print('\nSearching for the push instruction pattern...')
operand_at_push = 0x77AFA7D4
# Find the push by searching for the correct relocated value
# File operand = runtime_operand - delta
file_operand = operand_at_push - delta
print('Looking for push imm32 with operand %08X' % file_operand)
pattern = struct.pack('<I', file_operand)
for i in range(len(data) - 5):
    if data[i] == 0x68 and data[i+1:i+5] == pattern:
        rva_of_push = sections['.text']['vaddr'] + (i - sections['.text']['raddr'])
        rt_addr = actual_base + rva_of_push
        print('  Found PUSH at file offset %x, RVA %x, runtime %08X' % (i, rva_of_push, rt_addr))

# Also search for the push in .rdata or other sections
print('\nSearching ALL sections for push...')
for sec_name, sec in sections.items():
    for i in range(sec['raddr'], sec['raddr'] + sec['rsize'] - 5):
        if data[i] == 0x68 and data[i+1:i+5] == pattern:
            rva = sec['vaddr'] + (i - sec['raddr'])
            rt = actual_base + rva
            print('  %s: File %x RVA %x RT %08X' % (sec_name, i, rva, rt))

# What's the string at runtime 77AFA7D4?
# .rdata in file: VA=c5000, FileOff=c3e00
# But at runtime .rdata starts at 77AF7000
# So runtime .rdata VA = 77AF7000 - actual_base = C7000
# This means .rdata in memory is at RVA C7000, not C5000 as in file
# The discrepancy is 2000 bytes
# So: file_offset_for_runtime_string = c3e00 + (37D4 - 2000) = c3e00 + 17D4

# Actually let me think differently
# Runtime string address: 77AFA7D4
# RVA of string = 77AFA7D4 - 77A30000 = CA7D4
# File .rdata: VA=C5000, FileOff=C3E00
# But runtime .rdata is at RVA C7000 (77AF7000 - 77A30000)
# So the runtime VA is 2000 higher than file VA
# The difference is: runtime_va_file = C5000, runtime_va_actual = C7000
# runtime_rva_delta = C7000 - C5000 = 2000
# 
# String RVA in file = CA7D4 - 2000 = C87D4
# String file offset = c3e00 + (C87D4 - C5000) = c3e00 + 37D4 = c75d4

# Let me just search for the string in the file
str_to_find = b'vbox::CInputMgr::setKeyboardConfig'
idx = data.find(str_to_find)
print('\nString found at file offset: %x' % idx)
if idx >= 0:
    # Find which section it's in
    for sec_name, sec in sections.items():
        if sec['raddr'] <= idx < sec['raddr'] + sec['rsize']:
            rva = sec['vaddr'] + (idx - sec['raddr'])
            print('  In section: %s, RVA: %x' % (sec_name, rva))
            print('  At runtime (expected): %08X' % (actual_base + rva))
            # Adjust for the runtime offset difference
            # runtime_rva = rva + 2000 (if in .rdata which shifted)
            if sec_name == '.rdata':
                runtime_rva = rva + 0x2000
                print('  At runtime (adjusted for section shift): %08X' % (actual_base + runtime_rva))
    # The x32dbg showed string at 77AFA7D4
    # Let me find what's at that exact address
    expected_runtime = 0x77AFA7D4
    expected_rva = expected_runtime - actual_base  # CA7D4
    adjusted_file_off = idx
    print('\nFile offset of string: %x' % adjusted_file_off)
    print('RVA (file-based): %x' % (sections['.rdata']['vaddr'] + (idx - sections['.rdata']['raddr'])))
    print('Runtime string address from x32dbg: %08X' % expected_runtime)
    print('Expected string start (adjusted): %08X' % (actual_base + sections['.rdata']['vaddr'] + (idx - sections['.rdata']['raddr'])))
