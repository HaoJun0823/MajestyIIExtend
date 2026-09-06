#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从原版 MJ2_fontfix.cpp 提取 charlist，还原 GBK 组合值并解码为 Unicode 码点，
生成 UTF-8 版本 charlist_data.h。顺序保持与原版一致（字形表索引不变）。"""
import re
import sys

SRC = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\源码\MJ2_fontfix\MJ2_fontfix.cpp"
OUT = r"G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h"

def uncomb(comb):
    """charlist 存储值 = ((GBK_tail+0x20)<<8) | (GBK_lead+0x20)"""
    lead = (comb & 0xFF) - 0x20
    tail = (comb >> 8) - 0x20
    return lead, tail

def gbk_to_unicode(lead, tail):
    """GBK 双字节 → Unicode 码点；失败返回 None"""
    b = bytes([lead, tail])
    for enc in ('gb18030', 'gbk'):
        try:
            return ord(b.decode(enc))
        except Exception:
            continue
    return None

def main():
    with open(SRC, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    m = re.search(r'static const WORD g_charlist_data\[\]\s*=\s*\{(.*?)\};', content, re.DOTALL)
    if not m:
        print("ERROR: charlist array not found", file=sys.stderr)
        sys.exit(1)
    vals = [int(v, 16) for v in re.findall(r'0x([0-9A-Fa-f]+)', m.group(1))]
    # 去掉结尾终止符 0x0000
    if vals and vals[-1] == 0:
        vals = vals[:-1]
    print(f"raw entries: {len(vals)}")

    unicode_pts = []
    kept_raw = []
    undecodable = 0
    for comb in vals:
        lead, tail = uncomb(comb)
        if not (0x81 <= lead <= 0xFE and 0x40 <= tail <= 0xFE):
            # 非 GBK 合法区，保留原组合值
            unicode_pts.append(comb)
            kept_raw.append(comb)
            continue
        cp = gbk_to_unicode(lead, tail)
        if cp is None:
            # 无法解码的 GB 扩展字符，保留原值
            unicode_pts.append(comb)
            kept_raw.append(comb)
            undecodable += 1
        else:
            unicode_pts.append(cp)

    print(f"unicode entries: {len(unicode_pts)}, undecodable kept raw: {len(kept_raw)}")

    # 验证：Unicode 码点必须在 16 位内
    over = [cp for cp in unicode_pts if cp > 0xFFFF]
    if over:
        print(f"WARN: {len(over)} codepoints exceed 0xFFFF")
    dup = len(unicode_pts) - len(set(unicode_pts))
    print(f"duplicates: {dup}")

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write("// Auto-generated charlist data - DO NOT EDIT\n")
        f.write(f"// Total entries: {len(unicode_pts)} (excluding 0x0000 terminator)\n")
        f.write("// Each entry is a Unicode codepoint (was GBK combo in original)\n")
        f.write("// Glyph index = array_position + 0x100\n\n")
        f.write("static const WORD g_charlist_data[] = {\n")
        for i in range(0, len(unicode_pts), 8):
            chunk = unicode_pts[i:i+8]
            line = ", ".join(f"0x{v:04X}" for v in chunk)
            if i + 8 < len(unicode_pts):
                line += ","
            f.write(f"    {line}\n")
        f.write("    ,0x0000  // terminator\n")
        f.write("};\n\n")
        f.write(f"static const int g_charlist_count = {len(unicode_pts)};\n")
    print(f"written: {OUT}")

    # 验证抽查
    for ch in ['啊', '中', '文', '王', '权', '。', '，']:
        cp = ord(ch)
        if cp in unicode_pts:
            print(f"  OK: U+{cp:04X} ({ch}) at index {unicode_pts.index(cp)}")
        else:
            print(f"  MISS: U+{cp:04X} ({ch})")

if __name__ == '__main__':
    main()