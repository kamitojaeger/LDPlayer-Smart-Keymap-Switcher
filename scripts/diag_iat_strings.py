"""Check IAT entry [0x79ccd760] and string constants used by Ctrl+F handler."""
import ctypes, struct, subprocess

DNPLYCORE_BASE = 0x79C10000

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

def find_pid():
    r = subprocess.run(["tasklist", "/fi", "IMAGENAME eq dnplayer.exe", "/fo", "csv", "/nh"],
                       capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        if "dnplayer.exe" in line.lower():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 2: return int(parts[1].strip())
    return 0

def read_mem(hProc, addr, size):
    buf = ctypes.create_string_buffer(size)
    br = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(addr), buf, size, ctypes.byref(br))
    return buf.raw[:br.value] if ok else b""

pid = find_pid()
hProc = kernel32.OpenProcess(0x10, False, pid)
assert hProc

# 1. Check IAT entry [0x79ccd760] — called at 0x1D9AC
iat_addr = 0x79ccd760
data = read_mem(hProc, iat_addr, 4)
if data and len(data) == 4:
    func_addr = struct.unpack("<I", data)[0]
    print(f"IAT [{iat_addr:08X}] -> 0x{func_addr:08X}")
    fbytes = read_mem(hProc, func_addr, 32)
    if fbytes:
        hx = " ".join(f"{b:02X}" for b in fbytes[:20])
        print(f"  first bytes: {hx}")

# Also check other IAT entries used in the handler
print()
for iat in [0x79ccd728, 0x79ccd760]:
    data = read_mem(hProc, iat, 4)
    if data and len(data) == 4:
        func_addr = struct.unpack("<I", data)[0]
        print(f"IAT [{iat:08X}] -> 0x{func_addr:08X}")
        fbytes = read_mem(hProc, func_addr, 24)
        if fbytes:
            hx = " ".join(f"{b:02X}" for b in fbytes[:20])
            print(f"  first bytes: {hx}")

# 2. Read string constants used in comparisons
print("\n=== String constants ===")
for addr, desc in [
    (0x79cd50a8, "compared at 0x1D889"),
    (0x79cd54dc, "compared at 0x1D8C8"),
    (0x79cd54fc, "compared at 0x1D8E1"),
    (0x79cd551c, "used at 0x1D8FF (with 0x13=19)"),
    (0x79cd56cc, "format string at 0x1DA27"),
    (0x79cd56f4, "source file at 0x1DA31"),
]:
    s = read_mem(hProc, addr, 128)
    if s:
        # Try as ASCII string
        null_pos = s.find(b'\x00')
        if null_pos >= 0:
            text = s[:null_pos].decode('ascii', errors='replace')
            print(f"  0x{addr:08X} ({desc}): \"{text}\"")
        else:
            print(f"  0x{addr:08X} ({desc}): {s[:32].hex()}")

# 3. Check what [edi + 0x10DC] might be — read from the savedInstance's "parent"
# We know savedInstance = 0x07A10498 (from priming)
# But edi is the handler's this, not CInputMgr
# Let's try to find edi by looking for the value at [some_obj + 0x10DC] that points to an object
# whose [+0x20] has a vtable with [+0xD8] returning savedInstance

# For now, let's check the vtable getter function
# The getter is at [[obj+0x20]] + 0xD8
# We need to find this. Let's search for a function that returns savedInstance (0x07A10498)
# Actually, the getter returns savedInstance. So if we search for the savedInstance value
# in the code section... no, that's too slow.

# Let's try: read the memory at addresses used in the JSON text finding (from 2026-07-14)
print("\n=== JSON text locations (from 2026-07-14 findings) ===")
# These were relative to the old base. Let's check current addresses.
# The 4 locations were: 0x054C4D43, 0x1DA749F7, 0x1DA75B97, 0x1DAC0D43
# 0x1DA749F7 is RVA 0x1DA749F7 - 0x79C10000 = too high, these were absolute addresses from old session
# Let's search for "keyboardMappings" string in dnplycore data section
json_sig = b'"keyboardMappings"'
print(f"Searching for '{json_sig.decode()}' in dnplycore.dll data section...")

# Read a large chunk of dnplycore data section (after code, typically at offset > 0x200000)
# Actually, let's search the entire readable region
# For efficiency, read in 64KB chunks
base = DNPLYCORE_BASE
found = []
for offset in range(0, 0x800000, 0x10000):
    chunk = read_mem(hProc, base + offset, 0x10000)
    if not chunk: break
    pos = 0
    while True:
        pos = chunk.find(json_sig, pos)
        if pos < 0: break
        addr = base + offset + pos
        # Read more context
        ctx = read_mem(hProc, addr, 200)
        text = ctx.decode('ascii', errors='replace')[:150]
        print(f"  Found at 0x{addr:08X} (RVA 0x{addr-base:06X}): {text[:100]}...")
        found.append(addr)
        pos += 1
    if len(found) >= 10: break

print(f"\nTotal JSON text locations: {len(found)}")

kernel32.CloseHandle(hProc)
