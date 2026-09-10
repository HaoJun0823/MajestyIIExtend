#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「GB18030 / GBK 字节序」字表写入 DLL 源，使 DLL 回到与老字库兼容的 GB18030 序。

单一数据源：fontgen/charlist_full_gb18030.txt
  - 由 gen_full_gb18030.py 生成：完整 GB18030 双字节平面（GBK 字节序，23940 字）
  - 这是用户确认“与老字库兼容、中文能正常显示”的序

动作：
  - 备份 dllmain.cpp / charlist_data.h
  - 重写 g_charlist_data[] = 文件序 GBK 值 + 0x0000 终结符
  - 重写 charlist_data.h 的 charlist[] = 同序 Unicode 码点 + 0x0000
  - charlist_count = 字数
注：贴图不在此脚本生成；贴图用 build_font_atlas 的 charlist_source=dll 模式，
    直接从本脚本写好的 g_charlist_data[] 派生，二者物理同源，不可能错位。
"""
import re, os, shutil

ROOT = r"G:/Projects/MajestyIIExtend"
FONTGEN = os.path.join(ROOT, "fontgen")
CPP = os.path.join(ROOT, "MajestyII_UTF8", "dllmain.cpp")
HDR = os.path.join(ROOT, "MajestyII_UTF8", "charlist_data.h")
CHARLIST = os.path.join(FONTGEN, "charlist_full_gb18030.txt")

hx = lambda n: f"0x{n:04X}"

data = open(CHARLIST, "rb").read()
assert len(data) % 2 == 0, "字表字节数应为偶数"
gbk_words = [(data[i] << 8) | data[i + 1] for i in range(0, len(data), 2)]
print(f"[数据源] {os.path.basename(CHARLIST)}: {len(gbk_words)} 字（GB18030/GBK 字节序）")
# 文件中每个「值」以小端字节序存放（data[2k]<<8|data[2k+1] = 小端字 L），
# 解码回字符须按内存字节顺序 (L&0xFF, L>>8)。
dec = lambda w: bytes([w & 0xFF, (w >> 8) & 0xFF]).decode("gbk", "replace")
first8 = "".join(dec(w) for w in gbk_words[:8])
print(f"[数据源] 首 8 字（GBK 字节序，通常为 GBK 首字…）: {first8!r}")

uni_points = []
for w in gbk_words:
    try:
        uni_points.append(ord(dec(w)))
    except Exception:
        uni_points.append(0xFFFD)

# 备份
for f in (CPP, HDR):
    bak = f + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(f, bak)
        print(f"[备份] {os.path.basename(f)} -> {os.path.basename(bak)}")
    else:
        print(f"[备份] {os.path.basename(f)}.bak 已存在，跳过（保留首次备份）")

def fmt_block(values, per_line=8):
    lines = []
    for i in range(0, len(values), per_line):
        chunk = values[i:i + per_line]
        comma = "," if i + per_line < len(values) else ""
        lines.append("  " + ", ".join(chunk) + comma)
    return "\n".join(lines)

src = open(CPP, encoding="utf-8", errors="ignore").read()
new_block_gbk = fmt_block([hx(w) for w in gbk_words]) + ",\n  0x0000"
src2 = re.sub(r"(g_charlist_data\[\]\s*=\s*\{).*?(\n\};)",
              lambda mm: mm.group(1) + "\n" + new_block_gbk + mm.group(2),
              src, count=1, flags=re.S)
assert src2 != src, "g_charlist_data 替换未生效"
open(CPP, "w", encoding="utf-8").write(src2)
print(f"[写入] g_charlist_data[] -> {len(gbk_words)} 项 + 0x0000")

hdr = open(HDR, encoding="utf-8", errors="ignore").read()
new_block_uni = fmt_block([hx(u) for u in uni_points]) + ",\n  0x0000  // terminator"
hdr2 = re.sub(r"(charlist\[\]\s*=\s*\{).*?(\n\};)",
              lambda mm: mm.group(1) + "\n" + new_block_uni + mm.group(2),
              hdr, count=1, flags=re.S)
assert hdr2 != hdr, "charlist[] 替换未生效"
hdr2 = re.sub(r"charlist_count\s*=\s*\d+", f"charlist_count = {len(gbk_words)}", hdr2)
open(HDR, "w", encoding="utf-8").write(hdr2)
print(f"[写入] charlist[] -> {len(uni_points)} 项, charlist_count = {len(gbk_words)}")

# 回读校验
c2 = open(CPP, encoding="utf-8", errors="ignore").read()
m2 = re.search(r"g_charlist_data\[\]\s*=\s*\{(.*?)\};", c2, re.S)
w2 = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{4})", m2.group(1)) if int(x, 16) != 0]
assert w2 == gbk_words, "回读 g_charlist_data 与数据源不符"
print("[回读] ✅ DLL 源已更新为 GB18030 序且自检通过")
print("✅ 完成：DLL g_charlist_data[] 现为 GB18030/GBK 字节序（与老字库兼容）。贴图请用 build_font_atlas 的 charlist_source=dll 派生。")
