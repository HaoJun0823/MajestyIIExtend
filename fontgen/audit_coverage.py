# -*- coding: utf-8 -*-
"""全字典 × 贴图 覆盖性体检：
1) 从 dllmain.cpp 提取 g_charlist_data（部署字表）
2) 在部署的 asi 里核对同源
3) 载入 texts.zip 各 TUV
4) 遍历字典所有字符，找出「查不到」或「贴图空槽」的字，按 key 汇总
"""
import os, re, sys, struct, zipfile, io
from collections import defaultdict, Counter

BASE = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection"
UPD = os.path.join(BASE, "update")
SRC = r"G:\Projects\MajestyIIExtend\MajestyII_UTF8\dllmain.cpp"
ASI = os.path.join(UPD, "MajestyII_UTF8.asi")
ZIP = os.path.join(UPD, "localization", "texts", "texts.zip")


def extract_charlist_from_src():
    src = open(SRC, "rb").read().decode("utf-8", errors="replace")
    lines = src.splitlines()
    start = None
    for i, l in enumerate(lines):
        if "g_charlist_data[]" in l and "=" in l:
            start = i
            break
    if start is None:
        raise RuntimeError("cannot find g_charlist_data")
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j].strip().startswith("};"):
            end = j
            break
    vals = []
    for l in lines[start:end + 1]:
        for m in re.finditer(r'0[xX]([0-9A-Fa-f]{4})', l):
            vals.append(int(m.group(1), 16))
    return vals


def load_dict(p):
    raw = open(p, "rb").read()
    txt = raw.decode("gbk", errors="replace")
    lines = txt.splitlines()
    d = {}
    order = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith("#"):
            k = s[1:].strip()
            j = i + 1
            while j < n and not lines[j].strip().startswith("#"):
                j += 1
            v = "\n".join(lines[i + 1:j]).strip("\n")
            if k and k not in d:
                order.append(k)
            if k:
                d[k] = v
            i = j
        else:
            i += 1
    return d, order


def load_tuv(zf, name):
    txt = zf.read(name).decode("utf-8", errors="replace")
    lines = txt.splitlines()
    rects = []
    start = None
    for i, l in enumerate(lines):
        p = l.split()
        if len(p) == 4 and all(x.lstrip("-").isdigit() for x in p):
            start = i
            break
    for l in lines[start:]:
        p = l.split()
        if len(p) == 4:
            try:
                rects.append(tuple(map(int, p)))
            except Exception:
                pass
    return rects


def main():
    vals = extract_charlist_from_src()
    print("源 g_charlist_data entries = %d ; first=%s last=%s" % (len(vals), hex(vals[0]), hex(vals[-1])))
    ser = b"".join(struct.pack("<H", v) for v in vals)
    asi = open(ASI, "rb").read()
    off = asi.find(ser[:128])
    print("部署 asi 内字表定位: %s" % (hex(off) if off >= 0 else "NOT FOUND (不同源!)"))

    idx = {}
    for i, v in enumerate(vals):
        if v not in idx:
            idx[v] = i
    print("唯一值数 = %d (重复 %d)" % (len(idx), len(vals) - len(idx)))

    zf = zipfile.ZipFile(ZIP)
    tuvs = sorted(n for n in zf.namelist() if n.lower().endswith(".tuv"))
    print("\n=== texts.zip TUV 清单 ===")
    tuv = {}
    for n in tuvs:
        r = load_tuv(zf, n)
        tuv[n] = r
        blank = sum(1 for x in r if x[2] <= x[0] or x[3] <= x[1])
        print("  %-38s entries=%5d blank=%5d" % (n.rsplit("/", 1)[-1], len(r), blank))

    # 主字体（默认字体）
    main_tuv = None
    for n in tuvs:
        if n.endswith("small_c.tuv"):
            main_tuv = n
    print("\n主字体 = %s" % main_tuv)
    rects = tuv[main_tuv]

    def slot_of(ch):
        b = ch.encode("gbk", errors="replace")
        if len(b) == 1:
            return 0  # 拉丁：slot = byte-0x20，另行处理
        if len(b) != 2:
            return None
        L = b[0] | (b[1] << 8)
        i = idx.get(L)
        if i is None:
            return "NOTFOUND"
        return 224 + i

    d, order = load_dict(os.path.join(UPD, "DictRead.txt"))

    missing_chars = Counter()          # 字表中查不到
    blank_chars = Counter()            # 查到但贴图空槽
    affected_keys = defaultdict(list)  # key -> [问题字]
    ascii_blank = Counter()

    for k in order:
        v = d[k]
        for ch in v:
            o = ord(ch)
            if o < 0x80:
                # 拉丁：slot = o-0x20
                s = o - 0x20
                if 0 <= s < len(rects):
                    x0, y0, x1, y1 = rects[s]
                    if x1 <= x0 or y1 <= y0:
                        # 空格是正常的零宽；其余算异常
                        if ch not in (" ",):
                            ascii_blank[ch] += 1
                            affected_keys[k].append(ch)
                continue
            s = slot_of(ch)
            if s is None:
                continue
            if s == "NOTFOUND":
                missing_chars[ch] += 1
                affected_keys[k].append(ch)
                continue
            if s >= len(rects):
                missing_chars[ch] += 1
                affected_keys[k].append(ch)
                continue
            x0, y0, x1, y1 = rects[s]
            if x1 <= x0 or y1 <= y0:
                blank_chars[ch] += 1
                affected_keys[k].append(ch)

    print("\n=== 字母表查不到（回退 slot224）===")
    print("  不同字数=%d  总出现=%d" % (len(missing_chars), sum(missing_chars.values())))
    for ch, c in missing_chars.most_common(40):
        print("    %r GBK=%s x%d" % (ch, ch.encode("gbk", errors="replace").hex().upper(), c))

    print("\n=== 查到但贴图空槽（笔画全无 → 字消失）===")
    print("  不同字数=%d  总出现=%d" % (len(blank_chars), sum(blank_chars.values())))
    for ch, c in blank_chars.most_common(60):
        s = slot_of(ch)
        print("    %r GBK=%s slot=%s x%d" % (ch, ch.encode("gbk", errors="replace").hex().upper(), s, c))

    print("\n=== 拉丁空槽(非空格) ===")
    print("  ", ascii_blank.most_common(20))

    print("\n=== 受影响 key 数 = %d ===" % len(affected_keys))
    for k in order:
        if k in affected_keys:
            chars = affected_keys[k]
            uniq = "".join(dict.fromkeys(chars))
            print("  #%-34s 问题字: %s" % (k, uniq))

    # 重点：用户报的那条
    print("\n=== 用户报的 key 明细 ===")
    for k in ("11_D0_MESSAGE_TEXT1", "11_D0_MESSAGE_TEXT2"):
        v = d.get(k, "")
        print("#%s = %r" % (k, v))
        for ch in v:
            o = ord(ch)
            if o < 0x80:
                s = o - 0x20
                tag = "ASCII slot=%d rect=%s" % (s, rects[s] if 0 <= s < len(rects) else "OOR")
            else:
                s = slot_of(ch)
                if s == "NOTFOUND":
                    tag = "!! NOTFOUND -> 回退224"
                elif s >= len(rects):
                    tag = "!! slot=%s 超出贴图范围" % s
                else:
                    tag = "slot=%d rect=%s" % (s, rects[s])
            print("    %s  %s" % (ch, tag))


if __name__ == "__main__":
    main()
