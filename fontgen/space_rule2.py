# -*- coding: utf-8 -*-
"""标签感知的空格规则验证 + 应用。
规则：在文本区(不在 <...> 标签内)每个 CJK 汉字后插入一个空格。
验证：compact(V2) 再 respace() 应能还原 V2。"""
import re, sys

CJK = re.compile(r'[\u4e00-\u9fff]')
TAG = re.compile(r'<[^>]*>')

def load(p):
    raw = open(p, 'rb').read()
    txt = raw.decode('gbk', errors='replace')
    lines = txt.splitlines(keepends=True)
    d, order = {}, []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].lstrip('\ufeff').strip()
        if s.startswith('#'):
            key = s[1:].strip()
            j = i + 1
            while j < n and not lines[j].lstrip('\ufeff').strip().startswith('#'):
                j += 1
            val = ''.join(lines[i+1:j]).strip('\n')
            if key and key not in d:
                order.append(key)
            if key:
                d[key] = val
            i = j
        else:
            i += 1
    return d, order

def _iter_text_spans(v):
    """产出 (start,end) —— 非标签区域。"""
    pos = 0
    spans = []
    for m in TAG.finditer(v):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(v):
        spans.append((pos, len(v)))
    return spans

def compact(v):
    """去掉 CJK 后紧跟的空格（仅文本区）。"""
    out = list(v)
    for s, e in _iter_text_spans(v):
        for i in range(s, e - 1):
            if out[i] == ' ' and CJK.match(out[i-1] if i > 0 else ''):
                out[i] = ''
    return ''.join(out)

def respace(v):
    """文本区每个 CJK 汉字后插一个空格（已跟空格则不重复）。"""
    res = []
    for s, e in _iter_text_spans(v):
        pass
    # 逐字符构建
    out = []
    n = len(v)
    in_tag = False
    for i, ch in enumerate(v):
        if ch == '<':
            in_tag = True
        if ch == '>':
            in_tag = False
            out.append(ch); continue
        out.append(ch)
        if not in_tag and CJK.match(ch):
            nxt = v[i+1] if i+1 < n else ''
            if nxt != ' ':
                out.append(' ')
    return ''.join(out)

V2 = r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\DictRead_V2.txt'
d2, _ = load(V2)
bad = 0
samples = []
for k, v in d2.items():
    got = respace(compact(v))
    if got != v:
        bad += 1
        if len(samples) < 6:
            samples.append((k, v, got, compact(v)))
print("=== 往返不一致条目: %d / %d ===" % (bad, len(d2)))
for k, v, g, c in samples:
    print("  #%s" % k)
    print("    V2    =%r" % v[:130])
    print("    compact=%r" % c[:130])
    print("    respace=%r" % g[:130])
