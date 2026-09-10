# -*- coding: utf-8 -*-
"""最终核验：
(a) dllmain.cpp 的 g_charlist_data 与部署 asi 内的是否完整一致
(b) 16 个字体各自的空槽位置 vs 字典用字（找「按字体缺字」）
(c) 字体重复性检测（TUV 内容哈希）
"""
import re, struct, zipfile, hashlib, os
from collections import Counter, defaultdict

R = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection"
UPD = os.path.join(R, "update")
SRC = r"G:\Projects\MajestyIIExtend\MajestyII_UTF8\dllmain.cpp"
ASI = os.path.join(UPD, "MajestyII_UTF8.asi")
ZIP = os.path.join(UPD, "localization", "texts", "texts.zip")


def src_charlist():
    src = open(SRC, "rb").read().decode("utf-8", errors="replace")
    lines = src.splitlines()
    s = [i for i, l in enumerate(lines) if "g_charlist_data[]" in l and "=" in l][0]
    e = [j for j in range(s + 1, len(lines)) if lines[j].strip().startswith("};")][0]
    vals = []
    for l in lines[s:e + 1]:
        for m in re.finditer(r'0[xX]([0-9A-Fa-f]{4})', l):
            vals.append(int(m.group(1), 16))
    return vals


vals = src_charlist()
print("(a) 源 charlist 项数 =", len(vals))
ser = b"".join(struct.pack("<H", v) for v in vals)
asi = open(ASI, "rb").read()
off = asi.find(ser)
print("    源字表在部署 asi 中完整匹配:", off >= 0, hex(off) if off >= 0 else "")
if off < 0:
    # 找最长匹配前缀
    lo, hi = 0, len(ser)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if asi.find(ser[:mid]) >= 0:
            lo = mid
        else:
            hi = mid - 1
    print("    最长匹配前缀 = %d / %d 项" % (lo // 2, len(vals)))

idx = {}
for i, v in enumerate(vals):
    if v not in idx:
        idx[v] = i

zf = zipfile.ZipFile(ZIP)
tuvs = sorted(n for n in zf.namelist() if n.lower().endswith(".tuv"))


def load_rects(name):
    txt = zf.read(name).decode("utf-8", errors="replace")
    out = []
    for l in txt.splitlines():
        p = l.split()
        if len(p) == 4 and p[0].lstrip("-").isdigit():
            out.append(tuple(map(int, p)))
    return out


print("\n(c) 字体重复性（TUV sha1 前缀 + 条目/尺寸）")
h = {}
for n in tuvs:
    raw = zf.read(n)
    d = hashlib.sha1(raw).hexdigest()[:10]
    rs = load_rects(n)
    cw = Counter(x[2] - x[0] for x in rs[224:] if x[2] > x[0])
    ch = Counter(x[3] - x[1] for x in rs[224:] if x[3] > x[1])
    cjk = (cw.most_common(1)[0][0] if cw else None, ch.most_common(1)[0][0] if ch else None)
    print("   %-24s sha1=%s n=%d CJKcell=%s slot0=%s" % (n.split('/')[-1], d, len(rs), cjk, rs[0]))
    h.setdefault(d, []).append(n.split('/')[-1])
print("   完全相同的字体组:")
for d, ns in h.items():
    if len(ns) > 1:
        print("     ", ns)

print("\n(b) 按字体检查字典用字是否落在空槽")
d, order = {}, []
raw = open(os.path.join(UPD, "DictRead.txt"), "rb").read().decode("gbk", errors="replace")
lines = raw.splitlines()
i = 0
while i < len(lines):
    s = lines[i].strip()
    if s.startswith("#"):
        k = s[1:].strip()
        j = i + 1
        while j < len(lines) and not lines[j].strip().startswith("#"):
            j += 1
        if k:
            d[k] = "\n".join(lines[i + 1:j]).strip("\n")
            order.append(k)
        i = j
    else:
        i += 1

# 收集字典里用到的 CJK 槽
need = set()
for k in order:
    for ch in d[k]:
        b = ch.encode("gbk", errors="replace")
        if len(b) == 2:
            L = b[0] | (b[1] << 8)
            j = idx.get(L)
            if j is not None:
                need.add(224 + j)
print("   字典用到 CJK 槽数 =", len(need))
bad = {}
for n in tuvs:
    rs = load_rects(n)
    miss = [s for s in need if s < len(rs) and (rs[s][2] <= rs[s][0] or rs[s][3] <= rs[s][1])]
    oob = [s for s in need if s >= len(rs)]
    if miss or oob:
        bad[n] = (len(miss), len(oob))
print("   有缺字的字体:", bad if bad else "无（全部字体都覆盖）")
