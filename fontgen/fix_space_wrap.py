# -*- coding: utf-8 -*-
"""修复「长串中文消失」（简体 / 繁体两套字典通用）：
  根因：字典自 V3 起被去掉了「汉字后空格」，而 Majesty2 引擎只在空格处断行
        → 长串变成不可断的整块 → 排版失败 → 文字不显示（闪一下/消失）。
  做法：① 把空格补回字典（标签感知；编码自适应 GBK / UTF-8）
        ② 把 texts.zip 内 16 个字体里 slot0(空格) 的步进从 7~10px 压到 2px
           —— 引擎步进 = 下槽 x0 - 本槽 x0，故令 slot0.x0 = slot1.x0 - 2。
        ③ 重打包 texts.zip（路径被占用时先写 .tmp，提示用户关游戏后 mv）

用法:
    python fix_space_wrap.py                       # 默认简体 update/DictRead.txt
    python fix_space_wrap.py --dict <路径>          # 指定字典（自动探测编码）
    python fix_space_wrap.py --tuv-only            # 只压 TUV 步进 + 重打包（不碰字典）
    python fix_space_wrap.py --dict <路径> --no-tuv # 只补字典空格，不碰 zip
"""
import os, re, shutil, zipfile, time, sys, argparse

R = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection"
UPD = os.path.join(R, "update")
TXT_DIR = os.path.join(UPD, "localization", "texts")
ZIP = os.path.join(TXT_DIR, "texts.zip")

SPACE_ADVANCE = 2      # 空格目标步进(px)；0 = 完全紧凑
CJK = re.compile(r'[\u4e00-\u9fff]')
TS = time.strftime("%y%m%d_%H%M")


def detect_encoding(raw):
    """返回 (编码名, 解码文本)。GBK 优先（能解出即为 GBK 语料），否则 UTF-8。"""
    for enc in ("gbk", "utf-8"):
        try:
            return enc, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("无法识别字典编码（既非 GBK 也非 UTF-8）")


def respace(v):
    """在每个汉字后补一个 ASCII 空格（标签 <...> 内部不动；已有空格则不重复补）。"""
    out = []
    n = len(v)
    in_tag = False
    for i, ch in enumerate(v):
        if ch == '<':
            in_tag = True
        if ch == '>':
            in_tag = False
            out.append(ch)
            continue
        out.append(ch)
        if not in_tag and CJK.match(ch):
            nxt = v[i + 1] if i + 1 < n else ''
            if nxt != ' ':
                out.append(' ')
    return ''.join(out)


def unspace(v):
    """去掉「汉字后紧跟的那个空格」，用于往返校验。"""
    return ''.join(ch for i, ch in enumerate(v)
                   if not (ch == ' ' and i > 0 and CJK.match(v[i - 1])))


def load_pairs(text):
    """键行/值行两行一组解析（与 DLL LoadDict 一致：值只占一行）。"""
    ls = text.replace('\r\n', '\n').split('\n')
    d = {}
    i = 0
    while i < len(ls):
        if ls[i].startswith('#'):
            k = ls[i][1:].strip()
            d[k] = ls[i + 1] if i + 1 < len(ls) else ''
            i += 2
        else:
            i += 1
    return d


