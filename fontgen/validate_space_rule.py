# -*- coding: utf-8 -*-
"""验证：老字典(DictRead_V2)的空格规则 = 每个 CJK 汉字后插一个空格。
   若成立 → 空格只是「断行机会」，配合 TUV 里 0 宽度的空格字形，
   视觉上毫无间距（故老版中文看起来仍是紧凑的），只是可换行。"""
import re

def load(p):
    txt = open(p, 'rb').read().decode('gbk', errors='replace')
    lines = txt.splitlines()
    d, order = {}, []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].lstrip('\ufeff').strip()
        if s.startswith('#'):
            key = s[1:].strip()
            j = i + 1
            while j < n and not lines[j].lstrip('\ufeff').strip().startswith('#'):
                j += 1
            val = '\n'.join(lines[i+1:j]).strip('\n')
            if key and key not in d:
                order.append(key)
            if key:
                d[key] = val
            i = j
        else:
            i += 1
    return d, order

CJK = re.compile(r'[\u4e00-\u9fff]')

V2 = r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\DictRead_V2.txt'
d2, _ = load(V2)

# 1) 空格前面的字符类型统计
from collections import Counter
prev = Counter()
after = Counter()
for k, v in d2.items():
    for m in re.finditer(' ', v):
        i = m.start()
        pc = v[i-1] if i > 0 else '<BOL>'
        nc = v[i+1] if i+1 < len(v) else '<EOL>'
        prev['CJK' if CJK.match(pc) else ('ASCII' if pc.isascii() else pc)] += 1
        after['CJK' if CJK.match(nc) else ('ASCII' if nc.isascii() else nc)] += 1
print("=== 空格前一个字符类型 (V2) ===")
for k, c in prev.most_common(15):
    print("   %-8s %d" % (k, c))
print("=== 空格后一个字符类型 (V2) ===")
for k, c in after.most_common(15):
    print("   %-8s %d" % (k, c))

# 2) 规则复现：对 V2 每个值先压紧(删掉所有空格)，再按规则插空格，比较是否与 V2 一致
def respace(s):
    # 规则 A：每个 CJK 汉字后插一个空格
    out = []
    for i, ch in enumerate(s):
        out.append(ch)
        if CJK.match(ch):
            nxt = s[i+1] if i+1 < len(s) else ''
            if nxt != ' ':
                out.append(' ')
    return ''.join(out)

mismatch = 0
samples = []
for k, v in d2.items():
    compact = v.replace(' ', '')
    got = respace(compact)
    if got != v:
        mismatch += 1
        if len(samples) < 5:
            samples.append((k, v, got))
print("\n=== 规则A(每汉字后插空格) 与 V2 不一致的条目数: %d / %d ===" % (mismatch, len(d2)))
for k, v, g in samples:
    print("   #%s\n     V2 =%r\n     规则=%r" % (k, v[:120], g[:120]))

# 3) 各版本字典的空格风格
print("\n=== 各版本空格风格 ===")
import os
base = r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update'
for name in ("DictRead.txt", "DictRead_V2.txt", "DictRead_V3.txt", "DictRead_V4.txt",
             "DictRead_V6.txt", "DictRead_V7.txt", "DictRead_V7_CHT.txt"):
    p = os.path.join(base, name)
    if not os.path.exists(p):
        print("   %-24s (缺失)" % name); continue
    dd, _ = load(p)
    sp = 0; comp = 0; other = 0
    for v in dd.values():
        n = len(CJK.findall(v))
        if n == 0:
            continue
        s = sum(1 for i, c in enumerate(v[:-1]) if CJK.match(c) and v[i+1] == ' ')
        r = s / n
        if r >= 0.8: sp += 1
        elif r <= 0.2: comp += 1
        else: other += 1
    print("   %-24s 空格风格=%d 紧凑=%d 混合=%d  (size=%d)" % (name, sp, comp, other, os.path.getsize(p)))
