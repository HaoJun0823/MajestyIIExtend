#!/usr/bin/env python3
"""
Monitor all 3 state arrays + fallback glyph data at runtime.
Goal: determine if the same character's 3 UTF-8 bytes are split across different hook points.
"""
import ctypes
from ctypes import wintypes
import struct
import time
import sys

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# Process info - need to find Majesty2.exe PID
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

def find_pid(name):
    # Use tasklist
    import subprocess
    result = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'],
                           capture_output=True, text=True)
    for line in result.stdout.strip().split('\n'):
        parts = line.strip().strip('"').split('","')
        if len(parts) >= 2:
            return int(parts[1])
    return None

pid = find_pid('Majesty2.exe')
if not pid:
    print("ERROR: Majesty2.exe not found")
    sys.exit(1)
print(f"Found Majesty2.exe PID={pid}")

h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not h:
    print(f"ERROR: OpenProcess failed: {GetLastError()}")
    sys.exit(1)

# DLL base = 0x66A00000 (confirmed)
DLL_BASE = 0x66A00000

# State array addresses (confirmed from disassembly)
STATES = {
    'state1 (hook1 main)': 0x66A083A0,  # flag, b1=+4, b2=+8
    'state2 (hook2 width)': 0x66A08394,  # flag, b1=+4, b2=+8
    'state3 (hook3&4 rend)': 0x66A08388,  # flag, b1=+4, b2=+8
}

# g_pCharlist pointer at 0x66A08018
P_CHARLIST_ADDR = 0x66A08018

# Fallback glyph at 0xA0D7F8, width at 0xA0D810
FALLBACK_GLYPH_ADDR = 0xA0D7F8
FALLBACK_WIDTH_ADDR = 0xA0D810

# Hook points in game code (to verify hooks are installed)
HOOK_POINTS = {
    'hook1 @ 0x7E235D': 0x7E235D,
    'hook2 @ 0x7E1A53': 0x7E1A53,
    'hook3 @ 0x7D95F7': 0x7D95F7,
    'hook4 @ 0x7D9DAA': 0x7D9DAA,
}

def read_mem(addr, size):
    buf = (ctypes.c_ubyte * size)()
    bytesRead = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(bytesRead))
    if not ok or bytesRead.value != size:
        return None
    return bytes(buf[:size])

def read_dword(addr):
    data = read_mem(addr, 4)
    if data:
        return struct.unpack('<I', data)[0]
    return None

def read_float(addr):
    data = read_mem(addr, 4)
    if data:
        return struct.unpack('<f', data)[0]
    return None

def dump_state(addr):
    """Read 12 bytes of state: [flag:1][pad:3][b1:4][b2:4]"""
    data = read_mem(addr, 12)
    if not data:
        return "READ FAILED"
    flag = data[0]
    b1 = struct.unpack('<I', data[4:8])[0]
    b2 = struct.unpack('<I', data[8:12])[0]
    return f"flag={flag} b1=0x{b1:08X} b2=0x{b2:08X}"

print("\n=== Initial State ===")
for name, addr in STATES.items():
    print(f"  {name} @ 0x{addr:08X}: {dump_state(addr)}")

# Read g_pCharlist
pcl = read_dword(P_CHARLIST_ADDR)
print(f"\n  g_pCharlist @ 0x{P_CHARLIST_ADDR:08X} = 0x{pcl:08X}" if pcl else "  g_pCharlist: READ FAILED")

# Read fallback glyph
fb_width = read_float(FALLBACK_WIDTH_ADDR)
print(f"  fallback_width @ 0x{FALLBACK_WIDTH_ADDR:08X} = {fb_width}" if fb_width is not None else "  fallback_width: READ FAILED")

# Verify hook installation (should be E8 = call)
print("\n=== Hook Installation Check ===")
for name, addr in HOOK_POINTS.items():
    data = read_mem(addr, 5)
    if data:
        is_call = data[0] == 0xE8
        if is_call:
            target = addr + 5 + struct.unpack('<i', data[1:5])[0]
            print(f"  {name}: CALL 0x{target:08X} (hooked)")
        else:
            print(f"  {name}: bytes={data.hex()} (NOT hooked?)")
    else:
        print(f"  {name}: READ FAILED")

# Now monitor states - sample 100 times over 5 seconds
print("\n=== Monitoring States (100 samples over 5s) ===")
print("Looking for non-zero state values (indicates active UTF-8 decoding)")
print("-" * 80)

changes = []
prev_states = {}
for name, addr in STATES.items():
    prev_states[addr] = read_mem(addr, 12)

for i in range(100):
    time.sleep(0.05)  # 50ms between samples
    for name, addr in STATES.items():
        curr = read_mem(addr, 12)
        if curr and curr != prev_states[addr]:
            flag = curr[0]
            b1 = struct.unpack('<I', curr[4:8])[0]
            b2 = struct.unpack('<I', curr[8:12])[0]
            pflag = prev_states[addr][0] if prev_states[addr] else -1
            pb1 = struct.unpack('<I', prev_states[addr][4:8])[0] if prev_states[addr] else 0
            pb2 = struct.unpack('<I', prev_states[addr][8:12])[0] if prev_states[addr] else 0
            changes.append({
                'sample': i,
                'name': name,
                'addr': addr,
                'flag': flag,
                'b1': b1,
                'b2': b2,
                'prev_flag': pflag,
                'prev_b1': pb1,
                'prev_b2': pb2,
            })
            prev_states[addr] = curr

if not changes:
    print("  No state changes detected in 5 seconds. Game may be idle.")
else:
    print(f"  Detected {len(changes)} state changes:")
    for c in changes[:50]:
        print(f"    [sample {c['sample']:3d}] {c['name']}: "
              f"flag {c['prev_flag']}→{c['flag']}, "
              f"b1 0x{c['prev_b1']:08X}→0x{c['b1']:08X}, "
              f"b2 0x{c['prev_b2']:08X}→0x{c['b2']:08X}")
    if len(changes) > 50:
        print(f"    ... ({len(changes) - 50} more)")

# Also check: are the states adjacent? If so, writing to one might corrupt another
print("\n=== State Array Layout ===")
addrs = sorted(STATES.values(), reverse=True)
for i, addr in enumerate(addrs):
    data = read_mem(addr, 12)
    names = [k for k, v in STATES.items() if v == addr]
    if data:
        flag = data[0]
        b1 = struct.unpack('<I', data[4:8])[0]
        b2 = struct.unpack('<I', data[8:12])[0]
        print(f"  0x{addr:08X} ({names[0]}): flag={flag} b1=0x{b1:08X} b2=0x{b2:08X}")
        if i < len(addrs) - 1:
            next_addr = addrs[i + 1]
            gap = addr - next_addr
            print(f"    ↑ gap to next: {gap} bytes (0x{addr - 12 - next_addr:08X} end vs 0x{next_addr:08X} start)")

kernel32.CloseHandle(h)
print("\nDone.")
