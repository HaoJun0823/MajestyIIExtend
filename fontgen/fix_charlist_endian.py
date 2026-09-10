#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 g_charlist_data[] 的「追加段字节序」错误（繁体乱码根因）。

背景（引擎语义，实测确认）：
  引擎读取字符串里的 GBK 双字节时按 x86 小端装入 → 查询键
      dx = 首字节 | (次字节 << 8)          ← 注意：次字节在高位
  g_charlist_data[] 里存的必须是同一个「小端字」L。
  原版 6995 项 + 用户现有前 6995 段都满足此约定，例如首项
      0xA1A3  ↔ 内存字节 (A3,A1) ↔ GBK 码 0xA3A1 = '！'   ✓

错误：追加的 16945 项由 gen_full_gb18030.py 枚举时写成了「原码」
      key = (首字节<<8)|次字节，与前面 6995 项相反。
  后果：① 构建脚本按小端解码 → 9712 项解码失败 → 贴图空白槽；
        ② 引擎按小端字查找 → 繁体字（次字节 0x40–0x80 那批）查不到 → 乱码。

修复：追加段改为「L 空间补集」——枚举完整 GBK 2 字节平面，取小端字形式，
      剔除前 6995 段已占用的值，按序追加。这样表中数值集合 == 完整 L 空间，
      任何 GBK 可编码字符都能被引擎查到，且贴图 100% 有字形。

产出：
  MajestyII_UTF8/dllmain.cpp        g_charlist_data[]（修复后，23940 项）
  MajestyII_UTF8/charlist_data.h    charlist[] + charlist_count（同序 Unicode）
  fontgen/charlist_full_gb18030.txt / charlist_full_unicode.txt / charlist_full_patch_c.txt
