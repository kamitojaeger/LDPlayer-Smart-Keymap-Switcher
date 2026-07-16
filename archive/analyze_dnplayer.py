import struct

with open(r'F:\leidian\LDPlayer9\dnplayer.exe', 'rb') as f:
    data = f.read()

# Try different runtime base addresses
print('=== Looking for code at 0092E3AF ===')
for try_base in range(0x00400000, 0x00A00000, 0x10000):
    rva = 0x0092E3AF - try_base
    if 0x1000 <= rva < 0x30C200:  # within .text
        text_off = rva - 0x1000
        file_off = 0x400 + text_off
        b = data[file_off:file_off+5]
        # Check if bytes look like valid code
        # Common instructions: 55(push ebp) 8B(mov) 83(sub) FF(call/jmp) E8(call) 68(push)
        if b[0] in (0x55, 0x8B, 0x83, 0xFF, 0xE8, 0x68, 0x56, 0x57, 0x53, 0xA1, 0x6A, 0xE9):
            print('base=%08X RVA=%x file=%x: %s' % (try_base, rva, file_off, ' '.join('%02X' % x for x in b)))
            if try_base == 0x008E0000:
                print('  Context:')
                for j in range(-16, 32, 16):
                    start = max(0, file_off + j)
                    context = data[start:start+16]
                    print('    %08X: %s' % (start, ' '.join('%02X' % x for x in context)))

# Find dnplycore.dll reference
print('\n=== dnplycore.dll references in dnplayer.exe ===')
idx = 0
while True:
    idx = data.find(b'dnplycore', idx)
    if idx < 0:
        break
    print('  File offset: %x' % idx)
    end = data.find(b'\x00', idx)
    if end > idx:
        print('    String: %s' % data[idx:end].decode('ascii', errors='replace'))
    # Check what section
    if 0x400 <= idx < 0x30b600:
        print('    In .text or IAT area (RVA ~ %x)' % (0x1000 + idx - 0x400))
    elif 0x30b600 <= idx < 0x3d1c00:
        print('    In .rdata (RVA ~ %x)' % (0x30d000 + idx - 0x30b600))
    elif 0x3d1c00 <= idx:
        print('    In .data or later')
    idx += 1

# Look at what's around the call stack functions
# The call chain: 00AE81F8 -> 00AF3706 -> ... -> 0092E3AF
# Let's analyze the parent function that dispatches to keyboard handling
print('\n=== Analyzing dispatch function 00AE81F8 ===')
# This is the one called from user32 message loop
for try_base in [0x008E0000]:
    rva = 0x00AE81F8 - try_base
    text_off = rva - 0x1000
    file_off = 0x400 + text_off
    if 0x400 <= file_off < 0x30b600:
        print('  Function at file offset %x:' % file_off)
        for j in range(0, min(64, len(data) - file_off), 16):
            print('    %08X: %s' % (file_off + j, ' '.join('%02X' % x for x in data[file_off+j:file_off+j+16])))

# Search for dnplycore.dll LOADLIBRARY or GetProcAddress calls
# These would reference the string 'dnplycore.dll'
print('\n=== Cross-reference search for dnplycore.dll ===')
# In the PE file, locate Import Address Table
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
import_rva = struct.unpack_from('<I', data, e_lfanew + 0x78 + 0x0C)[0]
print('  Import table RVA: %x' % import_rva)
# The string 'dnplycore.dll' is in .rdata (file offset 3cf5c2)
# Let's see what's at its runtime address
str_rva = 0x30D000 + (0x3cf5c2 - 0x30b600)  # approximate
print('  dnplycore.dll string RVA: ~%x' % str_rva)
