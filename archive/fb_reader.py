#!/usr/bin/env python3
"""读取 keymap_hook.dll v9 SDL framebuffer 捕获数据。

FB 名称存储在 LDKeymapSwitch_Mem_v9 共享内存 offset 11000 处。
"""

import ctypes
import struct
import time
import os
import numpy as np
from PIL import Image

KEYMAP_MEM = "LDKeymapSwitch_Mem_v9"
FB_MAGIC = 0x46425200
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testScreenShots")
os.makedirs(OUTPUT_DIR, exist_ok=True)
_kernel32 = ctypes.windll.kernel32
_kernel32.MapViewOfFile.restype = ctypes.c_void_p


def _read_keymap_str(offset, max_len=64):
    """从 keymap 共享内存读取 WCHAR 字符串。"""
    h = _kernel32.OpenFileMappingW(0x0004, False, KEYMAP_MEM)
    if not h:
        return ""
    try:
        addr = _kernel32.MapViewOfFile(h, 0x0004, 0, 0, offset + max_len * 2 + 50)
        if not addr:
            _kernel32.CloseHandle(h)
            return ""
        raw = ctypes.string_at(addr, offset + max_len * 2)
        _kernel32.UnmapViewOfFile(addr)
        _kernel32.CloseHandle(h)
        
        result = ""
        for i in range(0, max_len * 2, 2):
            ch = struct.unpack_from('<H', raw, offset + i)[0]
            if ch == 0:
                break
            if 32 <= ch < 127:
                result += chr(ch)
        return result
    except:
        _kernel32.CloseHandle(h)
        return ""


def discover_fb():
    """发现 FB 共享内存。"""
    # Read FB name from keymap shared memory
    name = _read_keymap_str(11000)
    if not name:
        return None
    # Verify
    h = _kernel32.OpenFileMappingW(0x0004, False, name)
    if not h:
        return None
    try:
        addr = _kernel32.MapViewOfFile(h, 0x0004, 0, 0, 0)
        if not addr:
            _kernel32.CloseHandle(h)
            return None
        hdr = ctypes.string_at(addr, 28)
        m, w, h, fmt, pitch, seq, ready = struct.unpack_from('<IIIIIII', hdr, 0)
        _kernel32.UnmapViewOfFile(addr)
        _kernel32.CloseHandle(h)
        if m == FB_MAGIC and w > 0:
            return {"name": name, "width": w, "height": h, "ready": ready}
    except:
        _kernel32.CloseHandle(h)
    return None


class FBCapture:
    """帧缓冲捕获器。"""

    def __init__(self):
        self._h = None
        self._addr = None
        self._last_seq = -1
        self._info = None

    def open(self):
        info = discover_fb()
        if not info:
            return False
        self._info = info
        self._h = _kernel32.OpenFileMappingW(0x0004, False, info['name'])
        if not self._h:
            return False
        self._addr = _kernel32.MapViewOfFile(self._h, 0x0004, 0, 0, 0)
        return self._addr is not None

    def close(self):
        if self._addr:
            _kernel32.UnmapViewOfFile(self._addr)
            self._addr = None
        if self._h:
            _kernel32.CloseHandle(self._h)
            self._h = None

    def read_frame(self, wait_new=True, timeout=3.0):
        """读取一帧，返回 numpy BGR 数组。"""
        if not self._addr:
            return None
        start = time.time()
        while time.time() - start < timeout:
            try:
                hdr = ctypes.string_at(self._addr, 28)
            except:
                return None
            m, w, h, fmt, pitch, seq, ready = struct.unpack_from('<IIIIIII', hdr, 0)
            if m != FB_MAGIC or not ready or w <= 0:
                time.sleep(0.005)
                continue
            if wait_new and seq == self._last_seq:
                time.sleep(0.005)
                continue
            self._last_seq = seq

            px_size = h * pitch
            pixels = ctypes.string_at(self._addr + 28, px_size)
            raw = np.frombuffer(pixels, dtype=np.uint8, count=px_size)
            bpp = 4
            rb = w * bpp
            if pitch == rb:
                img = raw.reshape((h, w, bpp))
            else:
                img = raw.reshape((h, pitch))[:, :rb].reshape((h, w, bpp))
            # SDL2 BGRA → BGR
            bgr = img[:, :, :3].copy()
            return bgr
        return None

    def save_frame(self, bgr_array, path=None):
        if bgr_array is None:
            return None
        if path is None:
            path = os.path.join(OUTPUT_DIR, "fb_latest.png")
        rgb = bgr_array[:, :, ::-1].copy()
        Image.fromarray(rgb).save(path)
        return path


def capture_to_numpy(timeout=3.0):
    """便捷函数：打开 FB → 读取一帧 → 返回 BGR numpy 数组。"""
    cap = FBCapture()
    if not cap.open():
        cap.close()
        return None
    try:
        return cap.read_frame(wait_new=True, timeout=timeout)
    finally:
        cap.close()


if __name__ == "__main__":
    print("[FB] Discovering shared memory...")
    info = discover_fb()
    if not info:
        print("[FB] NOT FOUND - is keymap_hook.dll v9 injected?")
        exit(1)
    print(f"[FB] Found: {info['name']} ({info['width']}x{info['height']})")

    cap = FBCapture()
    if not cap.open():
        print("[FB] Open failed")
        exit(1)
    print("[FB] Waiting for frame...")
    try:
        frame = cap.read_frame(timeout=10.0)
        if frame is not None:
            print(f"[FB] Frame: {frame.shape[1]}x{frame.shape[0]}")
            cap.save_frame(frame)
            print("[FB] Saved: testScreenShots/fb_latest.png")
        else:
            print("[FB] Timeout")
    finally:
        cap.close()