用法： python gen 目录下执行  python fix_charlist_endian.py
"""
import re, os, shutil, sys

ROOT = r"G:/Projects/MajestyIIExtend"
FONTGEN = os.path.join(ROOT, "fontgen")
CPP = os.path.join(ROOT, "MajestyII_UTF8", "dllmain.cpp")
HDR = os.path.join(ROOT, "MajestyII_UTF8", "charlist_data.h")
KEEP = 6995            # 原版序，slot 224..7218 不得改动

hx = lambda n: f"0x{n:04X}"

def dec_le(w):
    """小端字 → 字符：内存字节 (w&0xFF, w>>8)。"""
    try:
        return bytes([w & 0xFF, (w >> 8) & 0xFF]).decode("gbk")
    except Exception:
        return None

# ---------- 1) 读现有表，校验前 6995 段 ----------
src = open(CPP, encoding="utf-8", errors="ignore").read()
m = re.search(r"g_charlist_data\[\]\s*=\s*\{(.*?)\};", src, re.S)
assert m, "找不到 g_charlist_data[]"
vals = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{4})", m.group(1))]
vals = [v for v in vals if v != 0]
print(f"[1] 现有表 {len(vals)} 项；前{KEEP}段首 6: {''.join(dec_le(v) or '?' for v in vals[:6])}")
first = vals[:KEEP]
assert all(dec_le(v) for v in first), "前 6995 段存在无法解码项，与预期不符"
assert len(vals) >= KEEP, "表项少于 6995"

# ---------- 2) 枚举完整 GBK 2 字节平面的「小端字」全集 ----------
LEADS = range(0x81, 0xFF)                      # 0x81..0xFE
SECONDS = [b for b in range(0x40, 0xFF) if b != 0x7F]
LSPACE = []
for b1 in SECONDS:                             # 次字节
    for b0 in LEADS:                           # 首字节
        LSPACE.append(b0 | (b1 << 8))
print(f"[2] 小端字全集(L 空间) {len(LSPACE)} 个（= GBK 2 字节平面容量）")

# ---------- 3) 追加段 = L 空间补集 ----------
have = set(first)
add = [v for v in LSPACE if v not in have]
n_append = len(vals) - KEEP
if len(add) < n_append:
    print(f"    ⚠ 可用补集 {len(add)} < 需要的 {n_append}，将按可用数量输出")
table = first + add[:n_append]
print(f"[3] 追加 {len(table) - KEEP} 项 → 修复后表 {len(table)} 项；"
      f"去重后 {len(set(table))} 项")
assert len(set(table)) == len(table), "修复后仍存在重复值"

ok = sum(1 for v in table if dec_le(v))
print(f"    可解码（有真实字形）: {ok} / {len(table)}；"
      f"其余 {len(table) - ok} 为 PUA/未定义码位（游戏图标槽，按预期留空）")

# ---------- 4) 写回 dllmain.cpp ----------
for f in (CPP, HDR):
    bak = f + ".bak_endianfix"
    if not os.path.exists(bak):
        shutil.copy2(f, bak)
        print(f"[4] 备份 {os.path.basename(f)} -> {os.path.basename(bak)}")

def fmt_block(vals_in, per_line=8, tail0=True):
    out = []
    for i in range(0, len(vals_in), per_line):
        chunk = vals_in[i:i + per_line]
        comma = "," if (i + per_line < len(vals_in)) or tail0 else ""
        out.append("  " + ", ".join(chunk) + comma)
    if tail0:
        out.append("  0x0000")
    return "\n".join(out)

new_cpp = re.sub(r"(g_charlist_data\[\]\s*=\s*\{).*?(\n\};)",
                 lambda mm: mm.group(1) + "\n" + fmt_block([hx(v) for v in table]) + mm.group(2),
                 src, count=1, flags=re.S)
assert new_cpp != src, "g_charlist_data 替换未生效"
open(CPP, "w", encoding="utf-8").write(new_cpp)
print(f"[4] 已写回 dllmain.cpp: g_charlist_data[] = {len(table)} 项 + 0x0000")

# ---------- 5) 写回 charlist_data.h（同序 Unicode 码点）----------
uni = []
for v in table:
    c = dec_le(v)
    uni.append(ord(c) if c else 0xFFFD)
hdr = open(HDR, encoding="utf-8", errors="ignore").read()
mh = re.search(r"charlist\[\]\s*=\s*\{(.*?)\};", hdr, re.S)
if mh:
    hdr2 = re.sub(r"(charlist\[\]\s*=\s*\{).*?(\n\};)",
                  lambda mm: mm.group(1) + "\n" + fmt_block([hx(u) for u in uni]) + mm.group(2),
                  hdr, count=1, flags=re.S)
    hdr2 = re.sub(r"charlist_count\s*=\s*\d+", f"charlist_count = {len(uni)}", hdr2)
    open(HDR, "w", encoding="utf-8").write(hdr2)
    print(f"[5] 已写回 charlist_data.h: charlist[] = {len(uni)} 项")
else:
    print("[5] charlist_data.h 无 charlist[]，跳过")

# ---------- 6) 同步三个 txt 工件（保持与表一致）----------
with open(os.path.join(FONTGEN, "charlist_full_gb18030.txt"), "wb") as f:
    for v in table:
        f.write(bytes([(v >> 8) & 0xFF, v & 0xFF]))   # 供 apply_dll_charlist_patch 还原成同一 L
with open(os.path.join(FONTGEN, "charlist_full_unicode.txt"), "w", encoding="utf-8") as f:
    for v, u in zip(table, uni):
        f.write(f"U+{u:04X}\t{dec_le(v) or ''}\n")
with open(os.path.join(FONTGEN, "charlist_full_patch_c.txt"), "w", encoding="utf-8") as f:
    f.write(f"// ===== 追加到 g_charlist_data[] 末尾（{len(table)-KEEP} 项小端字 L，"
            f"保留原 {KEEP} 序）=====\n  "
            + ",\n  ".join(hx(v) for v in table[KEEP:]) + ",\n\n")
    f.write("// ===== 追加到 charlist[] 末尾（同序 Unicode）=====\n  "
            + ",\n  ".join(hx(u) for u in uni[KEEP:]) + ",\n")
print("[6] 已重写 charlist_full_gb18030.txt / charlist_full_unicode.txt / charlist_full_patch_c.txt")

# ---------- 7) 覆盖率自检 ----------
idx = {}
for k, v in enumerate(table):
    idx.setdefault(v, k)
print("[7] 词典覆盖率自检：")
allok = True
for fp in [r"I:/SteamLibrary/steamapps/common/Majesty 2 Collection/update/DictRead.txt",
           r"I:/SteamLibrary/steamapps/common/Majesty 2 Collection/update/DictRead_V7_CHT.txt"]:
    if not os.path.exists(fp):
        print(f"    (跳过，未找到 {fp})"); continue
    raw = open(fp, "rb").read()
    try: txt = raw.decode("gbk")
    except Exception: txt = raw.decode("gb18030", "replace")
    chars = sorted(set(c for c in txt if ord(c) > 0x2000))
    miss, nongbk = 0, 0
    for c in chars:
        try: b = c.encode("gbk")
        except Exception: nongbk += 1; continue
        if (b[0] | (b[1] << 8)) not in idx:
            miss += 1; allok = False
    print(f"    {os.path.basename(fp)}: 用字 {len(chars)}  GBK不可编码 {nongbk}  "
          f"引擎查不到(会乱码) {miss}")
print("✅ 完成" if allok else "⚠ 仍有缺口，见上")
