#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Precise stack offset calculation for texts() hook at 0x775939.

At hook point 0x775939:
  ESP = ESP_after_prologue (frame base = 0x00 offset)
  [ESP + 0x58] = arg_4 = a2 (the key string)
  
But wait - is this really arg_4 or a2?

IDA stack frame:
  __return_address at 0x50
  arg_0 at 0x54  (this is the first STACK argument after return address)
  arg_4 at 0x58  (second stack argument)
  arg_8 at 0x5C  (third stack argument)

For __thiscall: 'this' in ECX, so stack args are:
  [esp+0x54] = arg_0 = first stack arg = a2 (the key)  [No! IDA's arg_0 might be 'this']

Actually, let me check the instruction at 77552a:
  77552a: mov esi, [esp+50h+arg_4]
  
This loads ESI with arg_4. And the decompiled code says:
  v12 = (char *)a2;  // at 7755c8
  v13 = (char *)&loc_5A7244 + (_DWORD)this;  // at 7755ce
  
At 77552a (early in function), ESI is loaded from [esp+50h+arg_4]
Then at 77552e: cmp esi, 1 (comparing a2/key length to 1)
So ESI = a2 = key at that point.

Wait, but at 77552a: mov esi, [esp+50h+arg_4]
The decompiled code parameter mapping:
  this = ECX (thiscall)
  a2 = first stack arg = arg_0 at 0x54
  a3 = second stack arg = arg_4 at 0x58  
  a4 = third stack arg = arg_8 at 0x5C

But 77552a loads ESI from arg_4 (0x58) and compares to 1...
The decompiled code says:
  v12 = (char *)a2;
  if ( strlen(a2) != a3 )
  
And earlier: cmp esi, 1 where esi = [esp+arg_4]
This checks if a3 (length) > 1, which matches: if (a3 <= 1) { assert }

So: arg_4 at 0x58 = a3 (length, unsigned int)
And: arg_0 at 0x54 = a2 (key, const char*)

Wait no. Let me re-read:
  77552a: mov esi, [esp+50h+arg_4]  -- esi = [esp+0x58]
  77552e: cmp esi, 1                -- compare to 1
  775531: mov ebp, ecx              -- ebp = this
  775533: mov [esp+50h+var_48], ebp -- save this
  775537: ja loc_7755C6             -- if esi > 1, go to main path

Decompiled: if ( a3 <= 1 ) { assert("len > 1") }
So esi = a3 (length), and a3 is at [esp+0x58] = arg_4.

That means:
  arg_0 at 0x54 = ??? (maybe 'this' saved by caller, or maybe it's a2)
  arg_4 at 0x58 = a3 (length)
  arg_8 at 0x5C = a4

But where is a2 (the key)?
In the decompiled code:
  v12 = (char *)a2;  at 7755c8
Let me check 7755c6-7755c8:
"""

# Let me check the instruction at 0x7755C6
print("Need to check disassembly at 0x7755C6 to find where a2 is loaded")
print()
print("=== Current analysis ===")
print(f"arg_0 at [esp+0x54] — unknown (maybe this or a2)")
print(f"arg_4 at [esp+0x58] = a3 (length, unsigned int) — confirmed by cmp esi,1")
print(f"arg_8 at [esp+0x5C] = a4")
print()
print(f"Since thiscall uses ECX for 'this':")
print(f"  Stack args: [ret_addr+4] = a2, [ret_addr+8] = a3, [ret_addr+12] = a4")
print(f"  = [esp+0x54] = a2 (key)")
print(f"  = [esp+0x58] = a3 (length)")
print(f"  = [esp+0x5C] = a4")
print()
print(f"But IDA shows arg_0 at 0x54 and arg_4 at 0x58.")
print(f"IDA's 'arg_0' is the first stack arg = a2 (key)")
print(f"IDA's 'arg_4' is the second stack arg = a3 (length)")
print(f"IDA's 'arg_8' is the third stack arg = a4")
print()
print(f"Wait, but 77552a loads from arg_4 (0x58) and compares to 1 for length check...")
print(f"So arg_4 = a3 = length. That means arg_0 = a2 = key.")
print()
print(f"--- texts() hook offset ---")
print(f"At hook point 0x775939: [ESP + 0x54] = a2 (key)")
print(f"In texts() after 4 pushes (0x10 bytes):")
print(f"  [ESP_text + 0x54 + 0x10] = [ESP_text + 0x64] = a2 (key)")
print(f"  But code uses [esp+0x24+16] = [esp+0x34] — WRONG")
print(f"  Correct: [esp+0x44+16] = [esp+0x54]? No...")
print()
print(f"Let me recalculate:")
print(f"  ESP_text = ESP_hook - 0x10 (after 4 pushes)")
print(f"  [ESP_text + X] = [ESP_hook - 0x10 + X]")
print(f"  To get [ESP_hook + 0x54] (key): X = 0x54 + 0x10 = 0x64")
print(f"  So correct: [esp + 0x64] or [esp + 0x54 + 16]")
print(f"  But code uses [esp + 0x24 + 16] = [esp + 0x34]")
print(f"  Off by 0x64 - 0x34 = 0x30 = 48 bytes!")
print()
print(f"Wait, but hook_debug.log shows HITs working...")
print(f"Maybe the hook IS working, and the crash is from something else?")
print(f"Or maybe the deployed ASI is different from the source code?")
