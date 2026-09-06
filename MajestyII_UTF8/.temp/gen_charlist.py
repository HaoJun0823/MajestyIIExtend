# -*- coding: utf-8 -*-
# 重新生成 charlist_data.h:
# 1. 原版 GBK 码序 -> 用 gb18030 解码为 Unicode 码点 (顺序严格一致)
#    (不能用 'gbk'/cp936, 无法解码 GBK 扩展区 AA-FF, 导致从 A2B0 起全部错位)
# 2. 追加旧表补充的缺失汉字 (保持字形索引连续性)
import re

# ---------- 读取原版 GBK charlist ----------
with open(r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\源码\MJ2_fontfix\MJ2_fontfix.cpp',
          'r', encoding='utf-8', errors='replace') as f:
    src = f.read()
m = re.search(r'static const WORD g_charlist_data\[\] = \{(.*?)\};', src, re.S)
gbk_codes = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{4})', m.group(1))]
while gbk_codes and gbk_codes[-1] == 0:
    gbk_codes.pop()

print('原版 GBK 条目:', len(gbk_codes))

# ---------- 用 gb18030 解码 (GBK 超集, 全部码位可解) ----------
def gbk2uni(code):
    try:
        return ord(bytes([code >> 8, code & 0xFF]).decode('gb18030'))
    except Exception:
        return None

uni_base = []
fail = 0
for c in gbk_codes:
    u = gbk2uni(c)
    if u is None:
        fail += 1
        print('!! 无法解码 GBK %04X' % c)
        continue
    uni_base.append(u)
print('gb18030 解码失败:', fail, '条, 成功:', len(uni_base))

# ---------- 读取旧表补充部分 (索引 6995 之后) ----------
with open(r'G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h',
          'r', encoding='utf-8') as f:
    src2 = f.read()
m2 = re.search(r'static const unsigned short g_charlist\[\] = \{(.*?)\};', src2, re.S)
old_uni = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{4})', m2.group(1))]
while old_uni and old_uni[-1] == 0:
    old_uni.pop()
old_extra = old_uni[len(gbk_codes):] if len(old_uni) > len(gbk_codes) else []
print('旧表补充部分条目数:', len(old_extra))
print('旧表补充前10:', ['%04X' % x for x in old_extra[:10]])

# ---------- 合并: 基础表 + 旧补充中未覆盖的 ----------
existing = set(uni_base)
extra = [u for u in old_extra if u not in existing]
print('旧补充中未覆盖的:', len(extra), '条')
final_uni = uni_base + extra
print('合并后条目:', len(final_uni))

# 去重兜底（保持顺序）
seen = set()
dedup = []
for u in final_uni:
    if u not in seen:
        seen.add(u)
        dedup.append(u)
final_uni = dedup
print('去重后条目:', len(final_uni))

# ---------- 输出 ----------
out_path = r'G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('// Auto-generated charlist data - DO NOT EDIT\n')
    f.write('// Total entries: %d (excluding 0x0000 terminator)\n' % len(final_uni))
    f.write('// Each entry is a Unicode codepoint (was GBK combo in original)\n')
    f.write('// Glyph index = array_position + 0x100\n\n')
    f.write('static const unsigned short g_charlist[] = {\n')
    for i in range(0, len(final_uni), 12):
        chunk = final_uni[i:i+12]
        f.write('    ' + ', '.join('0x%04X' % u for u in chunk) + ',\n')
    f.write('    ,0x0000  // terminator\n')
    f.write('};\n\n')
    f.write('static const int g_charlist_count = %d;\n' % len(final_uni))

print('已写入:', out_path)

# ---------- 验证 ----------
with open(out_path, 'r', encoding='utf-8') as f:
    src3 = f.read()
m3 = re.search(r'static const unsigned short g_charlist\[\] = \{(.*?)\};', src3, re.S)
new_uni = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{4})', m3.group(1))]
while new_uni and new_uni[-1] == 0:
    new_uni.pop()

print()
print('=== 验证: 前 %d 条应与原版 GBK->gb18030 完全一致 ===' % len(gbk_codes))
mismatch = 0
for i in range(min(len(gbk_codes), len(new_uni))):
    u = gbk2uni(gbk_codes[i])
    if u != new_uni[i]:
        mismatch += 1
        if mismatch <= 10:
            print('位置 %d: GBK=%04X 正确=%04X 我们=%04X' % (i, gbk_codes[i], u, new_uni[i]))
print('前 %d 条不匹配: %d' % (min(len(gbk_codes), len(new_uni)), mismatch))
print('总条目:', len(new_uni))
print('头8条:', ['%04X' % x for x in new_uni[:8]])
print('  (期望: 3002 201C 201D 3014 3015 3008 3009 300A)')
print('尾8条:', ['%04X' % x for x in new_uni[-8:]])