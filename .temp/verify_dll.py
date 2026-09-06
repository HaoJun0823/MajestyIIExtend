# -*- coding: utf-8 -*-
"""验证编译出的 DLL：反汇编关键函数，检查状态机正确性"""
import struct
import sys

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    print("Installing capstone...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "capstone", "-q"])
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL_PATH = r"G:\Projects\MajestyIIExtend\MajestyII_UTF8\Release\MajestyII_UTF8.dll"
IMG_BASE = 0x10000000

with open(DLL_PATH, "rb") as f:
    data = f.read()

# PE parsing
e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
num_sections = struct.unpack_from("<H", data, e_lfanew + 6)[0]
opt_size = struct.unpack_from("<H", data, e_lfanew + 0x14)[0]
sec_off = e_lfanew + 24 + opt_size

sections = []
for i in range(num_sections):
    off = sec_off + i * 40
    name = data[off:off+8].rstrip(b'\x00').decode('ascii', errors='replace')
    vsize, vaddr, rsize, roff = struct.unpack_from("<IIII", data, off + 8)
    sections.append((name, vaddr, vsize, roff, rsize))

def rva_to_off(rva):
    for name, vaddr, vsize, roff, rsize in sections:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return roff + (rva - vaddr)
    return None

# Find exports
export_rva = struct.unpack_from("<I", data, e_lfanew + 24 + 0x60)[0]
print(f"Export directory RVA: 0x{export_rva:X}")

if export_rva:
    eo = rva_to_off(export_rva)
    if eo:
        num_funcs = struct.unpack_from("<I", data, eo + 0x14)[0]
        num_names = struct.unpack_from("<I", data, eo + 0x18)[0]
        func_rva = struct.unpack_from("<I", data, eo + 0x1C)[0]
        name_rva = struct.unpack_from("<I", data, eo + 0x20)[0]
        ord_rva = struct.unpack_from("<I", data, eo + 0x24)[0]
        
        fo = rva_to_off(func_rva)
        no = rva_to_off(name_rva)
        oo = rva_to_off(ord_rva)
        
        exports = {}
        for i in range(num_names):
            nr = struct.unpack_from("<I", data, no + i*4)[0]
            ordinal = struct.unpack_from("<H", data, oo + i*2)[0]
            fr = struct.unpack_from("<I", data, fo + ordinal*4)[0]
            nm_off = rva_to_off(nr)
            nm = b""
            while data[nm_off] != 0:
                nm += bytes([data[nm_off]])
                nm_off += 1
            exports[nm.decode('ascii')] = fr
        
        print(f"\nExports ({len(exports)}):")
        for name, rva in sorted(exports.items(), key=lambda x: x[1]):
            print(f"  0x{IMG_BASE+rva:08X} {name}")

# Now disassemble the .text section
text_sec = None
for s in sections:
    if s[0] == '.text':
        text_sec = s
        break

if text_sec:
    name, vaddr, vsize, roff, rsize = text_sec
    code = data[roff:roff+rsize]
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    
    print(f"\n.text section: VA=0x{IMG_BASE+vaddr:08X} size=0x{vsize:X}")
    
    # Disassemble and look for key patterns
    all_insns = list(md.disasm(code, IMG_BASE + vaddr))
    
    # Find function starts (look for our known function names via export)
    # Also search for key constants/patterns
    
    # 1. Find the state machine function (look for 'cmp byte ptr [ecx],0' pattern)
    print("\n=== Searching for state machine (sub_700036A0 equivalent) ===")
    for i, insn in enumerate(all_insns):
        if insn.mnemonic == 'cmp' and 'byte ptr [ecx]' in insn.op_str and '0' in insn.op_str:
            # Look backwards for function start
            j = i
            while j > 0:
                prev = all_insns[j-1]
                if prev.mnemonic in ('ret', 'retf', 'retn') or prev.mnemonic.startswith('ret'):
                    break
                j -= 1
            func_start = all_insns[j]
            print(f"  Found state machine at 0x{func_start.address:08X}")
            
            # Print first 40 instructions
            for k in range(j, min(j+50, len(all_insns))):
                ins = all_insns[k]
                print(f"    0x{ins.address:08X}: {ins.mnemonic} {ins.op_str}")
                if ins.mnemonic in ('ret', 'retn') and k > j+5:
                    # Check if next is a function start
                    if k+1 < len(all_insns):
                        nxt = all_insns[k+1]
                        if nxt.mnemonic in ('push', 'sub', 'mov') and 'esp' in nxt.op_str:
                            break
            break
    
    # 2. Find hook wrappers (look for pushad pattern)
    print("\n=== Searching for pushad wrappers ===")
    for i, insn in enumerate(all_insns):
        if insn.mnemonic == 'pushad':
            # Print context
            start = max(0, i-2)
            end = min(len(all_insns), i+10)
            for k in range(start, end):
                ins = all_insns[k]
                marker = " <<<" if k == i else ""
                print(f"    0x{ins.address:08X}: {ins.mnemonic} {ins.op_str}{marker}")
            print()
    
    # 3. Find ApplyHooks (look for 0x7D95F7 pattern)
    print("\n=== Searching for hook installation (0x7D95F7 etc) ===")
    for i, insn in enumerate(all_insns):
        if insn.mnemonic == 'push' and '0x7d95f7' in insn.op_str.lower():
            print(f"  Found at 0x{insn.address:08X}: {insn.mnemonic} {insn.op_str}")
            # Print surrounding context
            start = max(0, i-3)
            end = min(len(all_insns), i+10)
            for k in range(start, end):
                ins = all_insns[k]
                print(f"    0x{ins.address:08X}: {ins.mnemonic} {ins.op_str}")
            break
    
    # 4. Find zero-width patch (0xA0D810)
    print("\n=== Searching for zero-width patch (0xA0D810) ===")
    for i, insn in enumerate(all_insns):
        if insn.mnemonic == 'push' and '0xa0d810' in insn.op_str.lower():
            print(f"  Found at 0x{insn.address:08X}: {insn.mnemonic} {insn.op_str}")
            start = max(0, i-3)
            end = min(len(all_insns), i+5)
            for k in range(start, end):
                ins = all_insns[k]
                print(f"    0x{ins.address:08X}: {ins.mnemonic} {ins.op_str}")
            break
    
    # 5. Verify absolute address references to g_state1/2/3
    print("\n=== Searching for g_state references ===")
    # g_state1 is at offset in .data, look for push offset patterns
    state_refs = set()
    for insn in all_insns:
        if 'offset' in insn.op_str and '0x10008' in insn.op_str:
            state_refs.add(insn.op_str)
    if state_refs:
        print(f"  Found state references: {state_refs}")
    else:
        # Try broader search
        for insn in all_insns:
            if 'push' in insn.mnemonic and '0x100' in insn.op_str:
                # Check if it's a data section reference
                pass
    
    # 6. Check the search loop in state machine
    print("\n=== Verifying UTF-8 decode logic ===")
    # Look for: sub ebx, 0x20; and ebx, 0x0f; shl ebx, 12
    for i, insn in enumerate(all_insns):
        if insn.mnemonic == 'and' and '0xf' in insn.op_str and 'ebx' in insn.op_str:
            start = max(0, i-5)
            end = min(len(all_insns), i+15)
            print(f"  Found AND ebx,0xF at 0x{insn.address:08X}:")
            for k in range(start, end):
                ins = all_insns[k]
                print(f"    0x{ins.address:08X}: {ins.mnemonic} {ins.op_str}")
            break

print("\n=== DLL size ===")
import os
print(f"  Size: {os.path.getsize(DLL_PATH)} bytes")
print(f"  Original MJ2_fontfix.asi: ~17408 bytes")
