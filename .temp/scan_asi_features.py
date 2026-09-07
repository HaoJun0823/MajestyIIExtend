# -*- coding: utf-8 -*-
"""扫描部署 ASI 二进制特征，确认其包含哪些代码模块"""
import struct, sys, os

path = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\MajestyII_UTF8.asi"
data = open(path, "rb").read()
print(f"文件: {path}")
print(f"大小: {len(data)} bytes")

# 1. 字符串特征
def find_bytes(pat):
    return [i for i in range(len(data)) if data[i:i+len(pat)] == pat]

print("\n=== 字符串特征 ===")
for s in [b"DictRead.txt", b"hook_debug", b"HIT", b"MISS", b"LoadDict", b"Majesty", b"charlist", b".txt", b"utf-8", b"gbk", b"GPL", b"LogWrite"]:
    hits = find_bytes(s)
    print(f"  {s!r}: {len(hits)} 处 {[hex(x) for x in hits[:5]]}")

# 2. 关键 DWORD 常量 (LE)
def find_dword(v):
    b = struct.pack("<I", v)
    return [i for i in range(len(data)-3) if data[i:i+4] == b]

print("\n=== 关键常量 ===")
consts = {
    0x0077593E: "g_hookRetAddr (jmp back target)",
    0x00775939: "texts hook 目标地址",
    0x7D95F7: "GBK hook 1",
    0x7D9DAA: "GBK hook 2",
    0x7E1A53: "GBK hook 3",
    0x7E235D: "GBK hook 4",
    0x775510: "LocalizeKey 函数地址",
    0x10000000: "镜像基址",
}
for v, name in consts.items():
    hits = find_dword(v)
    print(f"  0x{v:08X} ({name}): {len(hits)} 处", [hex(x) for x in hits[:8]])

# 3. E9 jmp hook 指令扫描 (E9 xx xx xx xx)
print("\n=== E9 jmp 指令 (hook 点候选) ===")
jmp_count = 0
for i in range(len(data)-5):
    if data[i] == 0xE9:
        rel = struct.unpack("<i", data[i+1:i+5])[0]
        target = (0x10000000 + i) + 5 + rel  # 以镜像基址计算
        # 只打印指向游戏模块常用区的 jmp
        if 0x00700000 <= target <= 0x00800000:
            jmp_count += 1
            print(f"  文件偏移 0x{i:05X} (镜像 0x{0x10000000+i:08X}) -> 0x{target:08X}")
print(f"  共 {jmp_count} 个指向 0x7xxxxx 的 jmp")

# 3. PE 段信息
print("\n=== PE 段 ===")
pe = struct.unpack("<I", data[0x3C:0x40])[0]
nsec = struct.unpack("<H", data[pe+6:pe+8])[0]
opt = pe + 24
magic = struct.unpack("<H", data[opt:opt+2])[0]
sec_off = opt + (112 if magic == 0x10b else 240)
print(f"  PE 偏移 0x{pe:X}, 段数 {nsec}, magic 0x{magic:X}")
for i in range(nsec):
    off = sec_off + i*40
    name = data[off:off+8].rstrip(b'\0').decode('latin1')
    vsize, va, rawsize, rawoff = struct.unpack("<IIII", data[off+8:off+24])
    print(f"  {name:8s} VA=0x{va:08X} VSize=0x{vsize:08X} RawOff=0x{rawoff:08X} RawSize=0x{rawsize:08X}")

# 4. .data 段 BSS 大小验证 (g_hashTable)
print("\n=== BSS 检查 (.data VSize vs RawSize) ===")
for i in range(nsec):
    off = sec_off + i*40
    name = data[off:off+8].rstrip(b'\0').decode('latin1')
    vsize = struct.unpack("<I", data[off+12:off+16])[0]
    rawsize = struct.unpack("<I", data[off+20:off+24])[0]
    if name == ".data":
        print(f"  .data VSize=0x{vsize:X} RawSize=0x{rawsize:X} BSS={vsize-rawsize} bytes")