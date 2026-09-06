#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract charlist WORD array from MJ2_fontfix.cpp and generate C header for new DLL."""

import re
import sys

def extract_charlist(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Find the array
    m = re.search(r'static const WORD g_charlist_data\[\]\s*=\s*\{(.*?)\};', content, re.DOTALL)
    if not m:
        print("ERROR: Could not find charlist array", file=sys.stderr)
        sys.exit(1)
    
    body = m.group(1)
    # Extract all 0xXXXX values
    values = re.findall(r'0x([0-9A-Fa-f]+)', body)
    
    return [int(v, 16) for v in values]

def main():
    src = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\源码\MJ2_fontfix\MJ2_fontfix.cpp"
    out = r"G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h"
    
    values = extract_charlist(src)
    print(f"Extracted {len(values)} entries (including terminator)")
    
    # Last entry should be 0x0000
    assert values[-1] == 0, f"Last entry is 0x{values[-1]:04X}, expected 0x0000"
    
    # Build hash map for O(1) lookup: GBK code -> glyph index (i + 0x100)
    entries = values[:-1]  # remove terminator
    print(f"Charlist has {len(entries)} GBK characters")
    print(f"Glyph indices: 0x100..0x{0x100 + len(entries) - 1:04X}")
    
    with open(out, 'w', encoding='utf-8') as f:
        f.write("// Auto-generated charlist data - DO NOT EDIT\n")
        f.write(f"// Total entries: {len(entries)} (excluding 0x0000 terminator)\n")
        f.write("// Each entry is a GBK double-byte encoding\n")
        f.write("// Glyph index = array_position + 0x100\n\n")
        f.write("static const WORD g_charlist_data[] = {\n")
        
        for i in range(0, len(entries), 8):
            chunk = entries[i:i+8]
            line = ", ".join(f"0x{v:04X}" for v in chunk)
            if i + 8 < len(entries):
                line += ","
            f.write(f"    {line}\n")
        
        f.write("    ,0x0000  // terminator\n")
        f.write("};\n\n")
        f.write(f"static const int g_charlist_count = {len(entries)};\n")
    
    print(f"Written to {out}")
    
    # Verify: test a few known GBK codes
    test_cases = {
        0xB0A1: 0,    # 啊 - first GBK Hanzi
        0xD7F7: len(entries) - 1,  # last entry
    }
    for gbk, expected_idx in test_cases.items():
        if gbk in values:
            actual_idx = values.index(gbk)
            if actual_idx == expected_idx:
                print(f"  OK: 0x{gbk:04X} -> index {actual_idx} (glyph {actual_idx + 0x100:#06x})")
            else:
                print(f"  WARN: 0x{gbk:04X} -> index {actual_idx}, expected {expected_idx}")
        else:
            print(f"  FAIL: 0x{gbk:04X} not found!")

if __name__ == '__main__':
    main()
