#!/usr/bin/env python3
"""FB capture v4 - read FB name from temp file, capture frame from shared memory."""

import ctypes, struct, os, time
import numpy as np
from PIL import Image

FB_MAGIC = 0x46425200
TMP_FILE = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", ".")), "ld_fb_name.txt")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testScreenShots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

k = ctypes.windll.kernel32
k.OpenFileMappingW.restype = ctypes.c_void_p
k.MapViewOfFile.restype = ctypes.c_void_p
k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
k.UnmapViewOfFile.restype = ctypes.c_bool

# Read FB name from temp file
fb_name = ""
try:
    with open(TMP_FILE, "rb") as f:
        raw = f.read()
    # UTF-16LE decode
    fb_name = raw.decode("utf-16-le").rstrip("\x00")
    print(f"[1] FB name from temp file: {fb_name}")
except Exception as e:
    print(f"[ERR] Cannot read temp file {TMP_FILE}: {e}")
    exit(1)

if not fb_name:
    print("[ERR] Empty FB name")
    exit(1)

# Open FB shared memory
print(f"[2] Opening FB...")
h = k.OpenFileMappingW(0x0004, False, fb_name)
if not h:
    print(f"[ERR] FB not found (err={k.GetLastError()})")
    exit(1)

addr = k.MapViewOfFile(h, 0x0004, 0, 0, 0)
k.CloseHandle(h)

if not addr:
    print(f"[ERR] MapViewOfFile failed")
    exit(1)

print(f"[3] Waiting for frame...")
last_seq = -1
try:
    for _ in range(500):
        hdr = ctypes.string_at(addr, 28)
        m, w, h, fmt, pitch, seq, ready = struct.unpack_from("<IIIIIII", hdr, 0)
        if m == FB_MAGIC and ready and seq != last_seq and w > 0 and h > 0:
            last_seq = seq
            print(f"    Frame #{seq}: {w}x{h} pitch={pitch}")
            
            px = h * pitch
            pixels = ctypes.string_at(addr + 28, px)
            raw = np.frombuffer(pixels, dtype=np.uint8, count=px)
            
            bpp = 4
            rb = w * bpp
            img = raw.reshape((h, pitch))[:, :rb].reshape((h, w, bpp)) if pitch != rb else raw.reshape((h, w, bpp))
            
            for order, suffix in [([2, 1, 0], ""), ([0, 1, 2], "_rgb")]:
                rgb = img[:, :, order].copy()
                path = os.path.join(OUTPUT_DIR, f"fb_capture{suffix}.png")
                Image.fromarray(rgb).save(path)
                print(f"    Saved: {path}")
            break
        time.sleep(0.01)
    else:
        print("[3] Timeout - checking header:")
        hdr = ctypes.string_at(addr, 28)
        m, w, h, fmt, pitch, seq, ready = struct.unpack_from("<IIIIIII", hdr, 0)
        print(f"    magic=0x{m:08X} {w}x{h} seq={seq} ready={ready}")
finally:
    k.UnmapViewOfFile(addr)
    print("[Done]")
