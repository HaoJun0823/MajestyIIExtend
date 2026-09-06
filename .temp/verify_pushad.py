# -*- coding: utf-8 -*-
"""检查 pushad 是否被优化掉，以及 hook wrapper 的实际形态"""
import struct
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DLL_PATH = r"G:\Projects\MajestyIIExtend\MajestyII_UTF8\Release\MajestyII_UTF8.dll"
IMG_BASE = 0x10000000

with open(DLL_PATH, "rb") as f:
    data = f.read()

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

text_sec = [s for s in sections if s[0] == '.text'][0]
code = data[text_sec[3]:text_sec[3]+text_sec[4]]
md = Cs(CS_ARCH_X86, CS_MODE_32)
md.detail = True
all_insns = list(md.disasm(code, IMG_BASE + text_sec[1]))

# Print the full .text disassembly from 0x10001600 to end
print("=== Full disassembly from state machine to end ===")
for insn in all_insns:
    if insn.address >= 0x10001600:
        print(f"0x{insn.address:08X}: {insn.mnemonic:8s} {insn.op_str}")

print("\n\n=== ApplyHooks function (search for 0x7D95F7) ===")
# Find and print the full ApplyHooks
for i, insn in enumerate(all_insns):
    if insn.mnemonic == 'push' and '0x7d95f7' in insn.op_str.lower():
        # Find function start
        j = i
        while j > 0:
            prev = all_insns[j-1]
            if prev.mnemonic in ('ret', 'retn') and j > 3:
                # Check if this ret is the end of a previous function
                break
            j -= 1
        # Print from j to next ret
        for k in range(j, len(all_insns)):
            ins = all_insns[k]
            print(f"0x{ins.address:08X}: {ins.mnemonic:8s} {ins.op_str}")
            if ins.mnemonic in ('ret', 'retn') and k > i + 20:
                break
        break
