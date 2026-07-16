#!/usr/bin/env python3
"""Debug v2: 正确读取 keymap 共享内存。"""

import ctypes, struct, mmap

KEYMAP_MEM = "LDKeymapSwitch_Mem_v9"

print(f"[DEBUG] Keymap: {KEYMAP_MEM}")

try:
    mm = mmap.mmap(-1, 11544, tagname=KEYMAP_MEM, access=mmap.ACCESS_READ)
    # Read ALL as one buffer
    mm.seek(0)
    data = mm.read(11544)
    actual_size = len(data)
    print(f"[DEBUG] Mapped size: {actual_size} bytes")
    
    if actual_size >= 4:
        magic = struct.unpack_from('<I', data, 0)[0]
        print(f"[DEBUG] Magic: 0x{magic:08X}")
    
    if actual_size >= 20:
        hs = struct.unpack_from('<I', data, 0x10)[0]
        hc = struct.unpack_from('<I', data, 0x14)[0]
        print(f"[DEBUG] HookStatus: 0x{hs:08X}  HookCount: {hc}")
    
    # Search for "LDKeymapSwitch_FB" pattern anywhere
    fb_prefix = b"LDKeymapSwitch_FB"
    idx = data.find(fb_prefix)
    if idx >= 0:
        # Found as ASCII
        end = data.find(b'\x00', idx)
        fb_name_ascii = data[idx:end].decode('ascii')
        print(f"[DEBUG] FB name (ASCII at {idx}): \"{fb_name_ascii}\"")
    else:
        # Search as UTF-16LE
        fb_utf16 = b'L\x00D\x00K\x00e\x00y\x00m\x00a\x00p\x00S\x00w\x00i\x00t\x00c\x00h\x00_\x00F\x00B\x00'
        idx2 = data.find(fb_utf16)
        print(f"[DEBUG] FB UTF-16LE at: {idx2}")
        if idx2 >= 0:
            fb = ""
            for i in range(0, 256, 2):
                if idx2 + i >= len(data): break
                ch = struct.unpack_from('<H', data, idx2 + i)[0]
                if ch == 0: break
                if 32 <= ch < 127: fb += chr(ch)
            print(f"[DEBUG] FB name: \"{fb}\"")
    
    # Dump non-zero data starting from 10800
    print(f"[DEBUG] Non-zero data near end:")
    for off in range(10800, min(11544, actual_size), 8):
        chunk = data[off:off+8]
        if any(b != 0 for b in chunk):
            readable = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            print(f"  {off:5d} (0x{off:04X}): {chunk.hex():16s} {readable}")
    
    mm.close()
except Exception as e:
    print(f"[DEBUG] Error: {e}")
