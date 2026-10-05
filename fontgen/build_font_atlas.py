#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
TUV 字体图集生成器【数据驱动版】 - PNG + DDS(BGRA) + TUV 批量自动输出
================================================================================

【两种模式】
A. 追加模式（推荐，用于给游戏"原始贴图后面追加汉字"）：
   配置里提供 source_dds + source_tuv 两个键即进入本模式。
   - 读取游戏原始 DDS（未压缩 32 位 BGRA）作为底图，保留其原有 224 个基础
     字符（CP1252 0x20~0xFF）及其在原始 TUV 中的坐标不变；
   - 从 charlist（GBK）读出的中文字符渲染为白字+alpha 覆盖（与原始底图一致），
     在底图下方按行追加打包；
   - 直接写出与原始格式完全一致的 32 位 BGRA DDS 和扩展后的 TUV
     （TUVCOUNT = 224 + 中文字符数，前 224 行坐标原样保留）。
   - 无需 texconv，也不做 DXT 压缩，避免画质损失。

B. 从零生成模式（旧版）：不提供 source_dds/source_tuv 时，从空白图集全新打包。

【追加模式的每个字体配置键】
   source_dds   : 原始 DDS 路径（必填）
   source_tuv   : 原始 TUV 路径（必填；同族 a/b 变体可共享同一个 .tuv）
   size         : 字体像素字号
   outline      : true 表示"黑线描边"（字体说明.md 里的 _c / b 变体）
   bold         : true 表示加粗（_b 变体）
   out_prefix   : 输出文件名前缀（默认=原始 DDS 去掉扩展名的名字）
   tuv_out      : 可选；TUV 单独使用的名字（同族共享 TUV 时用，如 font12 家族
                  a/b 都写 font12.tuv）。缺省则与 out_prefix 相同。
   font_path    : 字体文件（可用 defaults 继承）
   enabled      : false 则跳过该字体

【TUV 格式】首行 TUVTXT，第二行 TUVCOUNT <n>，第三行 TUVBASE <宽> <高>，
随后每字符一行 <x1> <y1> <x2> <y2>（整数，左闭右开）。
原始游戏 TUV 用 Tab 分隔，坐标行原样保留。

【用法】
    python build_font_atlas.py [配置文件路径]
默认读取脚本同目录下的 font_config.yaml。也支持 .json。ini 已弃用。
相对路径均相对于配置文件所在目录；绝对路径原样使用。

【尺寸硬上限】
   游戏引擎支持的最大纹理为 4096×4096。本脚本在任何模式下都不会让图集
   的宽度或高度超过 MAX_ATLAS_DIM（= 4096）。超出时会打印警告并钳制，
   避免引擎丢弃/截断纹理导致追加的汉字不可见。

【字符过滤 / 自适应图集（节省贴图，针对 32 位进程内存上限）】
   在 from_scratch 模式下，若配置提供 `used_chars_txt`（GB18030 编码，内容为游戏
   里实际出现的全部文字），则只渲染「出现在该 txt 中」的汉字；其余汉字仍在 TUV 中
   保留槽位、但坐标写为 0 0 0 0（引擎画空、不显示方框），DDS 只打包有效字形 ——
   贴图体积大幅下降（例如 23940 字 → 仅实际用到的几千字）。
   开启该特性时，atlas_width/atlas_height 的 4096 固定值被忽略，改为从 1024 起自适应
   （按有效字数选最小的 2 的幂画布，仍受 MAX_ATLAS_DIM=4096 上限约束）。
