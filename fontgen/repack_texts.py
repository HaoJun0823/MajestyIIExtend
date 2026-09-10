# -*- coding: utf-8 -*-
"""
repack_texts.py — 把 fontgen 新烘的字库打进游戏的 texts.zip
================================================================================
用途：字体重新烘焙后（out_fromscratch/ 有新 TUV+DDS），用本脚本替换进
      `update/localization/texts/texts.zip`（也可指定 update_cht 等其它目录的 zip）。

★★★ 为什么本脚本必须内建 slot0 步进压缩（历史坑）★★★
--------------------------------------------------------------------------------
字典补空格（fix_space_wrap.py 第 1 步）之后，每个汉字后面都有一个 ASCII 空格。
Majesty2 引擎「每字符步进 = 下一槽的 x0 − 本槽的 x0」，所以**空格槽 slot0 的
步进直接决定空格占多宽**。字库烘焙出来的 slot0 步进是 7~13px（正常空格宽），
打进去之后界面会变成「学 习 治 理」这样的大间距。

修复方式：令 slot0.x0 = slot1.x0 − SPACE_ADVANCE（默认 2px），矩形同时收成
零宽（x2 = x0）。**矩形宽不影响绘制**（空格本来就没有墨迹；引擎的字符宽度来自
文本对象虚函数，不是 TUV），所以零宽是安全的 —— 已实机验证「效果极好」。

⚠️ 历史事故：2026-09-10 13:16 跑过一次 fix_space_wrap.py 修好了 zip，13:18
   又跑了一次早期的 repack_texts.py（当时不含本逻辑），把 slot0 步进改回 8px，
   修复被静默冲掉。⇒ 因此本逻辑必须内建在此脚本里，不能只放在事后补丁里。

用法：
    python repack_texts.py                        # 默认 update/localization/texts
    python repack_texts.py <zip> <atlas_dir>
    python repack_texts.py --space-advance 0      # 空格完全零宽（极端紧凑）
================================================================================
"""
import os, sys, shutil, zipfile, time, glob, argparse

R = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection"
DEFAULT_ZIP = os.path.join(R, "update", "localization", "texts", "texts.zip")
DEFAULT_ATLAS = r"G:\Projects\MajestyIIExtend\fontgen\out_fromscratch"
TS = time.strftime("%y%m%d_%H%M")
SPACE_ADVANCE = 2      # 空格槽目标步进(px)


def compress_slot0(tuv_bytes, space_advance=SPACE_ADVANCE):
    """把 TUV 里 slot0（第一个纯数字坐标行）的 x0 前移到 slot1.x0 − space_advance，
    矩形收成零宽。返回 (新字节, 旧步进, 新步进, 新行文本)。

    TUV 结构：TUVTXT / TUVCOUNT n / TUVBASE w h / 之后每行 <x1 y1 x2 y2>。
    第 0 行坐标 = 空格（引擎里空格是独立槽，不在 charlist 里）。
    """
    txt = tuv_bytes.decode("utf-8")
    trail = txt.endswith("\n")
    ls = txt.split("\n")
    idx0 = None
    for i, l in enumerate(ls):
        p = l.split()
        if len(p) == 4 and p[0].lstrip("-").isdigit():
            idx0 = i
            break
    if idx0 is None or idx0 + 1 >= len(ls):
        raise ValueError("TUV 里找不到 slot0/slot1 数字行")

    p0 = ls[idx0].split()
    p1 = ls[idx0 + 1].split()
    y0, y1 = int(p0[1]), int(p0[3])
    s1x = int(p1[0])
    old_adv = s1x - int(p0[0])
    new_x = s1x - space_advance
    sep = "\t" if "\t" in ls[idx0] else " "
    ls[idx0] = sep.join(str(v) for v in (new_x, y0, new_x, y1))
    new = "\n".join(ls)
    if trail and not new.endswith("\n"):
        new += "\n"
    return new.encode("utf-8"), old_adv, space_advance, ls[idx0]


