# -*- coding: utf-8 -*-
# 诊断：NEW/OLD 字典里 CJK 之间的空格风格（compact vs spaced）
# 字典格式：'#KEY' 独立一行，下一行是 value
import re

PATHS = {
    'NEW': r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\DictRead.txt',
    'OLD': r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\DictRead_V2.txt',
}

def load(p):
    txt = open(p, 'rb').read().decode('gbk', errors='replace')
    lines = txt.splitlines()
    d = {}
    order = []
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].lstrip('\ufeff').strip()
        if s.startswith('#'):
            key = s[1:].strip()
            # 收集后续直到下一个 '#' 开头或连续空行
            j = i + 1
            while j < n and not lines[j].lstrip('\ufeff').strip().startswith('#'):
                j += 1
            val = '\n'.join(lines[i+1:j]).strip('\n')
            if key and key not in d:
                order.append(key)
            if key:
                d[key] = val
            i = j
        else:
            i += 1
    return d, order, lines

def iscjk(c):
    return '\u3400' <= c <= '\u9fff'

def stat(v):
    # 去掉 <font ...> 标签后再统计
    v = re.sub(r'<[^>]*>', '', v)
    n = sum(1 for c in v if iscjk(c))
    s = sum(1 for i, c in enumerate(v[:-1]) if iscjk(c) and v[i+1] == ' ')
    return n, s

def show(tag, d, lines):
    print('=' * 74)
    print(tag, ' entries =', len(d))
    spaced = compact = mixed = other = 0
    for k, v in d.items():
        n, s = stat(v)
        if n == 0:
            other += 1; continue
        r = s / n
        if r >= 0.8:   spaced += 1
        elif r <= 0.2: compact += 1
        else:          mixed += 1
    print('--- 全局风格 (CJK 字符后跟空格的比例) ---')
    print('   纯空格风格 r>=0.8 :', spaced)
    print('   紧凑        r<=0.2 :', compact)
    print('   混合        其它   :', mixed)
    print('   无 CJK             :', other)
    print('--- 关键字命中 (含 TUTORIAL / EXITCONFIRM) ---')
    hits = [k for k in d if re.search(r'TUTORIAL|EXITCONFIRM', k, re.I)]
    for k in hits:
        v = d[k]; n, s = stat(v)
        print('   #%s  n=%d s=%d  %s' % (k, n, s, repr(v)[:180]))
    print('--- 含“学习治理王国”或“任务目标”的条目 ---')
    for k, v in d.items():
        if '学习治理王国' in v or '任务目标' in v or '学 习 治 理' in v:
            n, s = stat(v)
            print('   #%s n=%d s=%d  %s' % (k, n, s, repr(v)[:220]))

for tag, p in PATHS.items():
    try:
        d, order, lines = load(p)
    except Exception as e:
        print(tag, 'LOAD FAIL', e); continue
    show(tag, d, lines)
