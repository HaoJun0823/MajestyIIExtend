#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deep TUV comparison: parse as text header + binary data."""
import os

orig_dir = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\字体生成\Original_Fonts"
new_dir = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\resource.mod\Fonts"

fonts = ["font12", "font14", "font18", "console", "small", "big_caption", "med_caption", "paragraph"]

for name in fonts:
    orig_tuv = os.path.join(orig_dir, name + ".tuv")
    new_tuv = os.path.join(new_dir, name + ".tuv")
    
    if not os.path.exists(orig_tuv) or not os.path.exists(new_tuv):
        continue
    
    with open(orig_tuv, 'rb') as f:
        orig_data = f.read()
    with open(new_tuv, 'rb') as f:
        new_data = f.read()
    
    print(f"\n=== {name} ===")
    
    # Parse text header
    # Find end of first line
    orig_nl1 = orig_data.index(b'\n')
    new_nl1 = new_data.index(b'\n')
    orig_line1 = orig_data[:orig_nl1].decode('ascii', 'replace').strip()
    new_line1 = new_data[:new_nl1].decode('ascii', 'replace').strip()
    print(f"  Line1: orig=[{orig_line1}]  new=[{new_line1}]")
    
    # Second line
    orig_nl2 = orig_data.index(b'\n', orig_nl1+1)
    new_nl2 = new_data.index(b'\n', new_nl1+1)
    orig_line2 = orig_data[orig_nl1+1:orig_nl2].decode('ascii', 'replace').strip()
    new_line2 = new_data[new_nl1+1:new_nl2].decode('ascii', 'replace').strip()
    print(f"  Line2: orig=[{orig_line2}]  new=[{new_line2}]")
    
    # Show next few lines
    orig_rem = orig_data[orig_nl2+1:orig_nl2+200]
    new_rem = new_data[new_nl2+1:new_nl2+200]
    
    # Find all text lines in header
    orig_pos = 0
    new_pos = 0
    orig_lines = []
    new_lines = []
    for data, lines in [(orig_data, orig_lines), (new_data, new_lines)]:
        pos = 0
        while pos < len(data):
            nl = data.find(b'\n', pos)
            if nl == -1:
                line = data[pos:]
                if line:
                    lines.append((pos, line))
                break
            line = data[pos:nl]
            if line:
                lines.append((pos, line))
            pos = nl + 1
            # Stop after header (first ~20 lines or until non-ASCII)
            if len(lines) >= 5:
                break
    
    print(f"  Header lines: orig={len(orig_lines)} new={len(new_lines)}")
    for i in range(min(len(orig_lines), len(new_lines), 5)):
        op, ol = orig_lines[i]
        np, nl = new_lines[i]
        print(f"    L{i}: orig@0x{op:X}=[{ol[:60].decode('ascii','replace')}]  new@0x{np:X}=[{nl[:60].decode('ascii','replace')}]")
    
    # Compare binary content after header
    # Find where binary data starts (after all header lines)
    orig_hdr_end = orig_lines[-1][0] + len(orig_lines[-1][1]) + 1  # +1 for \n
    new_hdr_end = new_lines[-1][0] + len(new_lines[-1][1]) + 1
    
    print(f"  Header end: orig=0x{orig_hdr_end:X}  new=0x{new_hdr_end:X}")
    
    orig_bin = orig_data[orig_hdr_end:]
    new_bin = new_data[new_hdr_end:]
    print(f"  Binary data: orig={len(orig_bin)} bytes  new={len(new_bin)} bytes")
    
    if orig_bin == new_bin:
        print("  Binary: IDENTICAL")
    else:
        # Find first difference
        min_len = min(len(orig_bin), len(new_bin))
        first_diff = -1
        diff_count = 0
        for i in range(min_len):
            if orig_bin[i] != new_bin[i]:
                if first_diff == -1:
                    first_diff = i
                diff_count += 1
        print(f"  Binary: DIFFERENT (first diff at offset {first_diff}, {diff_count} bytes differ in {min_len})")
