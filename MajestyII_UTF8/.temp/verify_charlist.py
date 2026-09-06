# -*- coding: utf-8 -*-
import sys, hashlib

def sha1(p):
    with open(p, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()

def find_charlist(data):
    head = bytes([0x02, 0x30, 0x1C, 0x20, 0x1D, 0x20, 0x14, 0x30, 0x15, 0x30, 0x08, 0x30, 0x09, 0x30, 0x0A, 0x30])
    return data.find(head)

def count_entries(data, idx):
    n = 0
    i = idx
    while i + 1 < len(data):
        v = data[i] | (data[i+1] << 8)
        if v == 0:
            break
        n += 1
        i += 2
    return n

def read_cp(data, idx, n):
    return [data[idx+k*2] | (data[idx+k*2+1] << 8) for k in range(n)]

for p in sys.argv[1:]:
    data = open(p, "rb").read()
    idx = find_charlist(data)
    if idx < 0:
        print(f"[{p}] NOT FOUND")
        continue
    n = count_entries(data, idx)
    h8 = [hex(x) for x in read_cp(data, idx, 8)]
    tail = hex(data[idx+(n-1)*2] | (data[idx+(n-1)*2+1] << 8))
    print(f"[{p}] size={len(data)} sha1={sha1(p)[:12]} off=0x{idx:X} count={n} head8={h8} tail={tail}")