================================================================================
"""
import os
import sys
import re
import json
import struct
import math
import subprocess
import importlib.util
import time

# ---------------------------------------------------------------------------
# 依赖检查
# ---------------------------------------------------------------------------
if importlib.util.find_spec("PIL") is None:
    print("缺少 Pillow(PIL) 库，请执行:  pip install Pillow")
    sys.exit(1)
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------------------
# 图集尺寸硬上限（游戏引擎上限 4096×4096，任何维度都不得超过）
# 之前某些路径会无脑翻倍（如高度翻倍可能到 8192），导致纹理被引擎丢弃/截断。
# ---------------------------------------------------------------------------
MAX_ATLAS_DIM = 4096

# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
def _load_yaml(path):
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        print(f"[配置] 解析 {path} 需要 pyyaml，请执行:  pip install pyyaml")
        sys.exit(1)

def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_config(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        raw = _load_json(path)
    else:
        raw = _load_yaml(path)
    if not isinstance(raw, dict):
        raise ValueError(f"配置文件根节点必须是字典/映射，拿到 {type(raw).__name__}")
    return normalize_config(raw, path)

def normalize_config(raw, cfg_path):
    cfg_dir = os.path.dirname(os.path.abspath(cfg_path))
    src_root = raw.get("SRC") or raw.get("src") or ""

    def rel(p):
        if not p:
            return p
        if p.startswith("!!SRC/"):
            if not src_root:
                raise ValueError("配置使用了 !!SRC/ 占位符但未定义顶层 SRC 路径")
            p = p[len("!!SRC/"):]
            base = os.path.join(cfg_dir, src_root)
        else:
            base = cfg_dir if not os.path.isabs(p) else ""
        return p if os.path.isabs(p) else os.path.join(base, p)

    defaults = raw.get("defaults") or {}
    fonts = raw.get("fonts") or []

    g = {
        "charlist": rel(raw.get("charlist", "charlist.txt")),
        "dict_file": rel(raw.get("dict_file", "") or "DictRead.txt"),
        "auto_charlist": raw.get("auto_charlist", True),
        "output_dir": rel(raw.get("output_dir", "out")),
        "atlas_width": int(raw.get("atlas_width", 2048)),
        "atlas_height": int(raw.get("atlas_height", raw.get("atlas_width", 2048))),
        "ttf_chain": [rel(p) for p in (raw.get("ttf_chain") or defaults.get("ttf_chain") or [])],
        "output_format": str(raw.get("output_format", "dxt")).lower(),
        "padding": int(raw.get("padding", 1)),
        "texconv": rel(raw.get("texconv", "")),
        "start_code": raw.get("start_code", 0x20),
        "end_code": raw.get("end_code", 0xFF),
        "charlist_file": rel(raw.get("charlist_file", "")),
        # 字表来源：file = 读 charlist_file 字节序字表；dll = 直接读 dllmain.cpp 的
        #   g_charlist_data[]（任何序都行，贴图顺序与 DLL 严格同源，物理上不可能错位）
        "charlist_source": str(raw.get("charlist_source", "file")).lower(),
        "dll_cpp": rel(raw.get("dll_cpp", "")),
        # 码点网格模式：贴图按 Unicode 码点升序固定槽位
        #   slot 224 = U+grid_start（默认 0x4E00 一），slot 224+k = U+(grid_start+k)
        #   缺失码点为空槽。此序与游戏引擎「码点→槽位」对齐（原版中文贴图即此序）。
        "codepoint_grid": bool(raw.get("codepoint_grid", False)),
        "grid_start": int(str(raw.get("grid_start", "0x4E00")), 0),
        "grid_end": int(str(raw.get("grid_end", "0x9FFF")), 0),
        # 字符过滤：GB18030 编码的 txt（游戏实际出现的文字）；提供则只渲染用到的字
        "used_chars_txt": rel(raw.get("used_chars_txt", "")),
    }

    norm_fonts = []
    for i, f in enumerate(fonts or []):
        if not isinstance(f, dict):
            raise ValueError(f"fonts[{i}] 必须是字典")
        fc = {}
        fc["prefix"] = str(f.get("prefix", f"font_{i}"))
        fc["font_path"] = rel(f.get("font_path", "") or r"C:/Windows/Fonts/simhei.ttf")
        fc["size"] = int(f.get("size", 32))
        for k, v in defaults.items():
            if k not in f:
                fc[k] = v
        for k, v in f.items():
            if k not in ("prefix", "font_path", "size"):
                fc[k] = v
        # 归一化数字字段
        for key in ("threshold", "sharpness"):
            if key in fc and isinstance(fc[key], str):
                fc[key] = float(fc[key])
        # 布尔字段
        for key in ("bold", "outline", "zero_space_width", "auto_dds", "enabled"):
            if isinstance(fc.get(key), str):
                fc[key] = fc[key].strip().lower() in ("1", "true", "yes", "y", "on")
        for key in ("padding_top", "padding_bottom", "padding_left", "padding_right"):
            fc[key] = int(fc[key]) if key in fc and fc[key] is not None else 0
        if isinstance(fc.get("supersample"), str):
            fc["supersample"] = int(fc["supersample"])
        # 追加模式特有字段
        fc.update({
            "source_dds": rel(fc.get("source_dds", "")),
            "source_tuv": rel(fc.get("source_tuv", "")),
            "out_prefix": str(fc.get("out_prefix", "")) or None,
            "tuv_out": str(fc.get("tuv_out", "")) or None,
        })
        fc.setdefault("render_mode", "smooth")
        fc.setdefault("threshold", 128)
        fc.setdefault("sharpness", 1.5)
        fc.setdefault("bold", False)
        fc.setdefault("outline", False)
        fc.setdefault("supersample", 2)
        fc.setdefault("zero_space_width", False)
        # 空格槽 slot0 目标步进 px（见 write_tuv_scratch 文档）。
        #   None / 不写 = 保持自然格宽；数字 = 压到该值（2 为实机验证值）。
        if fc.get("space_advance") is not None:
            fc["space_advance"] = int(fc["space_advance"])
        else:
            fc["space_advance"] = None
        fc.setdefault("auto_dds", True)
        fc.setdefault("enabled", True)
        fc.setdefault("patch_png", "")
        if fc["patch_png"]:
            fc["patch_png"] = rel(fc["patch_png"])
        # 追加模式默认输出前缀 = 原始 DDS 名字
        if not fc["out_prefix"] and fc["source_dds"]:
            fc["out_prefix"] = os.path.splitext(os.path.basename(fc["source_dds"]))[0]
        # 字符过滤 txt：per-font 覆盖全局（相对路径按配置目录展开）
        _uct = f.get("used_chars_txt")
        fc["used_chars_txt"] = rel(_uct) if _uct else g["used_chars_txt"]
        norm_fonts.append(fc)

    # 解析每个字体的 ttf_chain 路径（defaults 已合并进 fc，这里只做路径展开）
    for fc in norm_fonts:
        if "ttf_chain" in fc:
            fc["ttf_chain"] = [rel(p) for p in fc["ttf_chain"] if p]
        else:
            fc["ttf_chain"] = list(g["ttf_chain"])

    if not norm_fonts:
        raise ValueError("配置中没有 fonts 列表，至少需要一个字体条目")
    if g["atlas_width"] <= 0 or g["atlas_width"] % 512 != 0:
        raise ValueError("atlas_width 必须是 512 的正整数倍（追加模式不使用，但保留校验）")
    if g["atlas_width"] > MAX_ATLAS_DIM or g["atlas_height"] > MAX_ATLAS_DIM:
        print(f"[配置] ⚠ atlas_width/atlas_height 超过游戏上限 {MAX_ATLAS_DIM}，"
              f"生成时将强制钳制")

    g["fonts"] = norm_fonts
    g["_cfg_dir"] = cfg_dir
    # 布尔字段归一化（INI 解析出来是字符串）
    if isinstance(g.get("auto_charlist"), str):
        g["auto_charlist"] = g["auto_charlist"].strip().lower() in ("1", "true", "yes", "y", "on")
    return g

# ---------------------------------------------------------------------------
# 自动生成 charlist：优先从 DictRead.txt 提取全部非 ASCII 字符
# 没有 DictRead.txt 时沿用现有 charlist
# ---------------------------------------------------------------------------
def decode_text(raw):
    """自动检测文本编码：BOM 优先，其次 UTF-8 严格解码，失败回退 GBK"""
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16-le")
    if raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16-be")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk")

def read_charlist(path):
    """读取 charlist（UTF-8 优先，兼容旧 GBK 文件），返回去除控制符后的字符列表"""
    with open(path, "rb") as f:
        raw = f.read()
    text = decode_text(raw)
    return [c for c in text if c not in ("\n", "\r", "\t", "\x0c", "\x00")]

def ensure_charlist(cfg):
    if not cfg.get("auto_charlist", True):
        print("[字符库] auto_charlist 已关闭，直接使用现有 charlist")
        return
    dict_path = cfg.get("dict_file") or ""
    if not (dict_path and os.path.isfile(dict_path)):
        print(f"[字符库] 未找到 {os.path.basename(dict_path or 'DictRead.txt')}，沿用现有 charlist：{cfg['charlist']}")
        return
    try:
        raw = open(dict_path, "rb").read()
        text = decode_text(raw)
    except Exception as e:
        print(f"[字符库] ⚠️ 读取 {dict_path} 失败：{e}，沿用现有 charlist")
        return

    chars = []
    seen = set()
    for ch in text:
        if ch in "\r\n\t\x0c\x00" or ord(ch) < 0x80:   # 跳过控制符与 ASCII（基础 224 已含）
            continue
        if ch in seen:
            continue
        if ch == "\ufffd":                              # 解码失败产生的替换符，直接丢弃
            continue
        seen.add(ch)
        chars.append(ch)
    content = "".join(chars)
    if not content:
        print(f"[字符库] ⚠️ {os.path.basename(dict_path)} 未提取到任何字符，沿用现有 charlist")
        return

    old = ""
    if os.path.isfile(cfg["charlist"]):
        try:
            old = "".join(read_charlist(cfg["charlist"]))
        except Exception:
            old = ""
    if old == content:
        print(f"[字符库] 已是最新（{len(chars)} 字符），复用 {cfg['charlist']}")
        return
    # 统一 UTF-8 写回（任何编辑器打开都不乱码；读取端自动兼容）
    with open(cfg["charlist"], "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[字符库] 已根据 {os.path.basename(dict_path)} 重新生成 {cfg['charlist']}"
          f"（{len(chars)} 个字符，UTF-8 编码）")

# ---------------------------------------------------------------------------
# 字体加载
# ---------------------------------------------------------------------------
_FONT_CACHE = {}

def load_font(font_path, pixel_size):
    key = (os.path.abspath(font_path), int(round(pixel_size)))
    f = _FONT_CACHE.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(font_path, pixel_size)
        except Exception as e:
            raise FileNotFoundError(f"字体加载失败 {font_path}：{e}")
        _FONT_CACHE[key] = f
    return f

def _font_has_glyph(font, ch):
    """快速探测字体是否包含该字符（getmask 非空）。缺失字符通常返回空白/.notdef。"""
    try:
        m = font.getmask(ch)
        return m.getbbox() is not None
    except Exception:
        return False

# ---------------------------------------------------------------------------
# DDS 读取（仅未压缩 32 位 BGRA，与游戏原始图集一致）
# ---------------------------------------------------------------------------
def load_dds_rgba(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:4] != b"DDS ":
        raise ValueError(f"不是有效的 DDS 文件：{path}（也许被误命名为 .dds，实际是其他格式）")
    H = struct.unpack("<I", raw[12:16])[0]
    W = struct.unpack("<I", raw[16:20])[0]
    fl = struct.unpack("<I", raw[80:84])[0]
    if fl & 0x4:  # DDSD_FOURCC -> 压缩纹理（DXT 等）
        raise ValueError(f"暂不支持压缩 DDS（{os.path.basename(path)} 是 DXT），"
                         f"请先用工具转成 32 位 BGRA")
    header = raw[:128]
    pixel = raw[128:]
    required = W * 4 * H
    if len(pixel) < required:
        raise ValueError(f"DDS 数据不足：{path}（期望 {required} 字节，实际 {len(pixel)}）")
    img = Image.frombytes("RGBA", (W, H), pixel[:required], "raw", "BGRA")
    return img, header

def save_bgra_dds(path, img, base_header):
    img = img.convert("RGBA")
    r, g, b, a = img.split()
    bgra = Image.merge("RGBA", (b, g, r, a))   # 通道重排为 B,G,R,A
    data = bgra.tobytes()
    W, H = img.size
    hdr = bytearray(base_header[:128])
    struct.pack_into("<I", hdr, 12, H)       # height
    struct.pack_into("<I", hdr, 16, W)       # width
    struct.pack_into("<I", hdr, 20, W * 4)   # pitch / linear size (RGB)
    with open(path, "wb") as f:
        f.write(hdr)
        f.write(data)

# ---------------------------------------------------------------------------
# texconv 封装（新版 DirectXTex：格式用 DXGI 名，如 BC2_UNORM / R8G8B8A8_UNORM）
# ---------------------------------------------------------------------------
DXT_TO_BC = {"DXT1": "BC1_UNORM", "DXT2": "BC2_UNORM",
             "DXT3": "BC2_UNORM", "DXT4": "BC3_UNORM", "DXT5": "BC3_UNORM"}

def detect_dds_fourcc(path):
    with open(path, "rb") as f:
        raw = f.read(128)
    if raw[:4] != b"DDS ":
        raise ValueError(f"不是有效的 DDS 文件：{path}（也许被误命名为 .dds，实际是其他格式）")
    fl = struct.unpack("<I", raw[80:84])[0]
    if fl & 0x4:
        return raw[84:88].decode("ascii", "ignore").upper()
    return "BGRA"

def _texconv_run(tc_path, args):
    r = subprocess.run([tc_path, "-nologo", "-y", "-m", "1"] + args,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", timeout=600)
    return r

def texconv_decode(src_dds, tmpdir, tc_path):
    """DXT DDS -> RGBA PNG，返回 PNG 路径"""
    r = _texconv_run(tc_path, ["-ft", "png", "-f", "R8G8B8A8_UNORM",
                               "-o", tmpdir, src_dds])
    out = os.path.join(tmpdir, os.path.splitext(os.path.basename(src_dds))[0] + ".png")
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(f"texconv 解码失败：{(r.stderr or r.stdout)[-400:]}")
    return out

def texconv_encode(png_path, outdir, bc, tc_path):
    """RGBA PNG -> DXT DDS（BC1/BC2/BC3），返回 DDS 路径"""
    r = _texconv_run(tc_path, ["-f", bc, "-o", outdir, png_path])
    out = os.path.join(outdir, os.path.splitext(os.path.basename(png_path))[0] + ".dds")
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(f"texconv 编码失败：{(r.stderr or r.stdout)[-400:]}")
    return out

# ---------------------------------------------------------------------------
# TUV 读取 / 写入
# ---------------------------------------------------------------------------
def read_tuv(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\r\n") for ln in f]
    count = None
    base_start = None
    for i, ln in enumerate(lines):
        if ln.upper().startswith("TUVBASE"):
            base_start = i + 1            # 坐标行从 TUVBASE 之后开始
        elif ln.upper().startswith("TUVCOUNT") and count is None:
            count = int(ln.split()[1])
    if base_start is None or count is None:
        raise ValueError(f"TUV 文件缺少/损坏 TUVTXT/TUVCOUNT/TUVBASE 头：{path}")
    base = lines[base_start:base_start + count]
    if not base:
        raise ValueError(f"TUV 文件缺少坐标行：{path}")
    return len(base), base

def write_tuv(path, base_lines, new_coords, total_count, w, h, zero_space_width=False):
    space_chars = {' ', '\u3000', '\t', '\n', '\r'}
    ZERO_INDEX = 223  # 0xFF = ÿ：引擎 CJK 前置标记槽，必须零尺寸（覆盖原版拉丁底图里的真实字形）
    with open(path, "w", encoding="utf-8") as f:
        f.write("TUVTXT\n")
        f.write(f"TUVCOUNT {total_count}\n")
        f.write(f"TUVBASE {w} {h}\n")
        for i, s in enumerate(base_lines):
            if i == ZERO_INDEX:
                f.write("0\t0\t0\t0\n")
            else:
                f.write(s + "\n")
        for x1, y1, x2, y2 in new_coords:
            f.write(f"{x1}\t{y1}\t{x2}\t{y2}\n")
    return total_count

# ---------------------------------------------------------------------------
# 追加模式：单个字符渲染（直接产 RGBA，白字+黑描边）
# ---------------------------------------------------------------------------
def glyph_advance_px(font_path, ch, pixel_size, _cache=None):
    """读取字形在 pixel_size 下的水平 advance（= 正确字距）。
    主源用 PIL getlength（FreeType 实例值，与渲染同源、且天然覆盖空格/全部 cmap）；
    fontTools hmtx 仅作兜底（处理个别 getlength 失败的情形）。返回 (advance_px, xmin_px)。"""
    # 主：FreeType getlength（与下方渲染用同一套 FreeType 实例，advance 即引擎应进位宽度）
    try:
        f = load_font(font_path, pixel_size)
        adv = f.getlength(ch)
        if adv and adv > 0:
            return adv, 0.0
    except Exception:
        pass
    # 兜底：fontTools hmtx（font 单位 / upem 缩放）
    if _cache is None:
        _cache = glyph_advance_px._cache
    try:
        tt = _cache.get(font_path)
        if tt is None:
            from fontTools.ttLib import TTFont
            tt = TTFont(font_path, lazy=True)
            _cache[font_path] = tt
        cp = ord(ch)
        cmap = tt.getBestCmap()
        if cp in cmap:
            gn = cmap[cp]
            adv = tt["hmtx"][gn][0] * pixel_size / tt["head"].unitsPerEm
            return adv, 0.0
    except Exception:
        pass
    return None, 0.0
glyph_advance_px._cache = {}


def latin_glyph_metrics(font_path, font_size, _cache=None):
    """Latin 区(0x20–0xFF)垂直布局度量：扫描整段拉丁字，取全局最高上升(min_top)与最深下伸
    (max_bottom)，返回 (y_offset, base_box_h)。
    y_offset 为所有 Latin 字共用的固定基线参考（draw.text 笔原点相对 box 顶），base_box_h 为
    统一行高。固定 y_offset 可让所有拉丁字基线齐平、下伸字(j/y/p/g/q)正确下探到基线下方，
    修复此前"贴底"逻辑把有下伸字基线抬高、导致 j/y 比 Maest 高/下伸失效的问题。缓存 per (font,size)。"""
    if _cache is None:
        _cache = latin_glyph_metrics._cache
    key = (font_path, font_size)
    if key in _cache:
        return _cache[key]
    import numpy as np
    from PIL import Image, ImageDraw
    f = load_font(font_path, font_size)
    DRAW_Y = 1000
    min_top = 10 ** 9
    max_bot = -10 ** 9
    for c in range(0x20, 0x100):
        im = Image.new("L", (40, 2100), 0)
        ImageDraw.Draw(im).text((5, DRAW_Y), chr(c), font=f, fill=255)
        a = np.asarray(im)
        rows = np.where(a.max(axis=1) > 10)[0]
        if len(rows) == 0:
            continue
        min_top = min(min_top, int(rows.min()) - DRAW_Y)
        max_bot = max(max_bot, int(rows.max()) - DRAW_Y)
    if min_top == 10 ** 9:
        min_top, max_bot = 0, font_size
    y_off = -min_top
    h = max_bot - min_top
    res = (y_off, h)
    _cache[key] = res
    return res
latin_glyph_metrics._cache = {}


def render_glyph_rgba(char, font_path, font_size, render_mode="smooth",
                      threshold=128, sharpness=1.5, bold=False, outline=False,
                      padding_top=0, padding_bottom=0, padding_left=0, padding_right=0,
                      supersample=1, advance_px=None, glyph_xmin_px=None,
                      latin_vmetrics=None):
    """原生 1x 绘制（FreeType 自带抗锯齿），字形输出为「纯白(255,255,255)+alpha」覆盖蒙版。
    不使用超采样/LANCZOS 缩放，避免白边与透明黑混合产生灰边（‘白色不纯’问题）。
    描边(outline)变体为「纯黑(0,0,0)描边 + 纯白填充」。
    advance_px 不为 None 时进入‘比例模式’：按字体真实 advance 变宽打包、左对齐并保留
    左侧边距(LSB)防裁切，用于 Latin 区(0x20–0xFF)；为 None 时保持固定字号格子(水平居中)，用于 CJK 区。
    返回 (RGBA 图像, 宽, 高)。"""
    from PIL import ImageChops
    base_box_h = font_size + padding_top + padding_bottom

    font = load_font(font_path, font_size)

    # 计算字形落点（基线贴底）
    try:
        bbox = font.getbbox(char)
    except Exception:
        try:
            bbox = font.getmask(char).getbbox()
        except Exception:
            bbox = None
    if not bbox:
        bbox = (0, 0, font_size, font_size)
    char_w = bbox[2] - bbox[0]
    char_h = bbox[3] - bbox[1]

    if advance_px is not None:
        # 比例模式(Latin 区)：cell 宽 = max(字体真实 advance, 墨宽)，左对齐。
        # 垂直方向：整段 Latin 共用同一基线 y_offset 与行高 base_box_h（由 latin_vmetrics 给出），
        # 使所有拉丁字基线齐平、j/y/p/g/q 等下伸字正确下探到基线下方——而非把墨迹底贴齐 box 底
        # （那种"贴底"会把有下伸字的基线抬高，导致 j/y 比 Maest 高、下伸失效）。
        # left_pad 仅用于吸收负 LSB（bbox[0]<0）防左侧裁切。
        if latin_vmetrics is not None:
            lat_y, lat_h = latin_vmetrics
        else:
            lat_y, lat_h = latin_glyph_metrics(font_path, font_size)
        base_box_h = lat_h
        left_pad = max(0, int(math.ceil(-bbox[0]))) if bbox[0] < 0 else 0
        base_box_w = max(int(round(advance_px)) + left_pad, char_w + left_pad)
        x_offset = left_pad - bbox[0]
        y_offset = lat_y
    else:
        # 固定格子模式(CJK 区)：字号为宽，水平居中；墨迹底贴 box 底
        base_box_w = font_size + padding_left + padding_right
        x_offset = padding_left + (base_box_w - padding_left - padding_right - char_w) // 2 - bbox[0]
        y_offset = base_box_h - padding_bottom - bbox[3]

    def _mask(off_x, off_y):
        m = Image.new("L", (base_box_w, base_box_h), 0)
        ImageDraw.Draw(m).text((off_x, off_y), char, font=font, fill=255)
        return m

    white_rgb = Image.new("RGB", (base_box_w, base_box_h), (255, 255, 255))

    if outline:
        # 黑描边（8 邻域偏移，先画底层）
        om = Image.new("L", (base_box_w, base_box_h), 0)
        od = ImageDraw.Draw(om)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                od.text((x_offset + dx, y_offset + dy), char, font=font, fill=255)
        if bold:
            for dx, dy in ((-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,-2),(-2,2),(2,2)):
                od.text((x_offset + dx, y_offset + dy), char, font=font, fill=255)
        # 白填充（中心）
        fm = _mask(x_offset, y_offset)
        # 合成：描边(黑,alpha=om) 在下，填充(白,alpha=fm) 在上
        out = Image.new("RGBA", (base_box_w, base_box_h), (0, 0, 0, 0))
        out.putalpha(om)
        white_rgba = Image.merge("RGBA",
                                  (white_rgb.split()[0], white_rgb.split()[1],
                                   white_rgb.split()[2], fm))
        canvas = Image.alpha_composite(out, white_rgba)
    else:
        fm = _mask(x_offset, y_offset)
        if bold:
            for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                fm = ImageChops.add(fm, _mask(x_offset + dx, y_offset + dy))
        canvas = Image.merge("RGBA",
                             (white_rgb.split()[0], white_rgb.split()[1],
                              white_rgb.split()[2], fm))

    return canvas, base_box_w, base_box_h

# ---------------------------------------------------------------------------
# 追加打包：在底图下方逐行追加字形
# ---------------------------------------------------------------------------
def pack_appended(base_w, glyphs, y_start, padding=1):
    new_coords = []
    cx, cy, row_max = 0, y_start, 0
    for ch, g, w, h in glyphs:
        if g is None:
            new_coords.append((0, 0, 0, 0))
            continue
        w = min(w, base_w)
        if cx + w > base_w:
            cx = 0
            cy += row_max + padding
            row_max = 0
        box = (cx, cy, cx + w, cy + h)
        new_coords.append(box)
        cx += w + padding
        row_max = max(row_max, h)
    final_h = (cy + row_max) if glyphs else y_start
    return new_coords, final_h

# ---------------------------------------------------------------------------
# 旧版：从零渲染（保留）
# ---------------------------------------------------------------------------
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
    font = load_font(font_path, render_font_size)

    bbox = draw.textbbox((0, 0), char, font=font)
    char_w = bbox[2] - bbox[0]
    char_h = bbox[3] - bbox[1]

    x_offset = (padding_left * factor) + (render_w - (padding_left + padding_right) * factor - char_w)//2 - bbox[0]
    y_offset = render_h - bbox[3] - (padding_bottom * factor)

    if bold and render_mode == "smooth":
        for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
            draw.text((x_offset+dx, y_offset+dy), char, font=font, fill=128)
        draw.text((x_offset, y_offset), char, font=font, fill=255)
    else:
        draw.text((x_offset, y_offset), char, font=font, fill=255)

    if render_mode == "smooth":
        if sharpness != 1.0:
            def enhance(p):
                return max(0, int(p*(1-(1-sharpness)*0.5))) if p < 128 \
                       else min(255, int(128+(p-128)*sharpness))
            canvas = canvas.point(enhance)
        if sharpness > 1.2:
            canvas = canvas.filter(ImageFilter.SHARPEN)
    elif render_mode == "binary":
        canvas = canvas.point(lambda p: 255 if p > threshold else 0)

    if factor > 1:
        canvas = canvas.resize((base_box_w, base_box_h), Image.Resampling.LANCZOS)
    return canvas, base_box_w, base_box_h

def pack_atlas(glyph_list, atlas_width=2048, padding=1):
    coord_list = []
    current_height = 512
    atlas = Image.new("L", (atlas_width, current_height), 0)
    cx, cy, row_max_h = 0, 0, 0
    for _, glyph, w, h in glyph_list:
        if glyph is None:
            coord_list.append((0, 0, 0, 0))
            continue
        if cx + w > atlas_width:
            cx = 0
            cy += row_max_h + padding
            row_max_h = 0
            if cy + h > atlas.height:
                nh = ((cy + h + 511) // 512) * 512
                # 游戏硬上限：任何维度不得超过 MAX_ATLAS_DIM
                if nh > MAX_ATLAS_DIM:
                    nh = MAX_ATLAS_DIM
                nc = Image.new("L", (atlas_width, nh), 0)
                nc.paste(atlas, (0, 0))
                atlas = nc
        # 已到上限仍放不下 → 写空槽，避免 paste 越界
        if cy + h > MAX_ATLAS_DIM or cx + w > atlas_width:
            coord_list.append((0, 0, 0, 0))
            cx += w + padding
            row_max_h = max(row_max_h, h)
            continue
        box = (cx, cy, cx + w, cy + h)
        atlas.paste(glyph, box)
        coord_list.append(box)
        cx += w + padding
        row_max_h = max(row_max_h, h)
    final_h = cy + row_max_h
    actual_h = max(atlas.height, ((final_h + 511) // 512) * 512)
    if actual_h > MAX_ATLAS_DIM:
        actual_h = MAX_ATLAS_DIM
    if actual_h < atlas.height:
        atlas = atlas.crop((0, 0, atlas_width, actual_h))
    elif actual_h > atlas.height:
        nc = Image.new("L", (atlas_width, actual_h), 0)
        nc.paste(atlas, (0, 0))
        atlas = nc
    return atlas, coord_list, actual_h

def apply_png_patch(atlas_img, coord_list, index, png_path):
    x1, y1, x2, y2 = coord_list[index]
    if x2 - x1 == 0 or y2 - y1 == 0:
        print(f"[补丁] 索引 {index} 尺寸为0，跳过")
        return atlas_img
    try:
        png = Image.open(png_path).convert("RGBA")
        png = png.resize((x2-x1, y2-y1), Image.Resampling.LANCZOS)
        if atlas_img.mode == 'L':
            rgba = Image.new("RGBA", atlas_img.size, (0,0,0,0))
            rgba.putalpha(atlas_img)
            white = Image.new("RGB", atlas_img.size, (255,255,255))
            rgba.paste(white, (0,0), atlas_img)
            atlas_img = rgba
        atlas_img.paste(png, (x1, y1), png)
        print(f"[补丁] ✅ 已应用到索引 {index}（$ 字符）")
    except Exception as e:
        print(f"[补丁] ⚠️ 失败：{e}")
    return atlas_img

def find_texconv(explicit=None):
    if explicit and os.path.isfile(explicit):
        return explicit
    search_dirs = [
        os.path.dirname(sys.executable),
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd(),
    ]
    for d in search_dirs:
        c = os.path.join(d, "texconv.exe")
        if os.path.isfile(c):
            return c
    from shutil import which
    return which("texconv.exe")

def convert_png_to_dds(png_path, texconv_path, output_dir):
    out_dds = os.path.join(output_dir, os.path.splitext(os.path.basename(png_path))[0] + ".dds")
    try:
        r = subprocess.run([texconv_path, "-nologo", "-y", "-m", "1", "-f", "BC3_UNORM",
                            "-o", output_dir, png_path],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="ignore", timeout=120)
    except Exception as e:
        print(f"      ↳ DDS 转换异常：{e}")
        return
    if r.returncode == 0 and os.path.isfile(out_dds):
        print(f"      ↳ DDS: {out_dds} (DXT5)")
        return
    msg = r.stderr.strip()[-300:] if getattr(r, "stderr", None) else ""
    print(f"      ↳ DDS 转换失败，返回码 {r.returncode} {msg}")

def write_tuv_onepass(file_path, char_list, tex_w, tex_h, coords, zero_space_width=False):
    space_chars = {' ', '\u3000', '\t', '\n', '\r'}
    ZERO_INDEX = 223
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("TUVTXT\n")
        f.write(f"TUVCOUNT {len(char_list)}\n")
        f.write(f"TUVBASE {tex_w} {tex_h}\n")
        for idx, (x1, y1, x2, y2) in enumerate(coords):
            if idx == ZERO_INDEX:
                f.write("0\t0\t0\t0\n")
                continue
            if zero_space_width and idx < len(char_list) and char_list[idx] in space_chars:
                f.write(f"{x1}\t{y1}\t{x1}\t{y2}\n")
            else:
                f.write(f"{x1}\t{y1}\t{x2}\t{y2}\n")

# ---------------------------------------------------------------------------
# 追加模式：构建
# ---------------------------------------------------------------------------
def build_append(g, fc):
    src_dds = fc["source_dds"]
    src_tuv = fc["source_tuv"]
    font_path = fc["font_path"]
    font_size = fc["size"]
    render_mode = fc["render_mode"]
    outline = fc.get("outline", False)
    bold = fc.get("bold", False)
    prefix = fc["out_prefix"]
    desc = ("描边" if outline else "") + ("加粗" if bold else "")
    if not desc:
        desc = "常规"
    print(f"\n===== 追加 [{prefix}]（基于 {os.path.basename(src_dds)}）  "
          f"字号={font_size}px  {desc} =====")

    if not os.path.isfile(src_dds):
        print(f"  ✗ 原始 DDS 不存在：{src_dds}")
        return False
    if not os.path.isfile(src_tuv):
        print(f"  ✗ 原始 TUV 不存在：{src_tuv}（同族 a/b 变体请指向共享的 .tuv）")
        return False
    if not os.path.isfile(font_path):
        print(f"  ✗ 字体文件不存在：{font_path}")
        return False

    base_img, base_header = None, None
    fourcc = detect_dds_fourcc(src_dds)
    if fourcc != "BGRA":
        if fourcc not in DXT_TO_BC:
            print(f"  ✗ 不支持的压缩格式 {fourcc}（仅支持 DXT1/3/5）")
            return False
        tc = find_texconv(g["texconv"])
        if not tc:
            print(f"  ✗ 未找到 texconv.exe（{fourcc} 格式必须用它解码）")
            return False
        tmpdir = os.path.join(g.get("_cfg_dir") or os.getcwd(), ".tmp_texconv")
        os.makedirs(tmpdir, exist_ok=True)
        dec_png = texconv_decode(src_dds, tmpdir, tc)
        base_img = Image.open(dec_png).convert("RGBA")
        print(f"      ↳ {fourcc} 解码完成（{base_img.width}×{base_img.height}）")
    else:
        base_img, base_header = load_dds_rgba(src_dds)
    base_w, base_h = base_img.size
    if base_w > MAX_ATLAS_DIM or base_h > MAX_ATLAS_DIM:
        print(f"  ✗ 原始 DDS {base_w}×{base_h} 已超过游戏上限 {MAX_ATLAS_DIM}，无法继续")
        return False
    base_count, base_lines = read_tuv(src_tuv)
    base_total0 = base_count

    # 中文字符：仅 charlist 里的字符（基础 224 已在底图中，不再渲染）
    if not os.path.exists(g["charlist"]):
        print(f"  ✗ 找不到 charlist 文件：{g['charlist']}")
        return False
    try:
        cn_chars = read_charlist(g["charlist"])
    except Exception:
        print(f"  ✗ {g['charlist']} 不是有效的文本文件")
        return False

    # 渲染
    glyphs = []
    for ch in cn_chars:
        try:
            img, w, h = render_glyph_rgba(
                ch, font_path, font_size, render_mode,
                fc["threshold"], fc["sharpness"], bold, outline,
                fc["padding_top"], fc["padding_bottom"],
                fc["padding_left"], fc["padding_right"], fc["supersample"])
        except Exception as e:
            print(f"  ⚠️ 渲染失败跳过字符 {ch!r}：{e}")
            img, w, h = None, 0, 0
        glyphs.append((ch, img, w, h))

    # 画布：宽度用 2 的幂（默认 2048，与正确字库一致），高度取 2 的幂
    # 老游戏 D3D9 引擎对非 2 的幂纹理高度会钳制/截断，导致 y≥原高的追加区不可见
    canvas_w = max(int(fc.get("atlas_width") or g.get("atlas_width", 2048)), base_w)
    # 游戏硬上限：任何维度不得超过 MAX_ATLAS_DIM
    if canvas_w > MAX_ATLAS_DIM:
        print(f"  ⚠ 画布宽 {canvas_w} 超过游戏上限 {MAX_ATLAS_DIM}，已强制钳制"
              f"（超出部分字形可能被裁切）")
        canvas_w = MAX_ATLAS_DIM
    new_coords, needed_h = pack_appended(canvas_w, glyphs, base_h, g["padding"])
    final_h = max(base_h, needed_h)
    p2 = 64
    while p2 < final_h:
        p2 <<= 1
    if p2 > MAX_ATLAS_DIM:
        print(f"  ⚠ 追加后图集高 {p2} 超过游戏上限 {MAX_ATLAS_DIM}，已强制钳制"
              f"（部分中文字形可能不可见；建议缩小字号或改用字表模式）")
        p2 = MAX_ATLAS_DIM
    final_h = p2
    ext = Image.new("RGBA", (canvas_w, final_h), (255, 255, 255, 0))
    ext.paste(base_img, (0, 0))
    dropped = 0
    for (ch, img, w, h), (x1, y1, x2, y2) in zip(glyphs, new_coords):
        if img is not None and x2 - x1 > 0 and y2 - y1 > 0:
            if x2 > canvas_w or y2 > final_h:
                # 被上限截断：写空槽并在 TUV 里改为 0 0 0 0，避免显示花屏
                dropped += 1
                idx = new_coords.index((x1, y1, x2, y2))
                new_coords[idx] = (0, 0, 0, 0)
                continue
            ext.paste(img, (x1, y1))
    if dropped:
        print(f"  ⚠ 有 {dropped} 个字形因超出 {MAX_ATLAS_DIM} 上限被丢弃（写空槽）")

    os.makedirs(g["output_dir"], exist_ok=True)
    tuv_name = fc.get("tuv_out") or prefix
    tuv_path = os.path.join(g["output_dir"], tuv_name + ".tuv")
    dds_path = os.path.join(g["output_dir"], prefix + ".dds")
    png_path = os.path.join(g["output_dir"], prefix + ".png")

    # 输出格式：默认 DXT（与正确字库一致；BGRA 源也转 DXT3），可配 bgra 保持无损
    out_fmt = str(fc.get("output_format") or g.get("output_format") or "dxt").lower()
    ext.save(png_path, format="PNG")
    if out_fmt == "bgra":
        save_bgra_dds(dds_path, ext, base_header)
        print(f"      ↳ DDS: {dds_path}（BGRA 32 位）")
    else:
        tc = find_texconv(g["texconv"])
        if not tc:
            print(f"  ✗ 未找到 texconv.exe，无法编码 DXT（可配置 output_format: bgra）")
            return False
        bc = DXT_TO_BC.get(fourcc, "BC2_UNORM")   # 未知/BGRA 源 → DXT3，与正确字库一致
        texconv_encode(png_path, g["output_dir"], bc, tc)
        print(f"      ↳ DDS: {dds_path}（{bc} 编码）")

    total = write_tuv(tuv_path, base_lines, new_coords,
                      base_total0 + len(cn_chars), ext.width, ext.height,
                      fc["zero_space_width"])

    print(f"  ✅ {dds_path}（{ext.width}×{ext.height}，追加 {len(cn_chars)} 个汉字）")
    print(f"     {tuv_path}（TUVCOUNT {total}：基础 {base_total0} + 中文 {len(cn_chars)},")
    return True

# ---------------------------------------------------------------------------
# from_scratch 模式：TTF 渲染 0x20–0xFF + 特殊码从原图抠取覆盖
# ---------------------------------------------------------------------------
def load_source_image(path):
    """按文件头判断格式加载源贴图：BMP / 未压缩 DDS / 其它交给 PIL。"""
    with open(path, "rb") as f:
        head = f.read(4)
    if head[:2] == b"BM":
        im = Image.open(path)
        im = im.convert("RGBA")
        im.load()
        return im
    if head[:4] == b"DDS ":
        img, _ = load_dds_rgba(path)
        return img
    im = Image.open(path)
    im = im.convert("RGBA")
    im.load()
    return im


def glyph_has_content(img, thr=10):
    """判定渲染结果是否真的有可见像素（alpha 通道最大值超过阈值）。"""
    if img is None:
        return False
    a = img.getchannel("A")
    mn, mx = a.getextrema()
    return mx > thr


SPACE_CHARS = {' ', '\u3000', '\t', '\n', '\r'}


def render_glyph_chain(char, ttf_chain, font_size, render_mode="smooth",
                       threshold=128, sharpness=1.5, bold=False, outline=False,
                       padding_top=0, padding_bottom=0, padding_left=0, padding_right=0,
                       supersample=2, proportional=False):
    """按 ttf_chain 顺序渲染，返回首个有内容的字形；空格直接渲染返回。
    优化：先快速探测(getmask)哪个 TTF 含该字，只对首个有字 TTF 做完整渲染，
    避免对每个字符都完整渲染整条 chain（对大字符集提速显著）。
    proportional=True 时(Latin 区)用 fontTools 取字形真实 advance，做变宽左对齐打包，
    使拉丁文字距比例正确（不再等宽拉伸）。"""
    ss = supersample if (render_mode == "smooth" and supersample > 1) else 1
    rs = int(round(font_size * ss))
    lat_vm = (latin_glyph_metrics(ttf_chain[0], font_size) if proportional else None)
    if char in SPACE_CHARS:
        adv_px, xmin = (glyph_advance_px(ttf_chain[0], char, font_size)
                        if proportional else (None, None))
        return render_glyph_rgba(char, ttf_chain[0], font_size, render_mode,
                                 threshold, sharpness, bold, outline,
                                 padding_top, padding_bottom, padding_left,
                                 padding_right, supersample,
                                 advance_px=adv_px, glyph_xmin_px=xmin,
                                 latin_vmetrics=lat_vm)
    chosen = None
    for fp in ttf_chain:
        try:
            font = load_font(fp, rs)
        except Exception as e:
            print(f"      ⚠ 字体加载失败 {os.path.basename(fp)}：{e}")
            continue
        if _font_has_glyph(font, char):
            chosen = fp
            break
    if chosen is None:
        return (None, 0, 0)
    adv_px, xmin = (glyph_advance_px(chosen, char, font_size)
                    if proportional else (None, None))
    try:
        return render_glyph_rgba(char, chosen, font_size, render_mode,
                                 threshold, sharpness, bold, outline,
                                 padding_top, padding_bottom, padding_left,
                                 padding_right, supersample,
                                 advance_px=adv_px, glyph_xmin_px=xmin,
                                 latin_vmetrics=lat_vm)
    except Exception as e:
        print(f"      ⚠ TTF 渲染异常 {os.path.basename(chosen)}：{e}")
        return (None, 0, 0)


def write_tuv_scratch(path, char_list, coords, w, h, zero_space_width=False,
                      space_advance=None):
    """写 TUV：TUVCOUNT=len(char_list)，首字符=配置中的 start_code（默认 0x20）。
    行序号即字符编号：第 i 行对应 start_code + i。

    ★ 三个与「空格槽 slot0」有关的参数，语义不同、勿混淆：

    1) ``zero_space_width``（追加模式旧参数）
       把空格槽的 x2 收成 x1（矩形零宽）但 **x0 不动** → 步进不变。
       这时空格不画墨迹，但引擎照旧前进原格宽。本模式默认 False。

    2) ``space_advance``（推荐，2026-09-10 新增）
       令 ``slot0.x0 = slot1.x0 − space_advance``，同时矩形收成零宽。
       引擎「每字符步进 = 下一槽 x0 − 本槽 x0」，所以这才真正把**空格宽度**
       压到 space_advance px。
       ⇒ 补空格修复（fix_space_wrap.py 第 1 步）之后，字典里汉字背后都有一个
          ASCII 空格当断行点；若不压窄，界面会变成「学 习 治 理」的大间距。
       矩形宽不影响绘制（空格本无墨迹；字符宽度取自文本对象虚函数，不是 TUV），
       故零宽安全 —— 已实机验证「效果极好」。默认 None = 不压（保持自然格宽）。

    3) ``ZERO_INDEX = 223``（字符 0xFF = ÿ）**恒定**写成 0 0 0 0 零尺寸。
       引擎在绘制每个中文（2 字节 GBK）字符前会先画一个 0xFF 前置标记；
       原版中文字库正是把该槽留空来隐藏它。若留成真实字形，每个中文前都会
       显式露出一个可见的 ÿ/图标框。
    """
    ZERO_INDEX = 223  # 0xFF = ÿ：引擎 CJK 前置标记槽，必须零尺寸
    with open(path, "w", encoding="utf-8") as f:
        f.write("TUVTXT\n")
        f.write(f"TUVCOUNT {len(char_list)}\n")
        f.write(f"TUVBASE {w} {h}\n")
        for idx, (x1, y1, x2, y2) in enumerate(coords):
            if idx == ZERO_INDEX:
                f.write("0\t0\t0\t0\n")
                continue
            if idx == 0 and space_advance is not None and len(coords) > 1:
                # 空格槽：x0 前移到「下一槽 x0 − space_advance」，矩形同步收成零宽
                s1x = coords[1][0]
                nx = s1x - space_advance
                f.write(f"{nx}\t{y1}\t{nx}\t{y2}\n")
                continue
            if zero_space_width and idx < len(char_list) and char_list[idx] in SPACE_CHARS:
                f.write(f"{x1}\t{y1}\t{x1}\t{y2}\n")
            else:
                f.write(f"{x1}\t{y1}\t{x2}\t{y2}\n")


def pack_atlas_rgba(glyph_list, atlas_width=2048, atlas_height=2048, padding=1):
    """RGBA 货架打包：把字形逐个贴进 atlas_width×atlas_height 画布，返回画布与坐标。
    任何维度都不会超过 MAX_ATLAS_DIM（游戏上限 4096）。"""
    coord_list = []
    atlas = Image.new("RGBA", (atlas_width, atlas_height), (0, 0, 0, 0))
    cx, cy, row_max_h = 0, 0, 0
    dropped = 0
    for _, glyph, w, h in glyph_list:
        if glyph is None:
            coord_list.append((0, 0, 0, 0))
            continue
        if cx + w > atlas_width:
            cx = 0
            cy += row_max_h + padding
            row_max_h = 0
            if cy + h > atlas.height:
                nh = atlas.height * 2
                while nh < cy + h:
                    nh *= 2
                # 游戏硬上限：任何维度不得超过 MAX_ATLAS_DIM
                if nh > MAX_ATLAS_DIM:
                    nh = MAX_ATLAS_DIM
                nc = Image.new("RGBA", (atlas_width, nh), (0, 0, 0, 0))
                nc.paste(atlas, (0, 0))
                atlas = nc
        # 超出上限 → 写空槽，不 paste
        if cy + h > MAX_ATLAS_DIM or cx + w > atlas_width:
            coord_list.append((0, 0, 0, 0))
            cx += w + padding
            row_max_h = max(row_max_h, h)
            dropped += 1
            continue
        box = (cx, cy, cx + w, cy + h)
        # 直接按 RGBA 拷贝（不带 mask）：避免 PIL 把白字按 alpha 预乘到透明黑底
        # 产生灰边（‘白色不纯’）。字形包围盒以 padding 分隔，互不重叠，安全。
        atlas.paste(glyph, box)
        coord_list.append(box)
        cx += w + padding
        row_max_h = max(row_max_h, h)
    if dropped:
        print(f"      ⚠ 有 {dropped} 个字形因超出 {MAX_ATLAS_DIM} 上限被丢弃（写空槽）")
    return atlas, coord_list


def read_charlist_bytes(path):
    """读取 GB18030 字节字表（每 2 字节一个 GBK/GB18030 码，由 gen_full_gb18030.py 产出），
    解码为 Unicode 字符列表。这是「字表驱动」模式的中文源。"""
    with open(path, "rb") as f:
        data = f.read()
    chars = []
    i, n = 0, len(data)
    while i + 1 < n:
        b0, b1 = data[i], data[i + 1]
        try:
            ch = bytes([b0, b1]).decode("gb18030")
        except Exception:
            ch = ""
        if ch and len(ch) == 1:
            chars.append(ch)
        i += 2
    return chars


def read_gb18030_used(path):
    """读取 GB18030 编码的 txt（游戏里实际出现的全部文字），返回去重后的字符集合。
    用于「只渲染用到的字」以大幅压缩贴图：出现在集合中的汉字才渲染进 DDS，
    其余汉字保留 TUV 槽位但坐标写 0 0 0 0（引擎画空）。"""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("gb18030")
    except Exception:
        text = raw.decode("gb18030", "ignore")
    if text.startswith("\ufeff"):           # 剥离可能混入的 UTF-8 BOM
        text = text[1:]
    skip = set("\r\n\t\x0c\x00\x0b\x08")
    return set(c for c in text if c not in skip)


def read_dll_charlist(dll_cpp):
    """从 DLL 源 dllmain.cpp 的 g_charlist_data[] 解析 GBK WORD 列表（去掉末尾 0x0000 终结符），
    逐字解码为字符。贴图第 224+k 槽 = 此列表第 k 个字，与引擎 sub_700036A0 的
    slot = (dx 在 g_charlist_data 中的下标) + 224 一一对应，从而贴图与 DLL 同源同序。"""
    src = open(dll_cpp, encoding="utf-8", errors="ignore").read()
    m = re.search(r"g_charlist_data\[\]\s*=\s*\{(.*?)\};", src, re.S)
    if not m:
        raise RuntimeError(f"在 {dll_cpp} 找不到 g_charlist_data[]")
    body = m.group(1)
    words = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{4})", body) if int(x, 16) != 0]
    chars = []
    for w in words:
        # 小端：WORD = (次字节<<8)|首字节，与引擎 sub_700036A0 构造 dx=(al<<8)|cl 一致。
        # 若按大端解码，每个字都会画成「两字节互换后的另一个汉字」→ 正常但错位的乱码。
        b = bytes([w & 0xFF, (w >> 8) & 0xFF])
        try:
            ch = b.decode("gbk")
        except Exception:
            ch = ""
        chars.append(ch)
    return chars, words


def _next_pow2(x):
    p = 1
    while p < x:
        p <<= 1
    return p


def _compute_atlas_dims(n_glyphs, cell, width0, height0, max_dim=MAX_ATLAS_DIM):
    """根据字形总数与单元尺寸，自动选一块够大的 2 的幂画布（行优先货架打包）。
    任何维度（宽/高）都不会超过 max_dim（游戏上限 4096）。"""
    W = max(1, int(width0))
    if W > max_dim:
        print(f"  ⚠ 起始画布宽 {W} 超过游戏上限 {max_dim}，已强制钳制")
        W = max_dim
    while True:
        cols = max(1, W // cell)
        rows = math.ceil(n_glyphs / cols) if n_glyphs > 0 else 0
        need_h = rows * cell
        if need_h <= max_dim:
            break
        if W >= max_dim:
            break
        W = min(W * 2, max_dim)
    # 在最终 W 下重新计算所需高度
    cols = max(1, W // cell)
    rows = math.ceil(n_glyphs / cols) if n_glyphs > 0 else 0
    need_h = rows * cell
    init_h = _next_pow2(max(need_h, height0, 64))
    if init_h > max_dim:
        init_h = max_dim
    if need_h > max_dim:
        print(f"  ⚠ 图集空间不足：{n_glyphs} 个字形 @ {cell}px 需要高 {need_h}px，"
              f"已钳制到上限 {max_dim}px；超出部分字形将被裁切（写空槽）")
    return W, init_h


def _default_dds_header(w, h):
    """构造未压缩 32 位 BGRA 的 DDS 头（无 mip、无压缩）。"""
    hdr = bytearray(128)
    struct.pack_into("<I", hdr, 0, 0x20534444)   # 'DDS '
    struct.pack_into("<I", hdr, 4, 124)          # header size
    struct.pack_into("<I", hdr, 8, 0x00001007)   # flags: CAPS|HEIGHT|WIDTH|PIXELFORMAT
    struct.pack_into("<I", hdr, 12, h)
    struct.pack_into("<I", hdr, 16, w)
    struct.pack_into("<I", hdr, 20, w * 4)       # pitch
    struct.pack_into("<I", hdr, 28, 1)           # depth
    struct.pack_into("<I", hdr, 76, 32)          # pf size
    struct.pack_into("<I", hdr, 80, 0x41)        # pf flags: ALPHAPIXELS|RGB
    struct.pack_into("<I", hdr, 88, 32)          # RGBBitCount
    struct.pack_into("<I", hdr, 92, 0x00FF0000)  # R mask
    struct.pack_into("<I", hdr, 96, 0x0000FF00)  # G mask
    struct.pack_into("<I", hdr, 100, 0x000000FF) # B mask
    struct.pack_into("<I", hdr, 104, 0xFF000000) # A mask
    struct.pack_into("<I", hdr, 108, 0x1000)     # caps: TEXTURE
    return bytes(hdr)


def build_from_scratch(g, fc):
    prefix = fc.get("out_prefix") or fc["prefix"]
    font_size = fc["size"]
    render_mode = fc["render_mode"]
    outline = fc.get("outline", False)
    bold = fc.get("bold", False)
    desc = ("描边" if outline else "") + ("加粗" if bold else "")
    if not desc:
        desc = "常规"

    # 特殊码（从原图抠取覆盖）
    special = set()
    for x in (fc.get("special_from_original") or []):
        special.add(int(x, 0) if isinstance(x, str) else int(x))
    special = sorted(special)

    print(f"\n===== 从零生成 [{prefix}]  字号={font_size}px  {desc}  "
          f"特殊码={[hex(c) for c in special] or '无'} =====")

    # TTF 叠加/回退链
    ttf_chain = list(fc.get("ttf_chain") or g.get("ttf_chain") or [])
    if not ttf_chain:
        ttf_chain = [r"C:/Windows/Fonts/simhei.ttf"]
    missing = [p for p in ttf_chain if not os.path.isfile(p)]
    if missing:
        print(f"  ✗ TTF 链缺失文件：{missing}")
        return False

    # 加载特殊码源图（按需）
    src_img = None
    src_coords = None
    if special:
        sd = fc.get("source_dds")
        st = fc.get("source_tuv")
        if not (sd and st and os.path.isfile(sd) and os.path.isfile(st)):
            print(f"  ⚠ 特殊码 {[hex(c) for c in special]} 需要 source_dds/source_tuv，"
                  f"但未配置或缺失；将改用 TTF 渲染这些码")
            special = []
        else:
            try:
                src_img = load_source_image(sd)
                _, src_coords = read_tuv(st)
                print(f"      ↳ 特殊码源：{os.path.basename(sd)}（{src_img.width}×{src_img.height}）")
            except Exception as e:
                print(f"  ⚠ 读取特殊码源失败：{e}；改用 TTF 渲染")
                src_img = None
                special = []

    # 起始/截止字符（可从 yaml 的全局或 per-font 配置；默认 0x20–0xFF，仅用于拉丁区/范围模式）
    def _to_int(v, default):
        if v is None:
            return default
        return int(v, 0) if isinstance(v, str) else int(v)
    start_code = _to_int(fc.get("start_code") or g.get("start_code"), 0x20)
    end_code   = _to_int(fc.get("end_code")   or g.get("end_code"),   0xFF)
    if start_code < 0x20:
        start_code = 0x20
    if end_code < start_code:
        end_code = start_code

    # 字表驱动模式：charlist_file 存在时，拉丁 0x20–0xFF(224) + 字表按序追加（覆盖 CJK 基本/扩展A/PUA 等）
    charlist_file = fc.get("charlist_file") or g.get("charlist_file")

    def _code_char(c):
        # <=0xFF 沿用 cp1252（与游戏文本编码一致）；>0xFF 直接取 Unicode 字符（汉字等）
        if c <= 0xFF:
            try:
                return bytes([c]).decode("cp1252", "replace")
            except Exception:
                return chr(c)
        return chr(c)

    LATIN_N = 224  # 0x20..0xFF
    is_charlist = bool(charlist_file and os.path.isfile(charlist_file))
    _dll_words = None

    if g.get("charlist_source") == "dll":
        # 贴图顺序完全由 DLL 的 g_charlist_data[] 决定（任何序都行，二者同源，
        # 物理上不可能错位）。这是彻底避免 GBK/Unicode 序混乱的唯一可靠方式。
        if not g.get("dll_cpp") or not os.path.isfile(g["dll_cpp"]):
            print(f"  ✗ charlist_source=dll 但 dll_cpp 缺失：{g.get('dll_cpp')}；回退字表文件模式")
            if is_charlist:
                cjk_chars = read_charlist_bytes(charlist_file)
                latin_chars = [_code_char(c) for c in range(0x20, 0x100)]
                all_char = latin_chars + cjk_chars
            else:
                all_char = [_code_char(c) for c in range(start_code, end_code + 1)]
        else:
            cjk_chars, _dll_words = read_dll_charlist(g["dll_cpp"])
            latin_chars = [_code_char(c) for c in range(0x20, 0x100)]
            all_char = latin_chars + cjk_chars
            print(f"      从 DLL 派生：拉丁 {LATIN_N} + g_charlist_data {len(cjk_chars)} "
                  f"= 共 {len(all_char)} 字")
            print(f"      DLL 首 6 字：{''.join(cjk_chars[:6])!r}")
    elif g.get("codepoint_grid"):
        # 码点网格（已弃用，保留以防回退）：拉丁 0x20–0xFF + Unicode 码点 grid 区间
        latin_chars = [_code_char(c) for c in range(0x20, 0x100)]
        grid_chars = [chr(cp) for cp in range(g["grid_start"], g["grid_end"] + 1)]
        all_char = latin_chars + grid_chars
        print(f"      码点网格模式：拉丁 {LATIN_N} + 码点 U+{g['grid_start']:04X}~U+{g['grid_end']:04X} "
              f"= 共 {len(all_char)} 字（槽 224 = U+{g['grid_start']:04X}）")
    elif is_charlist:
        cjk_chars = read_charlist_bytes(charlist_file)
        latin_chars = [_code_char(c) for c in range(0x20, 0x100)]
        all_char = latin_chars + cjk_chars
        print(f"      字表驱动模式：拉丁 {LATIN_N} + 字表 {len(cjk_chars)} = 共 {len(all_char)} 字")
        print(f"      字表源：{os.path.basename(charlist_file)}")
    else:
        if charlist_file:
            print(f"  ⚠ 配置了 charlist_file 但文件不存在：{charlist_file}；回退到 start..end 范围模式")
        all_char = [_code_char(c) for c in range(start_code, end_code + 1)]
        print(f"      范围模式：0x{start_code:02X} ~ 0x{end_code:02X}（共 {len(all_char)} 个）")

    n_chars = len(all_char)

    # ---- 字符过滤：只渲染「游戏实际用到的字」----
    used_txt = fc.get("used_chars_txt", "")
    filter_used = False
    used_set = None
    if used_txt:
        if not os.path.isfile(used_txt):
            # 🔴 配置指明了过滤字集却找不到：必须明确报错，禁止静默退回全量
            #    （否则会出现「以为过滤了、实际 23940 全字符集」的隐蔽失败）
            raise FileNotFoundError(
                f"[used_chars_txt] 配置指定了过滤字集文件，但找不到：\n"
                f"    解析路径 = {os.path.abspath(used_txt)}\n"
                f"    相对路径基于配置文件所在目录。请检查文件名/路径是否正确；\n"
                f"    若确实要渲染全量字库，请删除 yaml 中的 used_chars_txt 配置。")
        filter_used = True
        used_set = read_gb18030_used(used_txt)
        print(f"      字符过滤开启：used_chars_txt = {os.path.basename(used_txt)}"
              f"（去重用字 {len(used_set)} 个）")

    if n_chars > 4096 and not is_charlist and not filter_used:
        print(f"  ⚠ 字符数 {n_chars} 较大（>4096）。全量 BMP 渲染会生成超大贴图，"
              f"游戏很可能无法加载；中文正确做法是改用字表/追加模式只渲染实际出现的字。")

    glyph_list = []
    empty_codes = []
    filtered_count = 0
    for idx, ch in enumerate(all_char):
        # 仅拉丁区(前 224 个)有真实码点，用于特殊码判定；CJK 区只有槽位序号
        code = (0x20 + idx) if idx < LATIN_N else None
        # 字符过滤：仅渲染「实际用到」的汉字，其余写空槽（TUV 仍保留全量槽位对齐）
        if filter_used and idx >= LATIN_N and ch not in used_set:
            glyph_list.append((ch, None, 0, 0))
            filtered_count += 1
            continue
        if code is not None and code in special and src_img is not None and src_coords is not None:
            # 特殊码始终在原始 tuv 的 0x20 起坐标系里（src_coords 行号 = 0x20 + i）
            src_idx = code - 0x20
            if 0 <= src_idx < len(src_coords):
                parts = src_coords[src_idx].split()
                if len(parts) >= 4:
                    x1, y1, x2, y2 = [int(v) for v in parts[:4]]
                    if x2 - x1 > 0 and y2 - y1 > 0:
                        crop = src_img.crop((x1, y1, x2, y2)).convert("RGBA")
                        glyph_list.append((ch, crop, x2 - x1, y2 - y1))
                        continue
                    else:
                        print(f"  ⚠ 0x{code:02X} 在原图坐标为空，改用 TTF")
                else:
                    print(f"  ⚠ 0x{code:02X} 原图 tuv 坐标行不足，改用 TTF")
        img, w, h = render_glyph_chain(ch, ttf_chain, font_size, render_mode,
                                       fc["threshold"], fc["sharpness"], bold, outline,
                                       fc["padding_top"], fc["padding_bottom"],
                                       fc["padding_left"], fc["padding_right"], fc["supersample"],
                                       proportional=(idx < LATIN_N))
        if img is None:
            # 无字体含此字（如 PUA 私用区图标槽）→ 写空槽，不再画 .notdef 方框(X)
            empty_codes.append(code if code is not None else idx)
            glyph_list.append((ch, None, 0, 0))
        else:
            if not glyph_has_content(img) and code != 0x20:
                # 渲染出图但无可见像素（极少见）→ 同样空槽
                empty_codes.append(code if code is not None else idx)
                glyph_list.append((ch, None, 0, 0))
            else:
                glyph_list.append((ch, img, w, h))

    # 自动计算画布尺寸（行优先货架打包），避免小画布溢出或浪费空间。
    # 字符过滤时按「有效字形数」计算，并从 1024 起自适应（忽略 yaml 的 4096 固定值）。
    n_effective = sum(1 for (_, img, _, _) in glyph_list if img is not None)
    if filter_used:
        print(f"      有效字形 {n_effective} 个（全量 {n_chars}，因过滤写空槽 {filtered_count} 个）")
    cell = font_size + 2 * g["padding"] + 4 + (2 if outline else 0)
    if filter_used:
        start_w = start_h = 1024
    else:
        start_w, start_h = g["atlas_width"], g["atlas_height"]
    W, init_h = _compute_atlas_dims(n_effective, max(cell, 1), start_w, start_h)
    atlas, coords = pack_atlas_rgba(glyph_list, W, init_h, g["padding"])

    os.makedirs(g["output_dir"], exist_ok=True)
    tuv_name = fc.get("tuv_out") or prefix
    tuv_path = os.path.join(g["output_dir"], tuv_name + ".tuv")
    dds_path = os.path.join(g["output_dir"], prefix + ".dds")
    png_path = os.path.join(g["output_dir"], prefix + ".png")

    # 大 PNG 偶发被外部进程(杀软/索引)占用 → OSError(EINVAL)。
    # 先写临时文件再原子替换，最多重试 3 次，避免整套构建中断。
    tmp_png = png_path + ".tmp"
    last_err = None
    for _attempt in range(3):
        try:
            atlas.save(tmp_png, format="PNG")
            os.replace(tmp_png, png_path)
            last_err = None
            break
        except OSError as e:
            last_err = e
            try:
                if os.path.exists(tmp_png):
                    os.remove(tmp_png)
            except OSError:
                pass
            time.sleep(1.0)
    if last_err is not None:
        raise last_err
    print(f"      ↳ PNG: {png_path}（{atlas.width}×{atlas.height}）")

    out_fmt = str(fc.get("output_format") or g.get("output_format") or "dxt5").lower()
    if out_fmt == "bgra":
        save_bgra_dds(dds_path, atlas, _default_dds_header(atlas.width, atlas.height))
        print(f"      ↳ DDS: {dds_path}（BGRA 32 位）")
    else:
        tc = find_texconv(g["texconv"])
        if not tc:
            print(f"  ✗ 未找到 texconv.exe，无法编码 DXT5（可配置 output_format: bgra）")
            return False
        texconv_encode(png_path, g["output_dir"], "BC3_UNORM", tc)
        print(f"      ↳ DDS: {dds_path}（BC3/DXT5）")

    write_tuv_scratch(tuv_path, all_char, coords, atlas.width, atlas.height,
                      fc["zero_space_width"], fc.get("space_advance"))

    # 自检
    if not is_charlist and len(all_char) != (end_code - start_code + 1):
        print(f"  ⚠ 自检：字符数 {len(all_char)} 与范围 0x{start_code:02X}~0x{end_code:02X} 不符")
    for code in special:
        x1, y1, x2, y2 = coords[code - start_code]
        if x2 - x1 == 0 or y2 - y1 == 0:
            print(f"  ⚠ 自检失败：特殊码 0x{code:02X} 坐标为零（未抠到）")
    if (is_charlist or g.get("codepoint_grid")) and empty_codes:
        print(f"     空槽(无字形/缺失码点)数：{len(empty_codes)} —— 这些写空槽，不会显示方框")

    # 自检（dll 派生模式）：贴图 CJK 槽 224+k 的字符必须 == decode(g_charlist_data[k])。
    # 由于 cjk_chars 本就由 dll_words 解码而来，正常必全过；此检查防止打包管线意外重排。
    if _dll_words is not None:
        bad = 0
        for k, w in enumerate(_dll_words):
            if LATIN_N + k >= len(all_char):
                break
            try:
                exp = bytes([w & 0xFF, (w >> 8) & 0xFF]).decode("gbk")
            except Exception:
                exp = ""
            got = all_char[LATIN_N + k]
            if exp != got:
                bad += 1
                if bad <= 10:
                    print(f"  ⚠ 自检错位 slot {224 + k}: 期望 {exp!r} 实际 {got!r}")
        if bad == 0:
            print(f"  ✅ 自检通过：贴图 CJK 区顺序 == dllmain.cpp g_charlist_data[] 顺序（{len(_dll_words)} 项）")
        else:
            print(f"  ✗ 自检失败：{bad} 处贴图与 DLL 顺序不符！")
    print(f"  ✅ [{prefix}]  字符 {len(all_char)}，特殊码已处理：{[hex(c) for c in special] or '无'}")
    if empty_codes:
        print(f"     空字形/走回退的码点：{[hex(c) for c in empty_codes]}")
    return True


# ---------------------------------------------------------------------------
# 旧版：单套字体构建
# ---------------------------------------------------------------------------
def build_one(g, fc):
    font_path = fc["font_path"]
    font_size = fc["size"]
    render_mode = fc["render_mode"]
    print(f"\n===== 生成 [{fc['prefix']}]  字体={os.path.basename(font_path)}  字号={font_size}px  "
          f"模式={'平滑' if render_mode=='smooth' else '二值/阈值'+str(fc['threshold'])} =====")

    if not os.path.isfile(font_path):
        print(f"  ✗ 字体文件不存在：{font_path}")
        return

    all_char = []
    for code in range(0x20, 0x100):
        try:
            all_char.append(bytes([code]).decode("cp1252"))
        except Exception:
            all_char.append("\uFFFD")
    ascii_total = len(all_char)

    if not os.path.exists(g["charlist"]):
        print(f"  ✗ 找不到 charlist 文件：{g['charlist']}")
        return
    try:
        cn_chars = read_charlist(g["charlist"])
    except Exception:
        print(f"  ✗ {g['charlist']} 不是有效的文本文件")
        return
    all_char.extend(cn_chars)

    glyph_cache = []
    for idx, ch in enumerate(all_char):
        glyph, w, h = render_glyph(
            ch, font_path, font_size, render_mode,
            fc["threshold"], fc["sharpness"], fc["bold"],
            fc["padding_top"], fc["padding_bottom"],
            fc["padding_left"], fc["padding_right"], fc["supersample"])
        glyph_cache.append((ch, glyph, w, h))

    atlas, coords, _ = pack_atlas(glyph_cache, g["atlas_width"], g["padding"])

    patch = fc.get("patch_png") or ""
    if not (patch and os.path.exists(patch)):
        for d in (g.get("_cfg_dir"), os.path.dirname(os.path.abspath(__file__))):
            if d and os.path.isfile(os.path.join(d, "$.png")):
                patch = os.path.join(d, "$.png")
                break
    if patch and os.path.exists(patch):
        if fc["padding_top"] == fc["padding_bottom"] == fc["padding_left"] == fc["padding_right"]:
            atlas = apply_png_patch(atlas, coords, 4, patch)
        else:
            print("[补丁] 跳过：四向边距不一致（补丁要求上下左右相等）")

    if atlas.mode != 'RGBA':
        rgba = Image.new("RGBA", atlas.size, (0, 0, 0, 0))
        rgba.putalpha(atlas)
        white = Image.new("RGB", atlas.size, (255, 255, 255))
        rgba.paste(white, (0, 0), atlas)
        atlas = rgba

    os.makedirs(g["output_dir"], exist_ok=True)
    png_path = os.path.join(g["output_dir"], fc["prefix"] + ".png")
    atlas.save(png_path, format="PNG")

    if fc.get("auto_dds", True):
        tc = find_texconv(g["texconv"])
        if tc:
            convert_png_to_dds(png_path, tc, g["output_dir"])
        else:
            print("[DDS] ⚠️ 未找到 texconv.exe，跳过 DDS（可在配置 texconv 指定路径）")

    tuv_path = os.path.join(g["output_dir"], fc["prefix"] + ".tuv")
    write_tuv_onepass(tuv_path, all_char, atlas.width, atlas.height, coords,
                      fc["zero_space_width"])

    print(f"  ✅ [{fc['prefix']}]  {png_path}（{atlas.width}×{atlas.height}）")
    print(f"     {tuv_path}（字符 {len(all_char)}，中文起始索引 {ascii_total}）")

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "font_config.yaml")
    if not os.path.exists(cfg_path):
        print(f"[配置] 找不到配置文件：{cfg_path}")
        print("      用法： python build_font_atlas.py <配置.yaml|json>")
        sys.exit(1)

    cfg = load_config(cfg_path)
    has_append = any(fc.get("mode") == "append" for fc in cfg["fonts"])
    if has_append:
        ensure_charlist(cfg)
    else:
        print("[配置] 无 append 模式字体，跳过 charlist/DictRead 读取（符合「不再从这两者读取字」）")
    print("=" * 64)
    print(" TUV 字体图集生成器（数据驱动 · 追加模式）")
    print(" 配置文件：", os.path.abspath(cfg_path))
    print(" 输出目录：", os.path.abspath(cfg["output_dir"]))
    print(" 字符库   ：", os.path.abspath(cfg["charlist"]))
    print(" 字体套数 ：", len(cfg["fonts"]))
    print(f" 尺寸上限 ： {MAX_ATLAS_DIM}×{MAX_ATLAS_DIM}")
    print("=" * 64)

    ok = active = skipped = 0
    for fc in cfg["fonts"]:
        if not fc.get("enabled", True):
            name = fc.get("out_prefix") or fc["prefix"]
            print(f"\n──── 跳过（enabled:false）：[{name}]")
            skipped += 1
            continue
        active += 1
        mode = str(fc.get("mode", "from_scratch")).lower()
        if mode == "append":
            done = build_append(cfg, fc)
        elif mode == "one":
            done = (build_one(cfg, fc) or True)
        else:
            done = (build_from_scratch(cfg, fc) or True)
        ok += 1 if done else 0

    print(f"\n✅ 处理完成：启用 {active} 套（跳过 {skipped} 套），成功 {ok} 套。")

if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(f"\n程序异常：{err}")
        import traceback
        traceback.print_exc()
        sys.exit(1)