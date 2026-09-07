# -*- coding: utf-8 -*-
"""分析原版字体的字盒尺寸，推断字号和边距"""
import os

base = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\字体生成\Original_Fonts"
fonts = ["font12", "font14", "font18", "console", "small", "big_caption", "med_caption", "paragraph"]

for fname in fonts:
    tuv_path = os.path.join(base, fname + ".tuv")
    with open(tuv_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # 头部
    count = int(lines[1].split()[1])
    base_parts = lines[2].split()
    tex_w, tex_h = int(base_parts[1]), int(base_parts[2])
    
    # ASCII字符的尺寸（索引1='!'）
    c1 = lines[4].split()
    w1 = float(c1[2]) - float(c1[0])
    h1 = float(c1[3]) - float(c1[1])
    
    # CJK字符的尺寸（索引224起）
    cjk_sizes = []
    for i in range(227, min(240, len(lines))):
        parts = lines[i].split()
        w = float(parts[2]) - float(parts[0])
        h = float(parts[3]) - float(parts[1])
        if w > 0 and h > 0:
            cjk_sizes.append((w, h))
    
    # 统计CJK字符的平均宽高
    if cjk_sizes:
        avg_w = sum(s[0] for s in cjk_sizes) / len(cjk_sizes)
        avg_h = sum(s[1] for s in cjk_sizes) / len(cjk_sizes)
    else:
        avg_w = avg_h = 0
    
    # 看看原版有没有边距（检查第一个字符的x/y偏移）
    c0 = lines[3].split()
    x0, y0 = float(c0[0]), float(c0[1])
    
    # 检查big_caption和med_caption的Y偏移
    print(f"{fname:15s}: Tex={tex_w}x{tex_h} Count={count} | '!'=({w1:.0f}x{h1:.0f}) | CJK_avg=({avg_w:.1f}x{avg_h:.1f}) | first_offset=({x0:.0f},{y0:.0f})")

# 还需要了解原版字体的DDS尺寸
print("\n=== DDS文件大小 ===")
for fname in fonts:
    # 原版有些是单DDS有些是双DDS
    dds_files = []
    for suffix in ["a", "b", ""]:
        dds_path = os.path.join(base, fname + suffix + ".dds")
        if os.path.exists(dds_path):
            dds_files.append((fname + suffix, os.path.getsize(dds_path)))
    print(f"{fname:15s}: {dds_files}")
