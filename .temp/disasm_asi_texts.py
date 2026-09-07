# -*- coding: utf-8 -*-
"""反汇编当前部署 ASI 的 texts() 函数 - 找 push ebx;push edx;push edi;push ebp 特征并反汇编"""
import struct

path = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\MajestyII_UTF8.asi"
data = open(path, "rb").read()

# 精确解析 PE 段
pe = struct.unpack("<I", data[0x3C:0x40])[0]
nsec = struct.unpack("<H", data[pe+6:pe+8])[0]
opt = pe + 24
magic = struct.unpack("<H", data[opt:opt+2])[0]
sec_off = opt + (112 if magic == 0x10b else 240)
imgbase = struct.unpack("<I", data[opt+28:opt+32])[0]
print(f"PE={pe:#x} nsec={nsec} magic={magic:#x} ImageBase={imgbase:#x}")

secs = []
for i in range(nsec):
    off = sec_off + i*40
    name = data[off:off+8].rstrip(b'\0').decode('latin1')
    vsize, va, rawsize, rawoff = struct.unpack("<IIII", data[off+8:off+24])
    secs.append((name, va, vsize, rawoff, rawsize))
    print(f"  {name:8s} VA={va:#08x} VSize={vsize:#08x} RawOff={rawoff:#08x} RawSize={rawsize:#08x}")

def va_to_off(va):
    for name, sva, svsize, roff, rsize in secs:
        if sva <= va < sva + max(vsize, rsize):
            return roff + (va - sva)
    return None

# 找 texts() 特征: 53 57 52 55 (push ebx;push edi;push edx;push ebp 的某种顺序)
# 源码: push ebx; push edx; push edi; push ebp => 53 52 57 55
pat = bytes([0x53, 0x52, 0x57, 0x55])
print("\n=== texts 入口候选 (push ebx;push edx;push edi;push ebp) ===")
idx = 0
while True:
    i = data.find(pat, idx)
    if i < 0: break
    print(f"  RawOff=0x{i:X}  (VA=0x{imgbase+i:X})  后续: {data[i+4:i+20].hex(' ')}")
    idx = i + 1

# 找 mov ecx,[esp+0x34] = 8B 4C 24 34 或 [esp+0x24+16] 等价
print("\n=== mov ecx,[esp+imm] 候选 ===")
idx = 0
while True:
    i = data.find(b'\x8b\x4c\x24', idx)
    if i < 0: break
    print(f"  文件Off=0x{i:X}: 8B 4C 24 {data[i+3]:02X} (esp+0x{data[i+3]:X})")
    idx = i + 1

# g_hookRetAddr 引用处 0x5114 附近上下文
print("\n=== g_hookRetAddr (0x5114) 附近 64 字节 ===")
off = 0x5114
print(data[off-0x20:off+0x20].hex(' '))
print(data[off-0x20:off+0x20].hex(' '))

# E9 相对跳转扫描: texts 函数内最后 jmp [g_hookRetAddr] 是 FF 25
print("\n=== jmp dword ptr [mem32] (FF 25) 特征 ===")
idx = 0
while True:
    i = data.find(b'\xff\x25', idx)
    if i < 0: break
    print(f"  文件Off=0x{i:X} target_mem={struct.unpack('<I', data[i+2:i+6])[0]:#x}")
    idx = i + 1

# 检查 E9 调用 (hook 安装时构造的 jmp): 找 mov [..], 0x775939 的常量写入位置 0x80a
print("\n=== 0x80a (mov [esp..], 0x775939) 附近 ===")
print(data[0x7E0:0x840].hex(' '))