def main():
    ap = argparse.ArgumentParser(description="把新烘字库打进 texts.zip（含 slot0 步进压缩）")
    ap.add_argument("zip", nargs="?", default=DEFAULT_ZIP, help="目标 texts.zip")
    ap.add_argument("atlas", nargs="?", default=DEFAULT_ATLAS, help="字库产物目录")
    ap.add_argument("--space-advance", type=int, default=SPACE_ADVANCE,
                    help="空格槽目标步进 px（默认 2；0=完全零宽）")
    ap.add_argument("--no-compress", action="store_true",
                    help="不压缩 slot0（仅当你要保持字库原样时才用）")
    args = ap.parse_args()
    ZIP, ATLAS = args.zip, args.atlas

    if not os.path.isfile(ZIP):
        print("✗ 找不到目标 zip：%s" % ZIP)
        return 1
    if not os.path.isdir(ATLAS):
        print("✗ 找不到字库目录：%s" % ATLAS)
        return 1

    # ---------- 收集本地产物 ----------
    local = {}
    for p in glob.glob(os.path.join(ATLAS, "**", "*.*"), recursive=True):
        ext = os.path.splitext(p)[1].lower()
        if ext in (".tuv", ".dds"):
            local[os.path.basename(p)] = p
    n_tuv = sum(1 for k in local if k.lower().endswith(".tuv"))
    n_dds = sum(1 for k in local if k.lower().endswith(".dds"))
    print("本地产物: %d 个 (tuv=%d, dds=%d)" % (len(local), n_tuv, n_dds))

    zf = zipfile.ZipFile(ZIP)
    names = zf.namelist()
    infos = {i.filename: i for i in zf.infolist()}
    blobs = {n: zf.read(n) for n in names}
    zf.close()

    # ---------- 同名替换 ----------
    replaced, missing, space_fixed = [], [], []
    for n in names:
        base = os.path.basename(n)
        if not (base.lower().endswith((".tuv", ".dds")) and base in local):
            continue
        nb = open(local[base], "rb").read()
        # ★ TUV：写入前先压缩 slot0 步进（repack 的核心职责，见文件头说明）
        if base.lower().endswith(".tuv") and not args.no_compress:
            try:
                nb, old_adv, new_adv, line = compress_slot0(nb, args.space_advance)
                space_fixed.append((base, old_adv, new_adv, line))
            except Exception as e:
                print("  ⚠ %s 压缩 slot0 失败：%s（原样写入）" % (base, e))
        if nb != blobs[n]:
            replaced.append((base, len(blobs[n]), len(nb)))
        blobs[n] = nb

    in_zip = set(os.path.basename(n) for n in names)
    for base in sorted(local):
        if base not in in_zip:
            missing.append(base)

    print("替换 %d 个条目:" % len(replaced))
    for b, o, nw in replaced:
        print("   %-24s %9d -> %9d" % (b, o, nw))

    if space_fixed and not args.no_compress:
        print("slot0 步进 -> %dpx（共 %d 个 TUV）:" % (args.space_advance, len(space_fixed)))
        for b, o, nw, line in space_fixed:
            print("   %-24s %2d -> %d px   rect=%s" % (b, o, nw, line.replace("\t", " ")))

    if missing:
        print("⚠️ 本地有但 zip 内无同名条目（未加入）: %s" % missing)

    # ---------- 重打包（先写 .tmp，被占用时提示关游戏）----------
    bak = ZIP + ".bak_before_repack_" + TS
    shutil.copy2(ZIP, bak)
    tmp = ZIP + ".tmp"
    zo = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
    for n in names:
        zi = infos[n]
        zi2 = zipfile.ZipInfo(n, zi.date_time)
        zi2.compress_type = zi.compress_type
        zi2.external_attr = zi.external_attr
        zo.writestr(zi2, blobs[n])
    zo.close()
    try:
        os.replace(tmp, ZIP)
        print("重打包完成: %s (%d entries, %d bytes)" % (ZIP, len(names), os.path.getsize(ZIP)))
    except PermissionError:
        print("⚠️ 目标被占用（游戏在运行？）。已生成：%s (%d bytes)" % (tmp, os.path.getsize(tmp)))
        print("   请关闭游戏后执行： mv \"%s\" \"%s\"" % (tmp, ZIP))
    print("备份: %s" % bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
