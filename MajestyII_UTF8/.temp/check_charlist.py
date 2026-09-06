# -*- coding: utf-8 -*-
# 验证：原版 GBK charlist 顺序 与 我们的 Unicode charlist 是否一一对应
import re

def parse_charlist(path, pattern, src_encoding):
    with open(path, 'r', encoding=src_encoding, errors='replace') as f:
        src = f.read()
    m = re.search(pattern, src, re.S)
    if not m:
        raise ValueError('pattern not found in ' + path)
    arr = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{4})', m.group(1))]
    while arr and arr[-1] == 0:
        arr.pop()
    return arr

# 1. 原版 GBK charlist
gbk = parse_charlist(
    r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\源码\MJ2_fontfix\MJ2_fontfix.cpp',
    r'static const WORD g_charlist_data\[\] = \{(.*?)\};',
    'utf-8')

# 2. 我们的 Unicode charlist
uni = parse_charlist(
    r'G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h',
    r'static const unsigned short g_charlist\[\] = \{(.*?)\};',
    'utf-8')

print('原版 GBK 条目:', len(gbk))
print('我们 Unicode 条目:', len(uni))
print('原版前8:', ['%04X' % x for x in gbk[:8]])
print('我们前8:', ['%04X' % x for x in uni[:8]])

def gbk2uni(b1, b2):
    try:
        return ord(bytes([b1, b2]).decode('gbk'))
    except Exception:
        return -1

print()
print('=== 逐位置对比: 原版GBK码->Unicode 与 我们的值 ===')
mismatch = 0
limit = min(len(gbk), len(uni))
for i in range(limit):
    u = gbk2uni(gbk[i] >> 8, gbk[i] & 0xFF)
    if u != uni[i]:
        if mismatch < 20:
            tag = '<<< 不匹配' if u != uni[i] else 'OK'
            print('位置 %d: 原版GBK=%04X 正确Unicode=%04X 我们=%04X %s' % (i, gbk[i], u, uni[i], tag))
        mismatch += 1
print('总不匹配: %d / 对比 %d' % (mismatch, limit))
print('长度差: 原版%d vs 我们%d' % (len(gbk), len(uni)))