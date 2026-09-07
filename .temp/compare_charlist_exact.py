# -*- coding: utf-8 -*-
"""Extract charlist from original MJ2_fontfix.cpp and compare with charlist_data.h"""

import re

# Read original source
orig_path = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\Majesty2-CN\source\MJ2_fontfix\MJ2_fontfix.cpp"
with open(orig_path, 'r', encoding='utf-8', errors='replace') as f:
    orig_content = f.read()

# Extract g_charlist_data from original
match = re.search(r'static\s+const\s+WORD\s+g_charlist_data\[\]\s*=\s*\{(.*?)\};', orig_content, re.DOTALL)
if not match:
    print("ERROR: Could not find g_charlist_data in original source")
    exit(1)

orig_hex = re.findall(r'0x([0-9A-Fa-f]{4})', match.group(1))
orig_values = [int(v, 16) for v in orig_hex]
print("Original charlist entries: %d" % len(orig_values))
print("First 5: %s" % ["0x%04X" % v for v in orig_values[:5]])
print("Last 5: %s" % ["0x%04X" % v for v in orig_values[-5:]])

# Read our charlist_data.h
our_path = r"G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h"
with open(our_path, 'r', encoding='utf-8') as f:
    our_content = f.read()

match2 = re.search(r'g_charlist\[\]\s*=\s*\{(.*?)\};', our_content, re.DOTALL)
if not match2:
    print("ERROR: Could not find g_charlist in our header")
    exit(1)

our_hex = re.findall(r'0x([0-9A-Fa-f]{4})', match2.group(1))
our_values = [int(v, 16) for v in our_hex]
print("\nOur charlist entries: %d" % len(our_values))
print("First 5: %s" % ["0x%04X" % v for v in our_values[:5]])
print("Last 5: %s" % ["0x%04X" % v for v in our_values[-5:]])

# Compare
if len(orig_values) != len(our_values):
    print("\nMISMATCH: Length differs! orig=%d our=%d" % (len(orig_values), len(our_values)))
    
mismatches = 0
for i in range(min(len(orig_values), len(our_values))):
    if orig_values[i] != our_values[i]:
        if mismatches < 20:
            print("MISMATCH at index %d: orig=0x%04X our=0x%04X" % (i, orig_values[i], our_values[i]))
        mismatches += 1

if mismatches == 0 and len(orig_values) == len(our_values):
    print("\n*** EXACT MATCH: charlist data is identical ***")
else:
    print("\n*** %d mismatches found ***" % mismatches)
