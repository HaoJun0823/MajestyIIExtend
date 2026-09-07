# -*- coding: utf-8 -*-
import re

# Read charlist data
with open(r'G:\Projects\MajestyIIExtend\MajestyII_UTF8\charlist_data.h', 'r') as f:
    content = f.read()

# Extract all hex values
values = re.findall(r'0x([0-9A-Fa-f]{4})', content)
charlist = set()
for v in values:
    charlist.add(int(v, 16))

print('Charlist entries: %d' % len(charlist))

# Test: state machine produces (trail << 8) | lead = reversed GBK
# For GBK B9FA (国): lead=B9, trail=FA, reversed = (FA << 8) | B9 = 0xFAB9
tests = {
    '。': (0xA1, 0xA3),
    '啊': (0xB0, 0xA1),
    '国': (0xB9, 0xFA),
    '战': (0xD5, 0xBD),
    '中': (0xD6, 0xD0),
    '文': (0xCE, 0xC4),
}

print()
print('Testing state machine combo (trail<<8|lead) vs charlist:')
for ch, (lead, trail) in tests.items():
    standard = (lead << 8) | trail
    reversed_fmt = (trail << 8) | lead
    in_standard = 'YES' if standard in charlist else 'NO'
    in_reversed = 'YES' if reversed_fmt in charlist else 'NO'
    print('  %s (GBK %02X%02X): standard=0x%04X(%s) reversed=0x%04X(%s)' % (
        ch, lead, trail, standard, in_standard, reversed_fmt, in_reversed))

print()
count_standard = sum(1 for _, (l, t) in tests.items() if ((l<<8)|t) in charlist)
count_reversed = sum(1 for _, (l, t) in tests.items() if ((t<<8)|l) in charlist)
print('Standard format matches: %d/%d' % (count_standard, len(tests)))
print('Reversed format matches: %d/%d' % (count_reversed, len(tests)))
