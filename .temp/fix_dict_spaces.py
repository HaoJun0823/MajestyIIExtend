#!/usr/bin/env python3
"""
DictRead_V2.txt 去空格脚本
规则：
  - 去掉中文字符（含中文标点）之间的空格
  - 去掉中文字符与相邻中文标点之间的空格
  - 保留英文单词间的空格
  - 保留 HTML 标签内的空格（如 face="..."）
  - 去掉行末中文内容后的尾随空格
  - 输出 UTF-8 无 BOM
"""
import re
import sys

INPUT = r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\DictRead_V2.txt'
OUTPUT = r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\DictRead_V2.txt'

# 读取
data = open(INPUT, 'rb').read()
text = data.decode('gbk')

# 中文字符范围：CJK统一汉字 + 中文标点
# CJK: \u4e00-\u9fff
# 中文标点: \u3000-\u303f（含：、。！？；：""''（）【】《》等）
# 全角符号: \uff00-\uffef（含：！？：；（）等）
CJK_PATTERN = re.compile(
    r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]'
)

lines = text.split('\r\n')
processed_lines = []
stats = {'spaces_removed': 0, 'lines_changed': 0}

for line in lines:
    original = line
    chars = list(line)
    result = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch == ' ':
            # 检查前一个已保留的字符和后一个字符是否都是中文
            prev_is_cjk = len(result) > 0 and bool(CJK_PATTERN.match(result[-1]))
            next_is_cjk = (i + 1) < len(chars) and bool(CJK_PATTERN.match(chars[i + 1]))
            
            if prev_is_cjk or next_is_cjk:
                # 至少一侧是中文，去掉这个空格
                stats['spaces_removed'] += 1
                i += 1
                continue
            else:
                # 两侧都不是中文，保留空格
                result.append(ch)
                i += 1
        else:
            result.append(ch)
            i += 1
    
    new_line = ''.join(result)
    # 去掉行末尾随空格（如果行末是中文字符的话）
    new_line = new_line.rstrip(' ') if new_line and CJK_PATTERN.match(new_line[-1]) else new_line
    # 更一般的尾随空格去除
    new_line = new_line.rstrip()
    
    if new_line != original:
        stats['lines_changed'] += 1
    processed_lines.append(new_line)

output_text = '\r\n'.join(processed_lines)

# 写出 UTF-8 无 BOM
with open(OUTPUT, 'w', encoding='utf-8', newline='') as f:
    f.write(output_text)

print(f'处理完成:')
print(f'  去除空格数: {stats["spaces_removed"]}')
print(f'  修改行数: {stats["lines_changed"]}')
print(f'  总行数: {len(processed_lines)}')
print(f'  原始大小: {len(data)} bytes (GBK)')
print(f'  输出大小: {len(output_text.encode("utf-8"))} bytes (UTF-8)')

# 验证：打印前30行
print('\n--- 前30行验证 ---')
for i, line in enumerate(processed_lines[:30]):
    print(f'{i}: {repr(line)}')