def fix_dict(dict_path):
    raw = open(dict_path, "rb").read()
    enc, txt = detect_encoding(raw)
    # 检查行尾风格，原样保留
    crlf = raw.count(b"\r\n")
    lone = raw.count(b"\n") - crlf
    eol = "\r\n" if crlf and not lone else "\n"

    lines = txt.split("\n")
    out = []
    changed = inserted = 0
    for l in lines:
        body = l[:-1] if l.endswith("\r") else l
        if body.startswith('#'):
            out.append(body)
            continue
        new = respace(body)
        if new != body:
            changed += 1
            inserted += new.count(' ') - body.count(' ')
        out.append(new)
    data = eol.join(out).encode(enc)

    old_d = load_pairs(txt)
    new_d = load_pairs(data.decode(enc))
    diff = [k for k in old_d if k not in new_d or unspace(new_d[k]) != old_d[k]]
    print("[1] 字典 %s" % os.path.basename(dict_path))
    print("    编码 %s  行尾 %s  条目 %d -> %d" % (enc, repr(eol), len(old_d), len(new_d)))
    print("    改行 %d  插入空格 %d  往返差异 %d" % (changed, inserted, len(diff)))
    for k in diff[:5]:
        print("     !!", k)
    if diff:
        print("    !! 往返校验失败，已中止写入")
        return

    bak = dict_path + ".bak_before_respace_" + TS
    shutil.copy2(dict_path, bak)
    open(dict_path, "wb").write(data)
    print("    写入 %s (%d bytes)" % (dict_path, len(data)))
    print("    备份 %s" % bak)


def fix_tuv_zip():
    zf = zipfile.ZipFile(ZIP)
    names = zf.namelist()
    infos = {i.filename: i for i in zf.infolist()}
    blobs = {n: zf.read(n) for n in names}
    zf.close()

    edited = []
    for n in names:
        if not n.lower().endswith('.tuv'):
            continue
        raw = blobs[n]
        txt = raw.decode('utf-8')
        trail = txt.endswith('\n')
        ls = txt.split('\n')
        idx0 = None
        for i, l in enumerate(ls):
            p = l.split()
            if len(p) == 4 and p[0].lstrip('-').isdigit():
                idx0 = i
                break
        if idx0 is None:
            print("    !! 无数字行:", n)
            continue
        p0 = ls[idx0].split()
        p1 = ls[idx0 + 1].split()
        y0, y1 = int(p0[1]), int(p0[3])
        s1x = int(p1[0])
        old_adv = s1x - int(p0[0])
        new_x = s1x - SPACE_ADVANCE
        ls[idx0] = "%d\t%d\t%d\t%d" % (new_x, y0, new_x, y1)
        new = '\n'.join(ls)
        if trail and not new.endswith('\n'):
            new += '\n'
        blobs[n] = new.encode('utf-8')
        edited.append((n.split('/')[-1], old_adv, SPACE_ADVANCE, ls[idx0]))

    print("[2] TUV slot0 步进压缩：")
    for nm, a, b, line in edited:
        print("    %-22s %2d -> %d px   rect=%s" % (nm, a, b, line.replace('\t', ' ')))

    bak = ZIP + ".bak_before_space" + str(SPACE_ADVANCE) + "_" + TS
    shutil.copy2(ZIP, bak)
    tmp = ZIP + ".tmp"
    zo = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
    for n in names:
        zi = infos[n]
        if n.endswith('/'):
            zo.writestr(zipfile.ZipInfo(n, zi.date_time), b'')
        else:
            zinfo = zipfile.ZipInfo(n, zi.date_time)
            zinfo.compress_type = zi.compress_type
            zinfo.external_attr = zi.external_attr
            zo.writestr(zinfo, blobs[n])
    zo.close()
    try:
        os.replace(tmp, ZIP)
        print("[3] 重打包 %s (%d entries, %d bytes)" % (ZIP, len(names), os.path.getsize(ZIP)))
    except PermissionError:
        print("[3] !! 目标被占用（游戏在运行？）。已生成：")
        print("    %s (%d bytes)" % (tmp, os.path.getsize(tmp)))
        print("    请关闭游戏后执行:  mv \"%s\" \"%s\"" % (tmp, ZIP))
    print("    备份 %s" % bak)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", default=os.path.join(UPD, "DictRead.txt"),
                    help="字典文件路径（默认 update/DictRead.txt）")
    ap.add_argument("--no-dict", action="store_true", help="不改字典")
    ap.add_argument("--no-tuv", action="store_true", help="不压 TUV 步进、不重打包")
    args = ap.parse_args()

    if not args.no_dict:
        fix_dict(args.dict)
    if not args.no_tuv:
        fix_tuv_zip()


if __name__ == "__main__":
    main()
