# -*- coding: utf-8 -*-
# 生成"仅原版 6995 条"的 charlist（gb18030 解码，顺序与原版完全一致）
# 先用纯原版字符集验证 hook/状态机是否正确，排除字形表越界干扰
import re

with open(r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\源码\MJ2_fontfix\MJ2_fontfix.cpp',
          'r', encoding='utf-8', errors='replace') as f:
    src = f.read()
m = re.search(r'static const WORD g_charlist_data\[\] = \{(.*?)\};', src, re.S)
gbk_codes = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{4})', m.group(1))]
while gbk_codes and gbk_codes[-1] == 0:
    gbk_codes.pop()

def gbk2uni(code):
    try:
        return ord(bytes([code >> 8, code & 0xFF]).decode('gb18030'))
    except Exception:
        return None

uni = []
for c in gbk_codes:
    u = gbk2uni(c)
    if u is None:
        print('!! 无法解码 %04X' % c)
        continue
    uni.append(u)

print('原版条目:', len(gbk_codes), '转换后:', len(uni))

# 去重（gb18030 解码应该无重复，兜底）
seen = set()
dedup = []
for u in uni:
    if u not in seen:
        seen.add(u)
        dedup.append(u)
print('去重后:', len(dedup))

out_path = r'G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('// Auto-generated charlist data - DO NOT EDIT\n')
    f.write('// Total entries: %d (excluding 0x0000 terminator)\n' % len(dedup))
    f.write('// Unicode codepoints, order locked to original GBK order (gb18030 decode)\n')
    f.write('// Glyph index = array_position + 0x100\n\n')
    f.write('static const unsigned short g_charlist[] = {\n')
    n = len(dedup)
    for i in range(0, n, 12):
        chunk = dedup[i:i+12]
        suffix = ',' if i + 12 < n else ''
        f.write('    ' + ', '.join('0x%04X' % u for u in chunk) + suffix + '\n')
    f.write('    ,0x0000  // terminator\n')
    f.write('};\n\n')
    f.write('static const int g_charlist_count = %d;\n' % len(dedup))

print('已写入:', out_path, '总条目:', len(dedup))
print('头8:', ['%04X' % x for x in dedup[:8]])
print('尾8:', ['%04X' % x for x in dedup[-8:]])