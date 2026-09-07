#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只生成剩余5种字体（console, small, big_caption, med_caption, paragraph）"""
import os, sys, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SCRIPT_DIR = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\字体生成"
FONT_PATH = os.path.join(SCRIPT_DIR, "SourceHanSansHWSC-VF.ttf")
CHARLIST_PATH = os.path.join(SCRIPT_DIR, "charlist.txt")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "New_Fonts_CHS")
TEXCONV_PATH = os.path.join(SCRIPT_DIR, "texconv.exe")

# 只生成剩下的
FONT_CONFIGS = [
    ("console",      16, 2048, 1024),
    ("small",        16, 2048, 1024),
    ("big_caption",  24, 2048, 2048),
    ("med_caption",  19, 2048, 2048),
    ("paragraph",    20, 2048, 2048),
]

RENDER_MODE = "smooth"
SHARPNESS = 1.5
SUPERSAMPLE = 1  # 降为1x，加速4倍
GLYPH_PADDING = 1

def render_glyph(char, font_path, font_size):
    factor = SUPERSAMPLE if RENDER_MODE == "smooth" else 1
    box_w = font_size
    box_h = font_size
    rw, rh = box_w * factor, box_h * factor
    rfs = font_size * factor
    canvas = Image.new("L", (rw, rh), 0)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(font_path, rfs)
    bbox = draw.textbbox((0, 0), char, font=font)
    cw = bbox[2] - bbox[0]
    ch = bbox[3] - bbox[1]
    x_off = (rw - cw) // 2 - bbox[0]
    y_off = rh - bbox[3]
    draw.text((x_off, y_off), char, font=font, fill=255)
    if SHARPNESS != 1.0:
        canvas = canvas.point(lambda p: max(0, int(p*(1-(1-SHARPNESS)*0.5))) if p < 128 else min(255, int(128+(p-128)*SHARPNESS)))
    if SHARPNESS > 1.2:
        canvas = canvas.filter(ImageFilter.SHARPEN)
    if factor > 1:
        canvas = canvas.resize((box_w, box_h), Image.Resampling.LANCZOS)
    return canvas, box_w, box_h

def pack_atlas(glyph_list, atlas_w, max_h):
    coords = []
    cur_h = 512
    canvas = Image.new("L", (atlas_w, cur_h), 0)
    cx, cy, rh = 0, 0, 0
    for _, g, w, h in glyph_list:
        if g is None:
            coords.append((0,0,0,0)); continue
        if cx + w > atlas_w:
            cx = 0; cy += rh + 1; rh = 0
            if cy + h > canvas.height:
                nh = min(((cy+h+511)//512)*512, max_h)
                if nh <= canvas.height:
                    coords.append((0,0,0,0)); continue
                nc = Image.new("L", (atlas_w, nh), 0)
                nc.paste(canvas, (0,0)); canvas = nc
        canvas.paste(g, (cx, cy, cx+w, cy+h))
        coords.append((cx, cy, cx+w, cy+h))
        cx += w + 1; rh = max(rh, h)
    fh = cy + rh
    ah = max(canvas.height, ((fh+511)//512)*512)
    ah = min(ah, max_h)
    if ah < canvas.height:
        canvas = canvas.crop((0,0,atlas_w,ah))
    elif ah > canvas.height:
        nc = Image.new("L", (atlas_w, ah), 0); nc.paste(canvas,(0,0)); canvas = nc
    return canvas, coords, ah

def write_tuv(path, chars, tw, th, coords):
    with open(path, "w", encoding="utf-8") as f:
        f.write("TUVTXT\n"); f.write(f"TUVCOUNT {len(chars)}\n"); f.write(f"TUVBASE {tw} {th}\n")
        for i, (x1,y1,x2,y2) in enumerate(coords):
            if i == 223: f.write("0\t0\t0\t0\n"); continue
            if i < len(chars) and chars[i] in (' ','\u3000','\t','\n','\r'):
                f.write(f"{x1}\t{y1}\t{x1}\t{y2}\n")
            else:
                f.write(f"{x1}\t{y1}\t{x2}\t{y2}\n")

# 组装字符
all_char = []
for code in range(0x20, 0x100):
    try: ch = bytes([code]).decode("cp1252")
    except: ch = "\ufffd"
    all_char.append(ch)
with open(CHARLIST_PATH, "r", encoding="gbk") as f:
    cn = [c for c in f.read() if c not in ("\n","\r","\t","\x0c","\x00")]
all_char.extend(cn)
print(f"字符总数: {len(all_char)}")

os.makedirs(OUTPUT_DIR, exist_ok=True)

for prefix, fs, aw, ah in FONT_CONFIGS:
    print(f"\n--- {prefix} (size={fs}, atlas={aw}x{ah}) ---")
    # 渲染
    glyphs = []
    for i, ch in enumerate(all_char):
        g, w, h = render_glyph(ch, FONT_PATH, fs)
        glyphs.append((ch, g, w, h))
        if (i+1) % 2000 == 0: print(f"  渲染 {i+1}/{len(all_char)}")
    print(f"  渲染完成")
    # 打包
    atlas, coords, actual_h = pack_atlas(glyphs, aw, ah)
    print(f"  图集: {atlas.width}x{atlas.height}")
    # RGBA
    rgba = Image.new("RGBA", atlas.size, (0,0,0,0))
    rgba.putalpha(atlas)
    white = Image.new("RGB", atlas.size, (255,255,255))
    rgba.paste(white, (0,0), atlas)
    png_path = os.path.join(OUTPUT_DIR, f"{prefix}.png")
    rgba.save(png_path, format="PNG")
    print(f"  PNG: {os.path.getsize(png_path):,} bytes")
    # DDS
    if os.path.exists(TEXCONV_PATH):
        r = subprocess.run([TEXCONV_PATH, png_path, "-f", "DXT5", "-m", "1", "-y", "-o", OUTPUT_DIR],
                          capture_output=True, text=True, encoding='gbk', errors='ignore', timeout=120)
        print(f"  DDS: {'OK' if r.returncode==0 else 'FAIL'}")
    # TUV
    tuv_path = os.path.join(OUTPUT_DIR, f"{prefix}.tuv")
    write_tuv(tuv_path, all_char, atlas.width, atlas.height, coords)
    print(f"  TUV: {os.path.getsize(tuv_path):,} bytes")
    print(f"  {prefix} 完成!")

print("\n全部完成!")
