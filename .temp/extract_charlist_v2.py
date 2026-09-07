# -*- coding: utf-8 -*-
"""重新生成charlist.txt，保留所有6995个WORD值（排除0x0000终止符）
无效GBK编码用空格占位，保持索引一致"""
import re

cpp_path = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\Majesty2-CN\source\MJ2_fontfix\MJ2_fontfix.cpp"
out_path = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\字体生成\charlist.txt"

with open(cpp_path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

m = re.search(r'g_charlist_data\[\]\s*=\s*\{([^}]+)\}', text)
hex_values = re.findall(r'0x([0-9A-Fa-f]{4})', m.group(1))
print(f"提取到 {len(hex_values)} 个 WORD 值")

# 排除最后一个0x0000终止符
if hex_values[-1].upper() == '0000':
    hex_values = hex_values[:-1]
    print(f"排除终止符0x0000，剩余 {len(hex_values)} 个")

chars = []
valid = 0
invalid = 0
for hv in hex_values:
    word = int(hv, 16)
    lead = (word >> 8) & 0xFF
    trail = word & 0xFF
    try:
        ch = bytes([lead, trail]).decode("gbk")
        # 不去重，保持原序
        # 跳过纯空白控制字符但保留普通空格
        if ch in ("\n", "\r", "\t", "\x0c", "\x00"):
            chars.append(" ")  # 用空格占位
            invalid += 1
        else:
            chars.append(ch)
            valid += 1
    except:
        chars.append(" ")  # 无效GBK用空格占位
        invalid += 1

print(f"有效: {valid} | 占位: {invalid} | 总计: {len(chars)}")
print(f"224 + {len(chars)} = {224 + len(chars)} (应=7219)")

assert len(chars) == 6995, f"条目数不对: {len(chars)}"
assert 224 + len(chars) == 7219

# 写入GBK文件 — 每个字符一行
content = "\n".join(chars) + "\n"
with open(out_path, "w", encoding="gbk") as f:
    f.write(content)

# 验证
with open(out_path, "r", encoding="gbk") as f:
    lines = f.readlines()
verify = [line.rstrip("\n\r") for line in lines if line.rstrip("\n\r") or True]
# 每行一个字符，空格也算
verify_chars = []
for line in lines:
    c = line.rstrip("\n\r")
    if c:
        verify_chars.append(c[0])
    else:
        verify_chars.append(" ")  # 空行当空格

print(f"回读验证: {len(verify_chars)} 个字符")
if len(verify_chars) == len(chars):
    print("验证通过！")
else:
    print(f"不匹配: 原始={len(chars)} 回读={len(verify_chars)}")
