# -*- coding: utf-8 -*-
"""验证修正后的状态机返回值"""
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

text_sec = [s for s in sections if s[0] == '.text'][0]
code = data[text_sec[3]:text_sec[3]+text_sec[4]]
md = Cs(CS_ARCH_X86, CS_MODE_32)
all_insns = list(md.disasm(code, IMG_BASE + text_sec[1]))

# Find and print the state machine function
print("=== State Machine (sub_700036A0) ===")
in_func = False
for insn in all_insns:
    if insn.address >= 0x10001600 and insn.address < 0x100016A0:
        print(f"  0x{insn.address:08X}: {insn.mnemonic:8s} {insn.op_str}")

# Verify: _caseState1 should now return 0xDF (not 0xFF)
print("\n=== Key checks ===")
for insn in all_insns:
    if 0x10001677 <= insn.address <= 0x10001687:
        print(f"  _caseState1: 0x{insn.address:08X}: {insn.mnemonic:8s} {insn.op_str}")

print()
for insn in all_insns:
    if 0x10001688 <= insn.address <= 0x1000169D:
        print(f"  _caseState0: 0x{insn.address:08X}: {insn.mnemonic:8s} {insn.op_str}")

# Check wrapper2: _cmp eax,0xff should now NOT match for 0xDF returns
print("\n=== Wrapper2 (sub_700037B0) ===")
for insn in all_insns:
    if 0x100016E0 <= insn.address <= 0x10001720:
        print(f"  0x{insn.address:08X}: {insn.mnemonic:8s} {insn.op_str}")
