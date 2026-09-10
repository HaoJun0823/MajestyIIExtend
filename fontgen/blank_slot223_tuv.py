#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 Majesty2 中文字库 TUV 的 slot 223（字符 0xFF = ÿ）强制写成 0 0 0 0。

背景：
  引擎在绘制每个中文（2 字节 GBK）字符前，会先画一个 0xFF 前置标记/占位。
  若该槽是真实字形，每个中文前会露出一个可见的 ÿ。原版中文字库正是把
  slot 223 留空成 0 0 0 0 来隐藏它（全文唯一的 0 0 0 0 就在此处）。
  从零/追加生成时若没做这一步，就会出现"中文前带 ÿ"的现象。

适用：本工具只针对"slot 有序、slot 0 = 0x20 起"的 TUV（即本项目的 scratch/append 产物）。
  slot 223 = 第 224 条数据行（TUVBASE 行之后第 224 行）。

用法：
  python blank_slot223_tuv.py <a.tuv> [b.tuv ...]
  python blank_slot223_tuv.py --dir <文件夹>      # 处理文件夹内所有 .tuv
"""
import sys, os, glob

ZERO_LINE = "0\t0\t0\t0"


def patch_tuv(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        data = f.read()
    lines = data.splitlines(keepends=True)
    # 解析 TUVCOUNT，纯拉丁字库(<=224)的 0xFF 是真实字符，不能留空，跳过
    tuvcount = 0
    for ln in lines:
        s = ln.strip()
        if s.upper().startswith("TUVCOUNT"):
            try:
                tuvcount = int(s.split()[1])
            except Exception:
                pass
            break
    if tuvcount and tuvcount <= 224:
        print(f"  · 纯拉丁字库(TUVCOUNT={tuvcount})，保留 0xFF，跳过：{path}")
        return False
    base_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().upper().startswith("TUVBASE"):
            base_idx = i
            break
    if base_idx is None:
        print(f"  ✗ 跳过（无 TUVBASE 头）：{path}")
        return False
    target = base_idx + 1 + 223          # 数据行下标 223 = slot 223
    if target >= len(lines):
        print(f"  ✗ 跳过（数据行不足 224，slot 223 不存在）：{path}")
        return False
    old = lines[target].rstrip("\r\n")
    if old == ZERO_LINE:
        print(f"  · 已是 0 0 0 0，无需修改：{path}")
        return False
    ending = "\r\n" if lines[target].endswith("\r\n") else ("\n" if lines[target].endswith("\n") else "")
    lines[target] = ZERO_LINE + ending
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(lines))
    print(f"  ✅ slot 223 -> 0 0 0 0（原：{old!r}）：{path}")
    return True


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--dir":
        folder = args[1] if len(args) > 1 else "."
        files = sorted(glob.glob(os.path.join(folder, "*.tuv")))
        if not files:
            print(f"  ✗ 文件夹内无 .tuv：{folder}")
            return
        for p in files:
            patch_tuv(p)
    else:
        for p in args:
            patch_tuv(p)


if __name__ == "__main__":
    main()
