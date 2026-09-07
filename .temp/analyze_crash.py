#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deep analysis of MajestyII_UTF8.asi crash:
- ASI loaded at 0x68eb0000 (from cdb lm output), ImageBase=0x10000000
- Crash at RVA 0x875d8 (esi=0x68f375d8)
- .data VA=0x6000 VSize=0x806DC -> end=0x866DC
- .reloc VA=0x87000 VSize=0x120 -> end=0x87120
- 0x875d8 is in gap between .data end (0x866DC) and .reloc start (0x87000)? NO
  0x875d8 > 0x87120 (end of .reloc), so it's AFTER .reloc
  Actually: 0x875d8 is between .reloc end (0x87120) and module end

Let's check: what is the total module size?
SectionAlignment = 0x1000 (4KB)
.data: VA=0x6000, aligned end = 0x87000 (round up 0x866DC to 0x87000)
.reloc: VA=0x87000, end=0x87120, aligned end = 0x88000
So module spans 0x0 to 0x88000 (550KB at ImageBase)

But ASI loaded at 0x68eb0000, so module spans:
  0x68eb0000 to 0x68eb0000 + 0x88000 = 0x68f38000

esi=0x68f375d8 -> RVA = 0x875d8
0x875d8 is between .reloc end (0x87120) and module end (0x88000)
This is the TAIL of the module image - possibly alignment padding.

BUT: .data VSize=0x806DC means BSS from 0x6200 to 0x866DC
The loader should commit the entire .data section.
But 0x875d8 is PAST .data end (0x866DC) and PAST .reloc end (0x87120)

Wait: let me recalculate.
.data VA=0x6000, VSize=0x806DC
0x6000 + 0x806DC = 0x866DC
/reloc VA=0x87000, VSize=0x000120
0x87000 + 0x120 = 0x87120

0x875d8 is > 0x87120, so it's in the gap after .reloc but before module end (aligned to 0x88000)
This area has NO section data - it's just alignment padding and should NOT be committed.

The real question is: WHY is esi pointing to 0x68f375d8?
Possible causes:
1. A global variable pointer in ASI was corrupted to point to this gap
2. std::string SSO buffer inside the ASI is being written by io.dll

Let's check .data section for what's at offset 0x6200 (after raw data, BSS starts).
The BSS contains g_hashTable (HASH_SIZE * 8 = 65521 * 8 = 524168 = 0x80028 bytes)
g_hashTable starts at some RVA in .data.

From source code:
  static HashEntry g_hashTable[HASH_SIZE];  // 65521 * 8 = 524168 bytes
  static CRITICAL_SECTION g_cs;             // Win32 CRITICAL_SECTION = 24 bytes on x86
  static unsigned int crc32_table[256];     // 1024 bytes
  static int crc32_table_built;             // 4 bytes
  static DWORD g_hookRetAddr = 0x0077593E; // 4 bytes (initialized)

Total BSS ~525KB, fits in .data VSize=0x806DC (515KB)... wait:
  0x806DC = 526300 bytes
  524168 + 24 + 1024 + 4 + 4 = 525224 bytes
  Remaining: 526300 - 525224 = 1076 bytes (enough for adder1-6, padding etc.)

So g_hashTable occupies most of .data BSS.
g_hashTable VA = .data start (0x6000) + raw data (0x200) = 0x6200
g_hashTable end = 0x6200 + 0x80028 = 0x86228

Hmm, but crash esi = 0x875d8 which is PAST g_hashTable end (0x86228)!
And it's past .data VEnd (0x866DC)!

So esi is pointing to a location OUTSIDE g_hashTable, OUTSIDE .data section entirely.

This suggests g_hashTable overflow or a different pointer.
"""

# Let's verify: can g_hashTable entries point to address 0x875d8?
# HashEntry = { DWORD crc32; char* text; } = 8 bytes
# If hash table overflows (all slots filled), HashInsert would write past the end!
# HASH_SIZE = 65521, if LoadDict loads MORE than 65521 entries, overflow!

# LoadDict log says: count=7264 - well under 65521, no overflow.

# Let's check: is 0x875d8 a valid stack value that got into esi?
# From the stack dump: 0x68f375d8 appears at esp+0x1A0 (001acdc0)
# And 0x68f365d8 (ASI+0x865d8) appears at esp+0x1A4 (001acdc4? no)

# Actually from the dds output:
# 001ace34 68f375d8 MajestyII_UTF8+0x875d8
# 001ace38 68f365d0 MajestyII_UTF8+0x865d0
# These are on the stack as return values or pointers.

# 0x865d0 = .data + 0x5d0 (in BSS area, would be inside g_hashTable)
# 0x875d8 = past .data end

# The REAL issue: these look like ASI addresses being used as std::string buffers
# by io.dll's xRepository::Remap function.

# KEY INSIGHT: The crash is NOT in ASI code, it's in ntdll (RtlPublishInvalidPageHelper)
# being called from io.dll's xRepository::Remap.
# io.dll is trying to write a string to address 0x68f375d8.
# This address is in the ASI module's uncommitted memory.

# WHY would io.dll write to an ASI address?
# Because io.dll's Remap function is processing resource paths,
# and one of those resource paths points to a string INSIDE the ASI module.

# This can happen if:
# 1. ASI hooks modify a resource path pointer to point into ASI memory
# 2. A font file name or resource name is stored in ASI's static data
# 3. The hook corrupts a pointer that io.dll later dereferences

# Let's check: does the ASI's hook target (0x775939) relate to resource loading?
# The hook at 0x775939 is in Majesty2.exe, it's the LocalizeKey function.
# The font hooks at 0x7D95F7 etc. are in the font rendering path.

# ALTERNATIVE THEORY: The crash is unrelated to ASI.
# io.dll's xRepository::Remap processes resource.mod updates,
# and when loading the new font files, something in the TUV/DDS
# causes the Remap to write to a wrong address.

# But the stack clearly shows MajestyII_UTF8+0x875d8 on the stack,
# meaning io.dll obtained this pointer from somewhere.

print("=== Analysis Summary ===")
print(f"ASI ImageBase: 0x10000000, loaded at: 0x68eb0000")
print(f"ASI .data: VA=0x6000, VSize=0x806DC (end=0x866DC)")
print(f"ASI .reloc: VA=0x87000, VSize=0x120 (end=0x87120)")
print(f"ASI module end (aligned): 0x88000")
print(f"Crash esi RVA: 0x875d8 (past .reloc end 0x87120, in alignment padding)")
print(f"g_hashTable: 65521 * 8 = {65521*8} = 0x{65521*8:X} bytes")
print(f"g_hashTable VA range: 0x6200 ~ 0x{0x6200 + 65521*8:X}")
print(f"Crash RVA 0x875d8 > g_hashTable end 0x{0x6200 + 65521*8:X}: {0x875d8 > 0x6200 + 65521*8}")
print()
print("CONCLUSION: esi points to uncommitted memory past all sections.")
print("This is likely a GARBAGE pointer, not a valid ASI data address.")
print("The real crash cause is probably in io.dll's Remap logic,")
print("possibly triggered by the new font files or resource.mod overlay.")
