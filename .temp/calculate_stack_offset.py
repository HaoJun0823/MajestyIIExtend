#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calculate the correct stack offset for texts() hook.

Function sub_775510 prologue:
  775510: push -1              ; esp -= 4
  775512: push offset SEH      ; esp -= 4
  775517: mov eax, fs:0        ; (no stack change)
  77551d: push eax             ; esp -= 4  (saved fs:0)
  77551e: mov fs:0, esp        ; (no stack change)
  775525: sub esp, 3Ch         ; esp -= 0x3C
  775528: push ebp             ; esp -= 4
  775529: push esi             ; esp -= 4

Total stack from return address:
  4 (push -1) + 4 (SEH) + 4 (fs:0) + 0x3C + 4 (ebp) + 4 (esi) = 0x50

So at 775529+1 (after push esi):
  [esp+0x00] = esi (just pushed)
  [esp+0x04] = ebp
  [esp+0x08..0x44] = var_48..var_2C (0x3C bytes of local vars)
  [esp+0x44] = var_C = saved fs:0
  [esp+0x48] = SEH handler
  [esp+0x4C] = var_4 = -1 (push 0FFFFFFFFh)
  [esp+0x50] = return address
  [esp+0x54] = arg_0 (this, in ecx originally but passed on stack? No, thiscall)
  [esp+0x58] = arg_4 (a2 = key)
  [esp+0x5C] = arg_8 (a3 = len)

Wait, this is __thiscall, so 'this' is in ecx, not on stack.
The function signature is: char __thiscall sub_775510(char *this, const char *a2, unsigned int a3, int a4)
So stack args are: a2, a3, a4
    
  [esp+0x50] = return address
  [esp+0x54] = a2 (key, arg_4 in IDA)
  [esp+0x58] = a3 (len, arg_8 in IDA)
  [esp+0x5C] = a4 (arg_C in IDA? but IDA shows arg_8 at 0x5c)

Actually IDA's stack frame shows:
  __return_address at 0x50
  arg_0 at 0x54  --> this is a2 (first stack arg after return, since thiscall uses ecx)
  arg_4 at 0x58  --> this is a3
  arg_8 at 0x5c  --> this is a4

But IDA labeled them as arg_0, arg_4, arg_8 - these are RELATIVE offsets from frame base.
In absolute terms (from esp at function body):
  [esp+0x54] = a2 (the key string)
  [esp+0x58] = a3 (length)
  [esp+0x5C] = a4

Now, at hook point 0x775939, is esp the same as after prologue?
Let's check: between prologue and 0x775939, is there any push without corresponding pop?

Looking at the disassembly:
- 775542: push eax (endl)
- 775543: push offset aFailed
- 77554d: push offset aAssertex
- 775548: push offset aKeyIsTooShort  -- wait, that's wrong order
Actually looking more carefully at the assert path (77553d-77559d):
  Multiple pushes and calls to sub_401880, with add esp,8 after each pair
  This path has balanced stack.

At 7755C6 (loc_7755C6, the main path when len > 1):
  Need to check if stack is balanced there too.

The key question: at 0x775939, what is the esp offset to a2 (the key)?

If the function is well-formed, esp at 0x775939 should be the same as esp after prologue
(0x77552a), because all paths balance the stack.

So at 0x775939:
  [esp + 0x54] = a2 (key)
  But IDA stack frame says arg_4 is at offset 0x58...
  
Wait, IDA's stack frame offsets are from the FRAME BASE, not from ESP.
Let me re-read:
  __return_address is at offset 0x50
  arg_0 is at offset 0x54
  arg_4 is at offset 0x58

These look like offsets from ESP (after prologue), where ESP points to the top of the frame.
So:
  [esp + 0x50] = return address
  [esp + 0x54] = arg_0 = a2 (key)  <-- but IDA says "arg_4" at 0x58
  
Actually IDA naming: arg_0, arg_4, arg_8 are at 0x54, 0x58, 0x5C
  arg_0 = first argument (at [esp+0x54]) = a2 (key)
  arg_4 = second argument (at [esp+0x58]) = a3 (len)
  arg_8 = third argument (at [esp+0x5C]) = a4

Wait, but the function prototype says:
  char __thiscall sub_775510(char *this, const char *a2, unsigned int a3, int a4)
