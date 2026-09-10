#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「完整 GB18030 2字节字符集」字表：
  - 引擎查字逻辑 edx=(al<<8)|cl 只能处理 2 字节 GB18030(GBK) 码，
    因此能真正进字库的最大集合 = 完整 GBK（GB18030 2字节平面）。
  - 保留现有 g_charlist_data 的 6995 项原序（slot 224..7218 不变），
    把剩余 GB18030 2字节字按字节序追加在后（append，不插入）。
  - 产出：
      charlist_full_gb18030.txt  GBK 字节串（供生成器/fonlist 消费）
      charlist_full_unicode.txt   U+xxxx 清单（逐行，便于核对）
      charlist_full_patch_c.txt  追加进 DLL 的 C 数组片段
用法： python gen_full_gb18030.py
"""
import re, os

FONTGEN = r"G:/Projects/MajestyIIExtend/fontgen"
SRC_CPP = r"G:/Projects/MajestyIIExtend/MajestyII_UTF8/dllmain.cpp"

def hx(n): return f"0x{n:04X}"

# ---- 1) 读取现有 g_charlist_data（保留原序）----
src = open(SRC_CPP, encoding="utf-8", errors="ignore").read()
m = re.search(r"g_charlist_data\[\]\s*=\s*\{(.*?)\};", src, re.S)
raw = re.findall(r"0x([0-9A-Fa-f]{4})", m.group(1))
words = [int(h, 16) for h in raw if int(h, 16) != 0]
seen = set(); existing = []
for w in words:
    if w not in seen:
        seen.add(w); existing.append(w)
print(f"[1] 现有 g_charlist_data 去重后: {len(existing)} 项")

# ---- 2) 枚举完整 GB18030 2字节平面（字节序）----
full = []
fullset = set()
for b0 in range(0x81, 0x100):           # 0x81..0xFE 首字节
    for b1 in list(range(0x40, 0x7F)) + list(range(0x80, 0x100)):  # 0x40..0xFE 排除 0x7F 次字节
        # ⚠ 存「小端字」L = 首字节 | (次字节<<8)：引擎按 x86 小端装入字符串两字节得到
        #   的查询键就是 L；原版 6995 项同样是 L。写成 (首字节<<8)|次字节 会导致
        #   繁体整片查不到（乱码）且构建脚本解码失败（贴图空白槽）。见 fix_charlist_endian.py。
        key = b0 | (b1 << 8)
        if key in fullset:
            continue
        try:
            ch = bytes([b0, b1]).decode("gb18030")
        except Exception:
            continue
        if len(ch) != 1:
            continue
        cp = ord(ch)
        if cp < 0x20:        # 跳过控制字符
            continue
        fullset.add(key)
        full.append(key)
print(f"[2] 完整 GB18030 2字节字符: {len(full)} 个")

# ---- 3) canonical = 原序 + 剩余(字节序) ----
existing_set = set(existing)
new = [w for w in full if w not in existing_set]
canonical = existing + new
missing_existing = [w for w in existing if w not in fullset]
print(f"[3] 追加新增: {len(new)} 个 | canonical 总 CJK: {len(canonical)}")
print(f"    现有项不在 GB18030 2字节平面内(应为0): {len(missing_existing)}")
total_slots = 224 + len(canonical)
print(f"    总槽数(拉丁224 + CJK{len(canonical)}) = {total_slots}")

def dec(w):
    # w 是小端字 L = 首字节 | (次字节<<8) → 内存字节顺序为 (首字节, 次字节)
    return bytes([w & 0xFF, (w >> 8) & 0xFF]).decode("gb18030")

chars = [dec(w) for w in canonical]

# 采样核对
print("    前8字:", "".join(chars[:8]))
print("    末8字:", "".join(chars[-8:]))

# ---- 4) 输出 ----
gbk_path = os.path.join(FONTGEN, "charlist_full_gb18030.txt")
with open(gbk_path, "wb") as f:
    for w in canonical:
        f.write(bytes([(w >> 8) & 0xFF, w & 0xFF]))
print(f"[4a] 写出 {gbk_path}  (字节数={os.path.getsize(gbk_path)}, 即 {len(canonical)} 字)")

uni_path = os.path.join(FONTGEN, "charlist_full_unicode.txt")
with open(uni_path, "w", encoding="utf-8") as f:
    for w, ch in zip(canonical, chars):
        f.write(f"U+{ord(ch):04X}\t{ch}\n")
print(f"[4b] 写出 {uni_path}")

patch_path = os.path.join(FONTGEN, "charlist_full_patch_c.txt")
with open(patch_path, "w", encoding="utf-8") as f:
    f.write(f"// ===== 追加到 g_charlist_data[] 末尾（新增 {len(new)} 项 GB18030 2字节，保留原6995序）=====\n  "
            + ",\n  ".join(hx(w) for w in new) + ",\n\n")
    f.write(f"// ===== 追加到 charlist[] 末尾（同序 Unicode）=====\n  "
            + ",\n  ".join(hx(ord(ch)) for ch in chars[len(existing):]) + ",\n")
print(f"[4c] 写出 {patch_path}")

# 统计中文汉字数（CJK 基本+扩展A）
n_han = sum(1 for ch in chars if 0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF)
n_pua = sum(1 for ch in chars if 0xE000 <= ord(ch) <= 0xF8FF)
print(f"    汉字(CJK基本+扩展A): {n_han} | PUA私用区(图标槽): {n_pua}")
print("✅ 完成")
