# -*- coding: utf-8 -*-
"""从 MJ2_fontfix.cpp 提取 g_charlist_data，只保留有效GBK编码，生成charlist.txt"""
import re

cpp_path = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\Majesty2-CN\source\MJ2_fontfix\MJ2_fontfix.cpp"
out_path = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\字体生成\charlist.txt"

with open(cpp_path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

m = re.search(r'g_charlist_data\[\]\s*=\s*\{([^}]+)\}', text)
hex_values = re.findall(r'0x([0-9A-Fa-f]{4})', m.group(1))

chars = []
skipped = 0
for hv in hex_values:
    word = int(hv, 16)
    lead = (word >> 8) & 0xFF
    trail = word & 0xFF
    try:
        ch = bytes([lead, trail]).decode("gbk")
        # 跳过空白/控制字符
        if ch in ("\n", "\r", "\t", "\x0c", "\x00", " ", "\u3000"):
            skipped += 1
            continue
        chars.append(ch)
    except:
        skipped += 1

# 去重
seen = set()
unique_chars = []
for ch in chars:
    if ch not in seen:
        seen.add(ch)
        unique_chars.append(ch)

print(f"总WORD: {len(hex_values)} | 有效GBK: {len(chars)} | 去重: {len(unique_chars)} | 跳过: {skipped}")

# 用\n连接写入，最后不加额外换行
content = "\n".join(unique_chars) + "\n"
with open(out_path, "w", encoding="gbk") as f:
    f.write(content)

# 验证：逐行读回
with open(out_path, "r", encoding="gbk") as f:
    lines = f.readlines()
verify_chars = [line.rstrip("\n\r") for line in lines if line.rstrip("\n\r")]
print(f"回读: {len(verify_chars)} 个字符")
if len(verify_chars) == len(unique_chars):
    print("验证通过！")
else:
    # 找出差异
    for i, (a, b) in enumerate(zip(unique_chars, verify_chars)):
        if a != b:
            print(f"  差异在位置{i}: 原始={repr(a)} 回读={repr(b)}")
            break
    print(f"原始={len(unique_chars)} 回读={len(verify_chars)}")