'this' is in ecx (thiscall), so stack args start with a2:
  [esp+0x54] = a2 = key  (IDA: arg_0)
  [esp+0x58] = a3 = len  (IDA: arg_4)
  [esp+0x5C] = a4        (IDA: arg_8)

Hmm, but IDA stack_frame shows:
  arg_0 at offset 0x54 with comment "this" 
  arg_4 at offset 0x58 with comment "arg1" (= a2)
  arg_8 at offset 0x5C with comment "arg2" (= a3)

So actually:
  [esp+0x54] = this (saved by caller? No, thiscall doesn't push this)
  
This is confusing. Let me check: __thiscall passes 'this' in ecx. 
But some compilers/decompilers show 'this' as arg_0 in the stack frame.

Let me check the actual instruction at 77552a:
  77552a: mov esi, [esp+50h+arg_4]
  
  esp+50h+arg_4 = esp + 0x50 + 0x08 = esp + 0x58? No.
  
Actually IDA's "esp+50h+arg_4" notation means:
  50h = stack frame size (0x50)
  arg_4 = offset 0x58 - 0x50 = 0x08
  
So: [esp + 0x50 + 0x08] = [esp + 0x58]
Wait that doesn't make sense either.

IDA notation: [esp+50h+arg_4] where 50h is the frame size and arg_4 is the arg offset.
The actual address is: [esp + arg_4] where arg_4 = 0x58 - 0x50 = 0x08
No, that's not right either.

The correct interpretation:
  "50h" in "[esp+50h+arg_4]" is the frame size used by IDA.
  The actual offset from ESP is: 50h + arg_4_offset_relative_to_frame
  
Actually I think IDA calculates:
  [esp + 50h + (arg_4 - 50h)] = [esp + arg_4]
  
No wait. In IDA, the stack frame offsets are absolute from the frame base (top of stack).
  var_48 at offset 0x08 means [ebp - 0x48 + 8]... no.

For ESP-based frames (no frame pointer), IDA uses:
  [esp + offset] where offset = stack_member_offset - current_esp_offset

But the stack frame listing shows absolute offsets from the bottom of the frame.
  __return_address at 0x50 means the return address is at frame_base + 0x50
  
After the prologue, ESP = frame_base + 0x00 (top of locals).
So [esp + 0x50] = return address.

When IDA says [esp+50h+arg_4], it means:
  [esp + (50h + arg_4 - 50h)] = [esp + arg_4]
  
No, IDA literally means [esp + 50h + arg_4_offset], where arg_4_offset is stored relative to EBP/frame.

Actually the simplest way: 
  IDA shows arg_4 at stack offset 0x58.
  After prologue, ESP is at offset 0x00 (bottom of locals).
  So arg_4 is at [ESP + 0x58].
  
  The instruction "mov esi, [esp+50h+arg_4]" means:
  [esp + 0x50 + arg_4] where arg_4 is defined as (0x58 - 0x50) = 0x08
  So it's [esp + 0x58].
  
YES: [esp + 0x58] = a2 (the key, called arg_4 in IDA = a2 in decompiler)

Actually wait, let me re-read the IDA stack frame:
  __return_address at 0x50
  arg_0 at 0x54   <-- this is probably 'this' (saved by the function? or first stack arg?)
  arg_4 at 0x58   <-- this is a2 (the key)
  arg_8 at 0x5C   <-- this is a3

And the instruction at 77552a: "mov esi, [esp+50h+arg_4]"
In IDA, "50h" is the frame size, and arg_4 = 0x58 - 0x50 = 8.
So [esp + 50h + 8] = [esp + 0x58] = arg_4 = a2 = KEY. ✓

At 0x77552a, ESI = a2 (the key). Then at 0x775935, ESI = [hash_bucket+8] = localized text.

Now in the ASI hook texts():
  push ebx        ; esp -= 4
  push edx        ; esp -= 4  
  push edi        ; esp -= 4
  push ebp        ; esp -= 4
  ; total: 4 pushes = 16 bytes (0x10)
  mov ecx, [esp+0x24 + 16]
  
  [esp + 0x24 + 16] = [esp + 0x34]
  Since we pushed 16 bytes, esp is 16 less than at hook point.
  At hook point (0x775939), esp was the same as prologue-end esp.
  So: [esp_hook - 16 + 0x34] = [esp_hook + 0x24]
  
  [esp_hook + 0x24] → what is this?
  From the frame: offset 0x24 = var_2C (a local variable, NOT an argument!)
  
  We need [esp_hook + 0x58] for a2 (the key).
  So the correct offset in texts() would be:
  [esp + 0x58 - 0x10] = [esp + 0x48]
  Or equivalently: [esp + 0x38 + 16] = [esp + 0x48]
  
  But the code uses [esp + 0x24 + 16] = [esp + 0x34]
  That's var_2C, not arg_4!
  
  The correct value should be [esp + 0x38 + 16] = [esp + 0x48]
  (0x58 - 0x10 = 0x48)

  Or in the code's notation: [esp + 0x38 + 16] = [esp + 0x48]
  So the code should use: mov ecx, [esp + 0x38 + 16]
  But it uses: mov ecx, [esp + 0x24 + 16]

  Difference: 0x38 - 0x24 = 0x14 (20 bytes off!)
  
  Actually wait, let me reconsider. The hook replaces 5 bytes at 0x775939.
  At 0x775939, the original instruction is "movzx eax, byte ptr [esi]" (3 bytes).
  The hook writes a 5-byte JMP, overwriting 5 bytes (0x775939-0x77593D).
  This clobbers 0x77593c (test al, al) and 0x77593e (jz) partially!
  
  No wait, JMP is 5 bytes: E9 xx xx xx xx
  0x775939: E9 (1 byte)
  0x77593A-0x77593D: offset (4 bytes)
  
  Original at 0x775939-0x77593D:
  0x775939: 0F B6 06     movzx eax, byte ptr [esi]  (3 bytes)
  0x77593C: 84 C0        test al, al                  (2 bytes)
  
  So the JMP overwrites: movzx + test al,al (5 bytes total). ✓
  
  The texts() function then does the movzx and test itself, and jumps to 0x77593E.
  
  Now at the JMP point (0x775939), what's on the stack?
  Between the prologue and 0x775939, is the stack balanced?
  
  Let me trace from loc_7755C6 (the main path):
  Need to see if there are any unbalanced pushes.
  
  Actually, the simplest approach: the decompiled code is well-formed C++,
  so the stack should be balanced at 0x775939.
  
  KEY QUESTION: what is [esp + 0x58] at 0x775939?
  It should be a2 (the key).
  
  In texts(), after 4 pushes (16 bytes):
  [esp + 0x48] = a2 (the key)  ← CORRECT offset
  
  But code uses [esp + 0x34] ← WRONG, this is a local variable
  
  CONCLUSION: The texts() function uses wrong stack offset [esp+0x24+16]=[esp+0x34]
  instead of the correct [esp+0x38+16]=[esp+0x48].
  It reads a local variable (var_2C) instead of the key argument (arg_4/a2).
"""

print("=== Stack offset analysis ===")
print(f"Frame size: 0x50 (from prologue)")
print(f"arg_4 (a2/key) at frame offset: 0x58")
print(f"At hook point 0x775939, ESP is at frame base (prologue-end ESP)")
print(f"  [ESP + 0x58] = a2 (key)")
print()
print(f"In texts() after 4 pushes (16 bytes = 0x10):")
print(f"  ESP_text = ESP_hook - 0x10")
print(f"  To access a2: [ESP_text + 0x58 + 0x10] = [ESP_text + 0x68]")
print(f"  But wait - after push ecx for FindTextByKey, ESP drops another 4")
print()
print(f"  Before push ecx: ESP = ESP_hook - 0x10")
print(f"  [ESP + 0x58 + 0x10] = [ESP + 0x68]? No...")
print(f"  [ESP_hook - 0x10 + 0x58] = [ESP + 0x48]")
print(f"  So correct offset: [esp + 0x48] or [esp + 0x38 + 16]")
print()
print(f"  Code uses: [esp + 0x24 + 16] = [esp + 0x34]")
print(f"  This accesses var_2C (frame offset 0x34) = local variable, NOT the key!")
print(f"  Correct: [esp + 0x38 + 16] = [esp + 0x48]")
print(f"  Difference: 0x14 = 20 bytes off")
