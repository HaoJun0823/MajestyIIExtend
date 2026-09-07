#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare DDS content between original and new fonts."""
import hashlib
import os

orig_dir = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\字体生成\Original_Fonts"
new_dir = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\resource.mod\Fonts"

# Get all DDS files
orig_dds = sorted([f for f in os.listdir(orig_dir) if f.endswith('.dds')])
new_dds = sorted([f for f in os.listdir(new_dir) if f.endswith('.dds')])

print("=== DDS files in Original_Fonts ===")
for f in orig_dds:
    path = os.path.join(orig_dir, f)
    with open(path, 'rb') as fh:
        h = hashlib.md5(fh.read()).hexdigest()
    print(f"  {f}: {os.path.getsize(path)} bytes  MD5={h[:16]}")

print("\n=== DDS files in update/resource.mod/Fonts ===")
for f in new_dds:
    path = os.path.join(new_dir, f)
    with open(path, 'rb') as fh:
        h = hashlib.md5(fh.read()).hexdigest()
    print(f"  {f}: {os.path.getsize(path)} bytes  MD5={h[:16]}")

print("\n=== DDS MD5 comparison ===")
for f in orig_dds:
    orig_path = os.path.join(orig_dir, f)
    new_path = os.path.join(new_dir, f)
    if not os.path.exists(new_path):
        print(f"  {f}: MISSING in update")
        continue
    with open(orig_path, 'rb') as fh:
        h1 = hashlib.md5(fh.read()).hexdigest()
    with open(new_path, 'rb') as fh:
        h2 = hashlib.md5(fh.read()).hexdigest()
    if h1 == h2:
        print(f"  {f}: SAME (both original)")
    else:
        print(f"  {f}: DIFFERENT (new font!)")
