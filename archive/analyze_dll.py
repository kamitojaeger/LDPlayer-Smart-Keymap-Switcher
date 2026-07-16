import struct

with open(r'F:\leidian\LDPlayer9\dnplycore.dll', 'rb') as f:
    data = f.read()

# Parse PE
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
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
    print('Section %s: VA=%x VAEnd=%x FileOff=%x Size=%x' % (name, vaddr, vaddr+vsize, raddr, rsize))

def file_off_to_rva(foff):
    for name, s in sections.items():
        if s['raddr'] <= foff < s['raddr'] + s['rsize']:
            return foff - s['raddr'] + s['vaddr']
    return None

str_rva = file_off_to_rva(0xc7609)
print('\nsetKeyboardConfig string RVA: %x' % str_rva)

text = sections.get('.text', sections.get('CODE', None))
if not text:
    print('No .text section found')
    exit()

text_data = data[text['raddr']:text['raddr'] + text['rsize']]
target_bytes = struct.pack('<I', str_rva)

count = 0
for i in range(len(text_data) - 7):
    if text_data[i] == 0x68 and text_data[i+1:i+5] == target_bytes:
        print('XREF PUSH: File=%x RVA=%x' % (text['raddr']+i, text['vaddr']+i))
        count += 1
    if text_data[i] == 0x8D and text_data[i+1] == 0x0D and text_data[i+2:i+6] == target_bytes:
        print('XREF LEA ECX: File=%x RVA=%x' % (text['raddr']+i, text['vaddr']+i))
        count += 1
    if text_data[i] in range(0xB8, 0xC0) and text_data[i+1:i+5] == target_bytes:
        print('XREF MOV: File=%x RVA=%x' % (text['raddr']+i, text['vaddr']+i))
        count += 1

if count == 0:
    print('No direct refs, trying relative LEA...')
    for i in range(len(text_data) - 7):
        if text_data[i] == 0x8D and (text_data[i+1] & 0xC7) == 0x80:
            modrm = text_data[i+1]
            disp32 = struct.unpack_from('<i', text_data, i+3)[0]
            ref_addr = text['vaddr'] + i + 7 + disp32
            if ref_addr == str_rva:
                print('XREF LEA REL: File=%x RVA=%x' % (text['raddr']+i, text['vaddr']+i))
                count += 1

print('Total references to setKeyboardConfig string: %d' % count)

# Search for CInputMgr RTTI
rtti_str = b'.?AVCInputMgr@vbox@@'
idx = data.find(rtti_str)
print('\nRTTI CInputMgr file offset: %x, RVA: %x' % (idx, file_off_to_rva(idx)))

# Find named pipes info
print('\n=== Named pipe strings ===')
idx = data.find(b'ld-winpipe')
while idx >= 0:
    end = data.find(b'\x00', idx)
    name = data[idx:end].decode('ascii', errors='replace')
    print('Pipe: %s at offset %x, RVA: %x' % (name, idx, file_off_to_rva(idx)))
    idx = data.find(b'ld-winpipe', idx + 1)

# Check for .?AVCInputMgr and related classes
print('\n=== Key class RTTI strings ===')
classes = ['.?AVCInputMgr@vbox@@', '.?AVCInputKeyboard@vbox@@', '.?AVCKeyboardShow@vbox@@',
           '.?AVIVBoxClient@vbox@@', '.?AVVBoxClientImpl@vbox@@', '.?AVVBoxService@vbox@@']
for cls in classes:
    cb = cls.encode('ascii')
    idx = data.find(cb)
    if idx >= 0:
        print('%s: file=%x RVA=%x' % (cls, idx, file_off_to_rva(idx)))

# Also find setKeyboardConfig function
# Look for nearby function prologue references
print('\n=== Context around setKeyboardConfig string ===')
print('Bytes around string:')
start = 0xc7600
print(data[start:start+50].hex())
print(data[start:start+50])

print('\n=== Done ===')
