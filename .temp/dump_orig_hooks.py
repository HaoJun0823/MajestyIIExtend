# -*- coding: utf-8 -*-
p = r'I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\线索2\源码\MJ2_fontfix\MJ2_fontfix.cpp'
t = open(p, encoding='gbk').read()
lines = t.splitlines()
for i in range(940, 1045):
    if i < len(lines):
        print(f'{i+1}: {lines[i]}')