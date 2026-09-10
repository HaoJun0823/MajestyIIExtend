# -*- coding: utf-8 -*-
"""把 compact 字典重新插入「汉字后空格」（零宽断行符），复刻老字典 V2 的断行行为。
逐行处理原始字节解码后的文本，保留原有的键行/值行结构与换行符。"""
import re, sys, os, shutil

CJK = re.compile(r'[\u4e00-\u9fff]')

def respace_line(v):
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
            nxt = v[i+1] if i + 1 < n else ''
            if nxt != ' ':
                out.append(' ')
    return ''.join(out)

def main(src, dst):
    raw = open(src, 'rb').read()
    print("size:", len(raw), "BOM:", raw[:3] == b'\xef\xbb\xbf')
    txt = raw.decode('gbk', errors='replace')
    print("CRLF count:", txt.count('\r\n'), " lone-LF:", txt.count('\n') - txt.count('\r\n'))
    lines = txt.splitlines(keepends=True)
    print("first 12 lines repr:")
    for l in lines[:12]:
        print("   ", repr(l))
    out_lines = []
    changed = 0
    inserted = 0
    for l in lines:
        core = l.lstrip('\ufeff')
        if core.lstrip().startswith('#'):
            out_lines.append(l)
            continue
        body = l.rstrip('\r\n')
        eol = l[len(body):]
        new = respace_line(body)
        if new != body:
            changed += 1
            inserted += new.count(' ') - body.count(' ')
        out_lines.append(new + eol)
    out_txt = ''.join(out_lines)
    data = out_txt.encode('gbk')
    open(dst, 'wb').write(data)
    print("changed lines:", changed, " inserted spaces:", inserted)
    print("new size:", len(data))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
