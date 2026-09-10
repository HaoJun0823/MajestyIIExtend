# -*- coding: utf-8 -*-
"""重建后验证：① 空槽数 ② 槽位内容与参考渲染一致 ③ 用原版 7219 贴图反证字节序约定。"""
import re, os, io
import numpy as np
from PIL import Image
import build_font_atlas as B

ROOT = r"G:/Projects/MajestyIIExtend"
CPP = os.path.join(ROOT, "MajestyII_UTF8", "dllmain.cpp")
OUT = os.path.join(ROOT, "fontgen", "out_fromscratch")
ORIG_TUV = r"I:/SteamLibrary/steamapps/common/Majesty 2 Collection/update/localization/texts/small_c.tuv"
ORIG_DDS = r"I:/SteamLibrary/steamapps/common/Majesty 2 Collection/update/localization/texts/small_c.dds"

src = open(CPP, encoding="utf-8", errors="ignore").read()
m = re.search(r"g_charlist_data\[\]\s*=\s*\{(.*?)\};", src, re.S)
vals = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{4})", m.group(1))]
vals = [v for v in vals if v != 0]
idx_of = {}
for k, v in enumerate(vals):
    idx_of.setdefault(v, k)
print(f"表 {len(vals)} 项")

def load(tuv, dds):
    lines = open(tuv, encoding="utf-8", newline="").read().splitlines()
    bi = next(k for k, l in enumerate(lines) if l.strip().upper().startswith("TUVBASE"))
    r = [tuple(int(x) for x in l.split("\t")) for l in lines[bi+1:] if len(l.split("\t")) == 4]
    return Image.open(dds).convert("RGBA"), r

def mask(im, rect, pad=18):
    x1, y1, x2, y2 = rect
    o = np.zeros((pad, pad), np.uint8)
    if x2 <= x1 or y2 <= y1: return o
    a = (np.asarray(im.crop((x1, y1, x2, y2)))[:, :, 3] > 96).astype(np.uint8)
    h, w = a.shape
    o[:min(h, pad), :min(w, pad)] = a[:pad, :pad]
    return o

def iou(a, b):
    u = np.logical_or(a, b).sum()
    return np.logical_and(a, b).sum() / u if u else 0.0

# ---- ① 空槽统计 ----
im, rects = load(os.path.join(OUT, "small_c.tuv"), os.path.join(OUT, "small_c.dds"))
A = np.asarray(im)[:, :, 3]
empty = [k for k in range(len(vals))
         if rects[224+k][2] <= rects[224+k][0] or A[rects[224+k][1]:rects[224+k][3],
                                                     rects[224+k][0]:rects[224+k][2]].max() <= 16]
print(f"\n① small_c 空槽: {len(empty)} / {len(vals)}   (修复前 9713)")
def dec(v):
    try: return bytes([v & 0xFF, (v >> 8) & 0xFF]).decode("gbk")
    except Exception: return None
print(f"   其中表中本身可解码(即不应为空、需为0): "
      f"{sum(1 for k in empty if dec(vals[k]))}")

# ---- ② 槽位内容 vs 参考渲染 ----
chain = ["SourceHanSansHWSC-VF.ttf", "unifont-16.0.04.ttf"]
print("\n② 槽位内容 == 期望字符？(IoU 对参考渲染)")
tests = "国國这這阵陣敌敵战戰时時间間体體币幣胜勝中一人三东公时空国际"
bad = 0
for c in tests:
    try: b = c.encode("gbk")
    except Exception: print(f"   {c}: 非GBK"); continue
    L = b[0] | (b[1] << 8)
    if L not in idx_of:
        print(f"   {c}: 表内无此项 ✗"); bad += 1; continue
    slot = idx_of[L] + 224
    gm = mask(im, rects[slot])
    img, w, h = B.render_glyph_chain(c, chain, 14, "native", 128, 0.5, False, True, 0,0,0,0, 1)
    rm = np.zeros((18, 18), np.uint8)
    if img is not None:
        a = (np.asarray(img.split()[3]) > 96).astype(np.uint8)
        rm[:min(a.shape[0],18), :min(a.shape[1],18)] = a[:18, :18]
    v = iou(gm, rm)
    flag = "OK" if v > 0.6 else "⚠不符"
    if v <= 0.6: bad += 1
    print(f"   {c}  L={L:#06x} slot={slot:5d}  IoU={v:.3f} {flag}")
print(f"   不符数: {bad}（应为 0）")

# ---- ③ 原版 7219 贴图反证：slot224 应为 '！' ----
oim, orects = load(ORIG_TUV, ORIG_DDS)
om = mask(oim, orects[224])
print("\n③ 原版 7219 贴图 slot224 对 '！' / '。' 的 IoU（验证字节序约定）")
for c in ["！", "。"]:
    img, w, h = B.render_glyph_chain(c, chain, 14, "native", 128, 0.5, False, False, 0,0,0,0, 1)
    rm = np.zeros((18, 18), np.uint8)
    if img is not None:
        a = (np.asarray(img.split()[3]) > 96).astype(np.uint8)
        rm[:min(a.shape[0],18), :min(a.shape[1],18)] = a[:18, :18]
    print(f"   slot224 vs {c}: IoU={iou(om, rm):.3f}   (墨迹像素 {int(om.sum())})")
