#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check TUV header format of new vs original fonts."""
import struct
import os

orig_dir = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\字体生成\Original_Fonts"
new_dir = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\resource.mod\Fonts"

fonts = ["font12", "font14", "font18", "console", "small", "big_caption", "med_caption", "paragraph"]

for name in fonts:
    orig_tuv = os.path.join(orig_dir, name + ".tuv")
    new_tuv = os.path.join(new_dir, name + ".tuv")
    
    if not os.path.exists(orig_tuv) or not os.path.exists(new_tuv):
        print(f"{name}: TUV not found (orig={os.path.exists(orig_tuv)}, new={os.path.exists(new_tuv)})")
        continue
    
    with open(orig_tuv, 'rb') as f:
        orig_data = f.read()
    with open(new_tuv, 'rb') as f:
        new_data = f.read()
    
    print(f"\n=== {name} ===")
    print(f"  Orig: {len(orig_data)} bytes  New: {len(new_data)} bytes")
    
    # Parse TUV header
    orig_count = struct.unpack_from('<I', orig_data, 0)[0]
    new_count = struct.unpack_from('<I', new_data, 0)[0]
    print(f"  TUVCOUNT: orig={orig_count}  new={new_count}")
    
    # Compare more header fields
    print(f"  Orig[0:20]: {orig_data[:20].hex(' ')}")
    print(f"  New [0:20]: {new_data[:20].hex(' ')}")
    
    # Check DDS dimensions from TUV header (offset 4: width, height)
    if len(orig_data) >= 12 and len(new_data) >= 12:
        orig_w, orig_h = struct.unpack_from('<II', orig_data, 4)
        new_w, new_h = struct.unpack_from('<II', new_data, 4)
        print(f"  TUVBASE: orig={orig_w}x{orig_h}  new={new_w}x{new_h}")
    
    # Also check DDS files
    for suffix in ['', 'a', 'b', '_c']:
        dds_name = name + suffix + ".dds"
        orig_dds = os.path.join(orig_dir, dds_name)
        new_dds = os.path.join(new_dir, dds_name)
        if os.path.exists(orig_dds) and os.path.exists(new_dds):
            osz = os.path.getsize(orig_dds)
            nsz = os.path.getsize(new_dds)
            match = "OK" if osz == nsz else "MISMATCH"
            print(f"  {dds_name}: orig={osz} new={nsz} {match}")
        elif os.path.exists(new_dds) and not os.path.exists(orig_dds):
            print(f"  {dds_name}: new only ({os.path.getsize(new_dds)} bytes)")
