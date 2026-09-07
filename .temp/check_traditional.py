#!/usr/bin/env python3
"""验证繁体字是否在 GBK charlist 中"""
import re

with open(r'G:\Projects\MajestyIIExtend\.temp\merged\MajestyII_merged.cpp', 'r', encoding='utf-8') as f:
    content = f.read()

m = re.search(r'g_charlist_data\[\]\s*=\s*\{([^}]+)\}', content, re.DOTALL)
vals = [int(v, 16) for v in re.findall(r'0x([0-9A-Fa-f]+)', m.group(1))]
charlist_set = set(vals)

test_chars = '擊殺賺金幣敵方英雄建築經過天數消怪物'
for ch in test_chars:
    gbk_bytes = ch.encode('gbk')
    lead = gbk_bytes[0]
    trail = gbk_bytes[1]
    combo = (lead << 8) | trail
    found = combo in charlist_set
    status = "FOUND" if found else "NOT FOUND"
    print(f"{ch} -> GBK {gbk_bytes.hex()} -> combo 0x{combo:04X} -> {status}")

# 统计：繁体常用字在 charlist 中的覆盖率
# 用一些常见繁体字测试
trad_chars = '擊殺賺金幣敵方英雄建築經過天數消怪物摧毀您的是對經過時間經過天敵方建造資源人口食物木材石頭鐵礦金錢收入支出建設升級訓練生產招募僱傭研究魔法技能天賦屬性防禦攻擊速度移動範圍視野生命值法力值經驗值等級'
in_list = 0
not_in = 0
not_in_chars = []
for ch in trad_chars:
    try:
        gbk_bytes = ch.encode('gbk')
        combo = (gbk_bytes[0] << 8) | gbk_bytes[1]
        if combo in charlist_set:
            in_list += 1
        else:
            not_in += 1
            not_in_chars.append(ch)
    except:
        not_in += 1
        not_in_chars.append(ch)

print(f"\nCoverage: {in_list}/{in_list+not_in} ({in_list*100//(in_list+not_in)}%)")
if not_in_chars:
    print(f"Not in charlist: {''.join(not_in_chars)}")
