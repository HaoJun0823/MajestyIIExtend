#!/usr/bin/env python3
"""
Deep analysis of state arrays - check if bytes are being split across hooks.
Also verify: does the game process text character-by-character or byte-by-byte?
"""
import ctypes
from ctypes import wintypes
import struct
import time
import sys

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

def find_pid(name):
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

h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not h:
    print(f"ERROR: OpenProcess failed")
    sys.exit(1)

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

# State array addresses
STATE1 = 0x66A083A0  # hook1
STATE2 = 0x66A08394  # hook2  
STATE3 = 0x66A08388  # hook3&4

# g_pCharlist
P_CHARLIST = 0x66A08018

print("=== Current State Analysis ===\n")

# Read all states
for name, addr in [('state1(hook1)', STATE1), ('state2(hook2)', STATE2), ('state3(hook3)', STATE3)]:
    data = read_mem(addr, 12)
    if data:
        flag = data[0]
        b1 = struct.unpack('<I', data[4:8])[0]
        b2 = struct.unpack('<I', data[8:12])[0]
        print(f"  {name} @ 0x{addr:08X}: flag={flag} b1=0x{b1:02X} b2=0x{b2:02X}")
        
        # Decode what this state represents
        if flag == 0:
            if b1 == 0 and b2 == 0:
                print(f"    → Idle (never used or completed)")
            else:
                # flag=0 but b1 has data → state machine completed and reset, but b1/b2 are stale
                print(f"    → Completed/reset (stale b1/b2 data)")
        elif flag == 1:
            # Waiting for byte 2
            print(f"    → Waiting for byte 2, lead byte = 0x{b1:02X}")
            if 0xE0 <= b1 <= 0xEF:
                # UTF-8 3-byte sequence
                cp_range = "CJK" if b1 >= 0xE4 else "other"
                print(f"    → UTF-8 lead byte, range: {cp_range}")
        elif flag == 2:
            # Waiting for byte 3
            print(f"    → Waiting for byte 3, b1=0x{b1:02X} b2=0x{b2:02X}")
            if 0xE0 <= b1 <= 0xEF and 0x80 <= b2 <= 0xBF:
                # We can predict what the 3rd byte should be
                # codepoint = (b1&0x0F)<<12 | (b2&0x3F)<<6 | (b3&0x3F)
                # We know b1 and b2, so the codepoint range is:
                cp_high = (b1 & 0x0F) << 12 | (b2 & 0x3F) << 6
                print(f"    → Partial codepoint so far: 0x{cp_high:04X} (waiting for b3 to complete)")
                print(f"    → Valid b3 range: 0x80-0xBF → codepoints 0x{cp_high | 0x00:04X}-0x{cp_high | 0x3F:04X}")
        print()

# Now let's check: what text is the game currently displaying?
# The texts_hook replaces text at 0x775939. The replaced text goes into esi.
# We can't easily read the current text, but we can check the dictionary file
# to see what UTF-8 sequences look like for common Chinese characters.

print("=== Analysis: Why state1 is stuck at flag=2 ===\n")
print("state1 has b1=0xE6, b2=0x88, which means:")
print("  - Byte 1 (0xE6) went through hook1 → state1 flag=1")
print("  - Byte 2 (0x88) went through hook1 → state1 flag=2")
print("  - Byte 3 (0x??) is expected through hook1 to complete the character")
print("  - But byte 3 NEVER arrived → state1 is stuck at flag=2")
print()
print("Meanwhile state2 has b1=0xE7 (different character!), meaning:")
print("  - A DIFFERENT byte went through hook2 while state1 was still waiting")
print("  - This confirms: the 3 bytes of the same character go through DIFFERENT hooks")
print()

# Let's verify by checking what 0xE6 0x88 would be with various 3rd bytes
print("=== Possible characters for state1 (0xE6 0x88 ??):")
for b3 in range(0x80, 0xC0, 0x08):
    cp = (0xE6 & 0x0F) << 12 | (0x88 & 0x3F) << 6 | (b3 & 0x3F)
    char = chr(cp) if cp < 0x10000 else '?'
    print(f"  0xE6 0x88 0x{b3:02X} → U+{cp:04X} = '{char}'")

print()
print("=== Possible characters for state2 (0xE7 0x8C ??):")
for b3 in range(0x80, 0xC0, 0x08):
    cp = (0xE7 & 0x0F) << 12 | (0x8C & 0x3F) << 6 | (b3 & 0x3F)
    char = chr(cp) if cp < 0x10000 else '?'
    print(f"  0xE7 0x8C 0x{b3:02X} → U+{cp:04X} = '{char}'")

# Check charlist for these codepoints
print("\n=== Charlist Lookup ===")
pcl_val = read_dword(P_CHARLIST)
print(f"g_pCharlist = 0x{pcl_val:08X}")

# Read first few entries of charlist to verify it's accessible
charlist_data = read_mem(pcl_val, 100)
if charlist_data:
    entries = []
    for i in range(0, 100, 2):
        val = struct.unpack('<H', charlist_data[i:i+2])[0]
        entries.append(val)
        if val == 0:
            break
    print(f"First {len(entries)} charlist entries: {[f'0x{e:04X}' for e in entries[:20]]}")

# Search for U+6218 (战) in charlist
target_cp = 0x6218
charlist_full = read_mem(pcl_val, 7232 * 2 + 2)
if charlist_full:
    found = False
    for i in range(0, 7232 * 2, 2):
        val = struct.unpack('<H', charlist_full[i:i+2])[0]
        if val == target_cp:
            print(f"  U+{target_cp:04X} (战) found at charlist index {i//2}, glyph={i//2 + 0x100}")
            found = True
            break
        if val == 0:
            print(f"  U+{target_cp:04X} (战) NOT found in charlist (hit terminator at index {i//2})")
            break
    if not found and len(charlist_full) >= 7232 * 2:
        print(f"  U+{target_cp:04X} (战) NOT found in charlist (searched all {7232} entries)")

# Search for U+6218 in charlist
print()
print("=== Key Question: How does the original GBK fontfix handle this? ===")
print("In GBK mode: 2 bytes per character, and the original code uses 6 BYTE adders")
print("  adder1/adder2 for hook1, adder3/adder4 for hook2, adder5/adder6 for hook3")
print("  Each pair is independent: flag in adder(odd), lead byte in adder(even)")
print("  GBK is only 2 bytes, so state machine is: state0 → state1 → done")
print("  The 3rd byte problem doesn't exist for GBK!")
print()
print("In UTF-8 mode: 3 bytes per character, but we're using the SAME hook points")
print("  The game calls these hooks for EACH BYTE of text rendering")
print("  If the game sends byte 1 through hook1, byte 2 through hook2, byte 3 through hook3...")
print("  ...then NO single state array ever sees all 3 bytes → permanent yyyyy!")
print()
print("This is the ROOT CAUSE: the game distributes bytes across different hook points")
print("for different rendering passes (main render, width cache, render path A/B)")
print("Each pass should see the FULL character, not just one byte of it")

kernel32.CloseHandle(h)
