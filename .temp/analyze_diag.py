#!/usr/bin/env python3
"""
Analyze the diagnostic data to understand the root cause.
Key questions:
1. Why 43.8% notFound? What codepoints are missing from charlist?
2. Why is state1 flag=1 (waiting for byte 2) at the second sample?
3. Are hook1 and hook2 processing the same text independently?
"""
import struct

# Read charlist_data.h to get all codepoints
charlist = []
with open(r"G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h", "r", encoding="utf-8") as f:
    in_array = False
    for line in f:
        if 'g_charlist[]' in line:
            in_array = True
            continue
        if in_array:
            if '}' in line:
                break
            # Parse hex values
            parts = line.strip().rstrip(',').split(',')
            for p in parts:
                p = p.strip()
                if p.startswith('0x') or p.startswith('0X'):
                    # Strip trailing comments
                    p = p.split('//')[0].strip().rstrip(',')
                    if p.startswith('0x') or p.startswith('0X'):
                        try:
                            val = int(p, 16)
                            charlist.append(val)
                        except ValueError:
                            pass

print(f"Charlist entries: {len(charlist)}")
charlist_set = set(charlist)

# The game is displaying Chinese text like "等待中", "战斗", "巡逻" etc.
# Let's check which codepoints in common Chinese text are missing from charlist
test_strings = [
    "等待中", "战斗", "巡逻", "沿路线行进", "回家", "守卫领地", 
    "行窃", "施咒", "治疗伤员", "寻找冒险", "收集宝藏",
    "漫无目的地游荡", "前去缴税", "购买新装备", "前去休整",
    "逃命", "陷入狂怒", "执行攻击旗令", "执行防御旗令", "执行探索旗令",
    "想要加入队伍", "公会", "分区不可用", "经济建筑", "防御设施",
    "神殿", "返回", "雇佣领主", "按下雇佣领主",
    "哥布林弓手技能", "格鲁姆-戈格斗士技能", "鼠盗技能",
]

print("\n=== Codepoint coverage for game text ===")
missing_all = set()
for s in test_strings:
    missing = []
    for ch in s:
        cp = ord(ch)
        if cp not in charlist_set:
            missing.append(f"U+{cp:04X}({ch})")
            missing_all.add(cp)
    if missing:
        print(f"  '{s}': MISSING {missing}")
    else:
        print(f"  '{s}': all OK")

print(f"\n=== Total unique missing codepoints: {len(missing_all)} ===")
for cp in sorted(missing_all):
    ch = chr(cp)
    print(f"  U+{cp:04X} = '{ch}'")

# Check: the diagnostic showed state2 b1=0xBB at second sample
# 0xBB is NOT a valid UTF-8 lead byte (should be 0xE0-0xEF for 3-byte)
# 0xBB would be a continuation byte (0x80-0xBF) or part of a 2-byte sequence
# This suggests state2 is seeing a DIFFERENT byte stream than state1

print("\n=== Analysis of state2 b1=0xBB ===")
print("0xBB is a UTF-8 continuation byte (0x80-0xBF range)")
print("This is NOT a valid lead byte for 3-byte UTF-8")
print("If state2 has flag=0 and b1=0xBB, it means:")
print("  - The state machine processed 0xBB as a single byte in state 0")
print("  - 0xBB > 0xA0, so it was treated as a lead byte")
print("  - But 0xBB is actually a continuation byte, not a lead byte")
print("  - This means state2 is seeing the SECOND byte of a UTF-8 sequence")
print("  - as the FIRST byte of a new sequence → desynchronized!")

print("\n=== Root Cause Analysis ===")
print("hook1 and hook2 process the SAME text independently (different rendering passes)")
print("hook2 runs MUCH more frequently (4251 vs 519 calls in 3s)")
print("This means hook2 (width cache) iterates through text more often")
print()
print("The problem: hook1 and hook2 maintain SEPARATE state machines")
print("When hook1 sees byte 1 (lead) and sets state=1, then hook2 sees the SAME byte 1")
print("and also sets its state=1. Then hook1 sees byte 2, hook2 sees byte 2, etc.")
print("Both should work correctly IF they see bytes in order.")
print()
print("BUT: state2 b1=0xBB (a continuation byte) suggests desynchronization")
print("This could happen if:")
print("  1. hook2 is called for a DIFFERENT text string between bytes")
print("  2. Some ASCII bytes or markup (<font...>) reset the state machine")
print("  3. The game interleaves text from different sources")
print()
print("The HIGH notFound rate (43.8%) confirms desynchronization:")
print("  When state machine is desynchronized, it combines wrong bytes")
print("  → produces invalid codepoints → not in charlist → notFound")
