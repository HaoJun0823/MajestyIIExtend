#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计当前翻译状态：词典规模、未翻译清单规模"""
import json
import os

base = r"I:\SteamLibrary\steamapps\common\Majesty HD\workspace\tools"

for fn in ["untranslated.json", "untranslated_full.json", "untranslated_full2.json",
           "untranslated_categorized.json", "round3_translations.json",
           "round4_translations.json", "round5_translations.py",
           "supplement_translations.json"]:
    p = os.path.join(base, fn)
    if not os.path.exists(p):
        print(f"{fn}: MISSING")
        continue
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            if 'exact' in data and 'templates' in data:
                print(f"{fn}: exact={len(data['exact'])} templates={len(data['templates'])}")
            elif fn == 'untranslated_categorized.json':
                total = sum(len(v) for v in data.values())
                cats = {k: len(v) for k, v in sorted(data.items(), key=lambda x: -len(x[1]))}
                print(f"{fn}: categories={len(data)} total_entries={total}")
                for k, v in cats.items():
                    print(f"    {k}: {v}")
            else:
                print(f"{fn}: {len(data)} entries")
        else:
            print(f"{fn}: {len(data)} entries (list)")
    except Exception as e:
        print(f"{fn}: ERROR {e}")