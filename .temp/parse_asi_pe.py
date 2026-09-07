#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse PE sections of two ASI files for comparison."""
import struct
import sys

def parse_pe(path):
    with open(path, 'rb') as f:
        data = f.read()
    print(f"\n=== {path} ({len(data)} bytes) ===")
    pe_off = struct.unpack_from('<I', data, 0x3C)[0]
    sig = data[pe_off:pe_off+4]
    print(f"  PE sig: {sig}")
    machine = struct.unpack_from('<H', data, pe_off+4)[0]
    n_sec = struct.unpack_from('<H', data, pe_off+6)[0]
    opt_size = struct.unpack_from('<H', data, pe_off+0x14)[0]
    opt_off = pe_off + 0x18
    img_base = struct.unpack_from('<I', data, opt_off + 0x1C)[0]
    print(f"  Machine=0x{machine:X}  Sections={n_sec}  ImageBase=0x{img_base:X}  OptSize=0x{opt_size:X}")
    
    sec_off = opt_off + opt_size
    print(f"  Section table at 0x{sec_off:X}")
    for i in range(n_sec):
        off = sec_off + i * 40
        name = data[off:off+8].rstrip(b'\x00')
        vsize, vaddr, rsize, raddr = struct.unpack_from('<IIII', data, off+8)
        chars = struct.unpack_from('<I', data, off+36)[0]
        prot = ''
        if chars & 0x20000000: prot += 'X'
        if chars & 0x40000000: prot += 'R'
        if chars & 0x80000000: prot += 'W'
        end_va = vaddr + vsize
        print(f"  {name.decode('ascii','replace'):<10} VA=0x{vaddr:06X} VEnd=0x{end_va:06X} VSize=0x{vsize:06X} Raw=0x{raddr:06X} RSize=0x{rsize:06X} Chars=0x{chars:08X} {prot}")
    
    # Check if 0x875d8 falls in any section
    target_rva = 0x875d8
    print(f"\n  RVA 0x{target_rva:X} analysis:")
    for i in range(n_sec):
        off = sec_off + i * 40
        vsize, vaddr, rsize, raddr = struct.unpack_from('<IIII', data, off+8)
        if vaddr <= target_rva < vaddr + vsize:
            file_off = raddr + (target_rva - vaddr)
            in_raw = raddr <= file_off < raddr + rsize
            print(f"    -> In section {data[off:off+8].rstrip(b'\\x00').decode('ascii','replace')} (VA=0x{vaddr:X}~0x{vaddr+vsize:X})")
            print(f"    -> File offset 0x{file_off:X}, in raw data: {in_raw}")
            if in_raw and file_off < len(data):
                content = data[file_off:file_off+32]
                print(f"    -> Content: {content.hex(' ')}")
            break
    else:
        print(f"    -> NOT in any section (gap/hole)")

parse_pe(r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\MajestyII_UTF8.asi")
parse_pe(r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\MajestyII_UTF8.asi.bak")
