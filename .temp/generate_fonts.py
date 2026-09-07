#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量字体图集生成器（非交互式）
基于 png字体+png补丁.py 的核心逻辑，自动生成8种字体到 New_Fonts_CHS 目录。

字符排列：CP1252基础字符(0x20-0xFF, 224个) + charlist.txt中的中文字符
输出：每种字体生成 .png + .dds + .tuv
"""

import os
import sys
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ===================== 路径配置 =====================
SCRIPT_DIR = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\字体生成"
FONT_PATH = os.path.join(SCRIPT_DIR, "SourceHanSansHWSC-VF.ttf")
CHARLIST_PATH = os.path.join(SCRIPT_DIR, "charlist.txt")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "New_Fonts_CHS")
TEXCONV_PATH = os.path.join(SCRIPT_DIR, "texconv.exe")

# ===================== 字体配置 =====================
# (输出前缀, 字号, 图集宽度, 图集高度)
# 原版分析：
#   font12: 2048x1024, CJK=12x12
#   font14: 2048x1024, CJK=14x14
#   font18: 2048x2048, CJK=18x18
#   console: 2048x1024, CJK=16x16
#   small: 2048x1024, CJK=16x16
#   big_caption: 2048x2048, CJK=24x24
#   med_caption: 2048x2048, CJK=19x19
#   paragraph: 2048x2048, CJK=20x20
FONT_CONFIGS = [
    ("font12",       12, 2048, 1024),
    ("font14",       14, 2048, 1024),
    ("font18",       18, 2048, 2048),
    ("console",      16, 2048, 1024),
    ("small",        16, 2048, 1024),
    ("big_caption",  24, 2048, 2048),
    ("med_caption",  19, 2048, 2048),
    ("paragraph",    20, 2048, 2048),
]

# ===================== 渲染参数 =====================
RENDER_MODE = "smooth"
SHARPNESS = 1.5
BOLD = False
SUPERSAMPLE = 2
ZERO_SPACE_WIDTH = True
PADDING_TOP = 0
PADDING_BOTTOM = 0
PADDING_LEFT = 0
PADDING_RIGHT = 0
GLYPH_PADDING = 1  # 字符间距

# ===================== 核心函数（从原脚本移植） =====================

def load_auto_font(font_path, pixel_size):
    return ImageFont.truetype(font_path, pixel_size)


def render_glyph(char, font_path, font_size, render_mode="smooth",
                 threshold=128, sharpness=1.5, bold=False,
                 padding_top=0, padding_bottom=0, padding_left=0, padding_right=0,
                 supersample=1):
    base_box_w = font_size + padding_left + padding_right
    base_box_h = font_size + padding_top + padding_bottom

    factor = supersample if (render_mode == "smooth" and supersample > 1) else 1

    render_w = base_box_w * factor
    render_h = base_box_h * factor
    render_font_size = font_size * factor

    canvas = Image.new("L", (render_w, render_h), 0)
    draw = ImageDraw.Draw(canvas)
    font = load_auto_font(font_path, render_font_size)

    bbox = draw.textbbox((0, 0), char, font=font)
    char_w = bbox[2] - bbox[0]
    char_h = bbox[3] - bbox[1]

    x_offset = (padding_left * factor) + (render_w - (padding_left + padding_right) * factor - char_w) // 2 - bbox[0]
    y_offset = render_h - bbox[3] - (padding_bottom * factor)

    if bold and render_mode == "smooth":
        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for dx, dy in offsets:
            draw.text((x_offset + dx, y_offset + dy), char, font=font, fill=128)
        draw.text((x_offset, y_offset), char, font=font, fill=255)
    else:
        draw.text((x_offset, y_offset), char, font=font, fill=255)

    if render_mode == "smooth":
        if sharpness != 1.0:
            def enhance_contrast(p):
                if p < 128:
                    return max(0, int(p * (1 - (1 - sharpness) * 0.5)))
                else:
                    return min(255, int(128 + (p - 128) * sharpness))
            canvas = canvas.point(enhance_contrast)
        if sharpness > 1.2:
            canvas = canvas.filter(ImageFilter.SHARPEN)
    elif render_mode == "binary":
        canvas = canvas.point(lambda p: 255 if p > threshold else 0)

    if factor > 1:
        canvas = canvas.resize((base_box_w, base_box_h), Image.Resampling.LANCZOS)

    return canvas, base_box_w, base_box_h


def pack_atlas(glyph_list, atlas_width=2048, padding=1, max_height=2048):
    coord_list = []
    current_height = 512
    atlas_canvas = Image.new("L", (atlas_width, current_height), 0)
    cur_x, cur_y, row_max_h = 0, 0, 0

    for _, glyph, w, h in glyph_list:
        if glyph is None:
            coord_list.append((0, 0, 0, 0))
            continue

        if cur_x + w > atlas_width:
            cur_x = 0
            cur_y += row_max_h + padding
            row_max_h = 0
            if cur_y + h > atlas_canvas.height:
                new_height = min(((cur_y + h + 511) // 512) * 512, max_height)
                if new_height <= atlas_canvas.height:
                    # 超出最大高度，强制截断
                    coord_list.append((0, 0, 0, 0))
                    continue
                new_canvas = Image.new("L", (atlas_width, new_height), 0)
                new_canvas.paste(atlas_canvas, (0, 0))
                atlas_canvas = new_canvas
                print(f"  图集高度扩展到：{new_height} px")

        box = (cur_x, cur_y, cur_x + w, cur_y + h)
        atlas_canvas.paste(glyph, box)
        coord_list.append((cur_x, cur_y, cur_x + w, cur_y + h))
        cur_x += w + padding
        row_max_h = max(row_max_h, h)

    final_height = cur_y + row_max_h
    actual_height = max(atlas_canvas.height, ((final_height + 511) // 512) * 512)
    actual_height = min(actual_height, max_height)

    if actual_height < atlas_canvas.height:
        atlas_canvas = atlas_canvas.crop((0, 0, atlas_width, actual_height))
    elif actual_height > atlas_canvas.height:
        new_canvas = Image.new("L", (atlas_width, actual_height), 0)
        new_canvas.paste(atlas_canvas, (0, 0))
        atlas_canvas = new_canvas

    return atlas_canvas, coord_list, actual_height


def write_tuv(file_path, char_list, tex_w, tex_h, coords, zero_space_width=False):
    space_chars = {' ', '\u3000', '\t', '\n', '\r'}
    ZERO_INDEX = 223  # ASCII 0xFF

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("TUVTXT\n")
        f.write(f"TUVCOUNT {len(char_list)}\n")
        f.write(f"TUVBASE {tex_w} {tex_h}\n")

        for idx, (x1, y1, x2, y2) in enumerate(coords):
            if idx == ZERO_INDEX:
                f.write("0\t0\t0\t0\n")
                continue

            if zero_space_width and idx < len(char_list):
                char = char_list[idx]
                if char in space_chars:
                    f.write(f"{x1}\t{y1}\t{x1}\t{y2}\n")
                else:
                    f.write(f"{x1}\t{y1}\t{x2}\t{y2}\n")
            else:
                f.write(f"{x1}\t{y1}\t{x2}\t{y2}\n")


def convert_png_to_dds(png_path, texconv_path, output_dir):
    cmd = [texconv_path, png_path, "-f", "DXT5", "-m", "1", "-y", "-o", output_dir]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                               encoding='gbk', errors='ignore', timeout=120)
        if result.returncode == 0:
            print(f"  DDS 转换成功")
            return True
        else:
            print(f"  DDS 转换失败 (返回码 {result.returncode})")
            if result.stderr:
                print(f"  错误: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"  DDS 转换异常: {e}")
        return False


def build_char_list(charlist_path):
    """组装字符序列：CP1252基础字符 + charlist中文字符"""
    all_char = []
    for code in range(0x20, 0x100):
        try:
            ch = bytes([code]).decode("cp1252")
        except:
            ch = "\ufffd"
        all_char.append(ch)

    with open(charlist_path, "r", encoding="gbk") as f:
        cn_raw = f.read()
    cn_chars = [c for c in cn_raw if c not in ("\n", "\r", "\t", "\x0c", "\x00")]
    all_char.extend(cn_chars)

    return all_char, len(all_char) - len(cn_chars), len(cn_chars)


def generate_one_font(prefix, font_size, atlas_w, atlas_h, char_list, ascii_count, cn_count):
    """生成一种字体的 .png + .dds + .tuv"""
    print(f"\n{'='*60}")
    print(f"生成 {prefix} (字号={font_size}px, 图集={atlas_w}x{atlas_h})")
    print(f"  字符总数: {len(char_list)} (ASCII={ascii_count}, CJK={cn_count})")
    print(f"{'='*60}")

    # 1. 渲染所有字符
    print("  [1/4] 渲染字符纹理...")
    glyph_cache = []
    total = len(char_list)
    for idx, ch in enumerate(char_list):
        glyph, w, h = render_glyph(
            ch, FONT_PATH, font_size, RENDER_MODE,
            128, SHARPNESS, BOLD,
            PADDING_TOP, PADDING_BOTTOM, PADDING_LEFT, PADDING_RIGHT,
            SUPERSAMPLE
        )
        if glyph is None:
            box_w = font_size + PADDING_LEFT + PADDING_RIGHT
            box_h = font_size + PADDING_TOP + PADDING_BOTTOM
            glyph = Image.new("L", (box_w, box_h), 0)
            w, h = box_w, box_h
        glyph_cache.append((ch, glyph, w, h))
        if (idx + 1) % 1000 == 0 or idx == total - 1:
            print(f"    渲染进度: {idx+1}/{total} ({int((idx+1)/total*100)}%)")

    # 2. 打包图集
    print("  [2/4] 打包纹理图集...")
    atlas_img, uv_coords, actual_h = pack_atlas(glyph_cache, atlas_w, GLYPH_PADDING, atlas_h)
    print(f"    图集尺寸: {atlas_img.width}x{atlas_img.height}")

    # 3. 转RGBA并保存PNG
    print("  [3/4] 保存PNG...")
    if atlas_img.mode != 'RGBA':
        rgba = Image.new("RGBA", atlas_img.size, (0, 0, 0, 0))
        rgba.putalpha(atlas_img)
        white = Image.new("RGB", atlas_img.size, (255, 255, 255))
        rgba.paste(white, (0, 0), atlas_img)
        atlas_img = rgba

    png_path = os.path.join(OUTPUT_DIR, f"{prefix}.png")
    atlas_img.save(png_path, format="PNG")
    print(f"    PNG: {png_path}")

    # 4. 转DDS
    print("  [4/4] 转换DDS...")
    if os.path.exists(TEXCONV_PATH):
        convert_png_to_dds(png_path, TEXCONV_PATH, OUTPUT_DIR)
        # 重命名DDS（texconv可能输出不同名）
        dds_expected = os.path.join(OUTPUT_DIR, f"{prefix}.dds")
        dds_texconv = os.path.join(OUTPUT_DIR, os.path.splitext(os.path.basename(png_path))[0] + ".dds")
        if dds_texconv != dds_expected and os.path.exists(dds_texconv):
            os.rename(dds_texconv, dds_expected)
    else:
        print("    texconv.exe 未找到，跳过DDS转换")

    # 5. 写TUV
    tuv_path = os.path.join(OUTPUT_DIR, f"{prefix}.tuv")
    write_tuv(tuv_path, char_list, atlas_img.width, atlas_img.height,
              uv_coords, ZERO_SPACE_WIDTH)
    print(f"    TUV: {tuv_path}")

    return atlas_img.width, atlas_img.height


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("="*60)
    print(" 批量字体图集生成器")
    print(f" 字体: {os.path.basename(FONT_PATH)}")
    print(f" 输出: {OUTPUT_DIR}")
    print(f" 渲染: smooth, sharpness={SHARPNESS}, supersample={SUPERSAMPLE}x")
    print("="*60)

    # 组装字符序列
    char_list, ascii_count, cn_count = build_char_list(CHARLIST_PATH)
    print(f"字符总数: {len(char_list)} (ASCII={ascii_count}, CJK={cn_count})")

    # 逐个生成
    results = []
    for prefix, font_size, atlas_w, atlas_h in FONT_CONFIGS:
        w, h = generate_one_font(prefix, font_size, atlas_w, atlas_h,
                                  char_list, ascii_count, cn_count)
        results.append((prefix, w, h, font_size))

    # 汇总
    print(f"\n{'='*60}")
    print("生成完成！汇总：")
    print(f"{'='*60}")
    for prefix, w, h, fs in results:
        print(f"  {prefix:15s}: {w}x{h} (字号={fs}px)")

    # 检查输出文件
    print(f"\n输出目录文件：")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        fpath = os.path.join(OUTPUT_DIR, f)
        print(f"  {f:30s} {os.path.getsize(fpath):>10,} bytes")


if __name__ == "__main__":
    main()
