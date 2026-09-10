#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从同目录 DictRead.txt 提取所有汉字与中文标点符号，写入 charlist.txt（GBK 编码）。

【用途】charlist.txt 是 build_font_atlas.py 的中文字符库（以 GBK 读取），
需保证写入的每个字符都能用 GBK 编码（无法编码的字符会被跳过并列出）。

【提取规则】
1. 汉字（CJK 统一表意文字，含扩展A区，GBK 范围内的）
2. 中文标点：全角标点/符号（「，。！？：；、""''《》〈〉「」『』（）【】
   ——…·～￥ 等）与 CJK 符号区（U+3000~U+303F）
3. 按 DictRead.txt 中首次出现的顺序输出，自动去重
4. 全角空格 U+3000 与制表符等空白符不提取（TUV 生成时会特殊处理空白）

【输出】charlist.txt，单行连续排列，GBK 编码（与现有 charlist.txt 格式一致）

【用法】
    python extract_charlist.py            # 默认读同目录 DictRead.txt
    python extract_charlist.py <输入文件> [输出文件]
"""
import os
import sys
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def is_cjk_ideograph(ch):
    """CJK 统一表意文字（基本区 + 扩展A），即『汉字』"""
    cp = ord(ch)
    return 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF


def is_chinese_punctuation(ch):
    """中文标点/符号：
    - CJK 符号和标点区 U+3000~U+303F（。「」等）
    - 全角形式区 U+FF00~U+FFEF（！？：；，、（）￥ 等，剔除全角空格与全角ASCII字母数字）
    - 通用标点中的中文常用符号：— … ・ ～ 「」『』《》〈〉
    """
    cp = ord(ch)
    if 0x3000 <= cp <= 0x303F:
        if cp == 0x3005:          # 々 汉字重复号，视为符号保留
            return True
        return cp != 0x3000       # 全角空格不要
    if 0xFF01 <= cp <= 0xFF60:    # 全角标点区（不含全角空格0x3000、全角字母数字0xFF01前段实际是标点）
        return True
    if ch in "—–…・～·":
        return True
    if ch in "〈〉《》「」『』【】":
        return True
    return False


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SCRIPT_DIR, "DictRead.txt")
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SCRIPT_DIR, "charlist.txt")

    if not os.path.isfile(in_path):
        print(f"✗ 找不到输入文件：{in_path}")
        sys.exit(1)

    # DictRead.txt 为 GBK 编码（无 BOM，回退 utf-8-sig 兼容 UTF-8 源）
    text = None
    last_err = None
    for enc in ("gbk", "utf-8-sig"):
        try:
            with open(in_path, "r", encoding=enc) as f:
                text = f.read()
            read_enc = enc
            break
        except UnicodeDecodeError as e:
            last_err = e
    if text is None:
        print(f"✗ 无法以 GBK/UTF-8 解码 {in_path}：{last_err}")
        sys.exit(1)

    seen = set()
    chars = []
    skipped = {}       # 无法用 GBK 编码的字符 -> 首次出现行号
    line_of = {}       # 字符 -> 首次出现行号（仅用于报告）
    for lineno, line in enumerate(text.splitlines(), 1):
        for ch in line:
            if not (is_cjk_ideograph(ch) or is_chinese_punctuation(ch)):
                continue
            if ch in seen:
                continue
            try:
                ch.encode("gbk")
            except UnicodeEncodeError:
                skipped.setdefault(ch, lineno)
                continue
            seen.add(ch)
            chars.append(ch)
            line_of[ch] = lineno

    # 排序：汉字按 GBK 编码排序，标点按 GBK 编码排序 —— 保持与旧 charlist
    # 『GBK 编码顺序排列』的既有习惯一致（旧文件为 GBK 码点升序）
    chars.sort(key=lambda c: c.encode("gbk"))

    with open(out_path, "wb") as f:
        f.write("".join(chars).encode("gbk"))

    n_cjk = sum(1 for c in chars if is_cjk_ideograph(c))
    n_punct = len(chars) - n_cjk
    print(f"✅ 提取完成：{in_path}（按 {read_enc} 解码）")
    print(f"   汉字 {n_cjk} 个，中文标点 {n_punct} 个，共 {len(chars)} 个 → {out_path}")
    if skipped:
        print(f"   ⚠️ 跳过 {len(skipped)} 个无法用 GBK 编码的字符：")
        for ch, ln in sorted(skipped.items(), key=lambda kv: kv[1]):
            print(f"      U+{ord(ch):04X} {ch!r}（首见于第 {ln} 行）")


if __name__ == "__main__":
    main()
