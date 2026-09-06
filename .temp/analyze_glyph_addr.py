# -*- coding: utf-8 -*-
"""
分析字形表地址关系。
从游戏主程序 hook 点上下文可知：
  hook 点做：shl reg, 5; add reg, 字形表基址; 然后访问 [reg+0x18] 和 [reg]
  
零宽补丁地址 0xA0D810 = 字形表基址 + 索引*32 + 0x18

需要确定字形表基址。

从反汇编可见：
  wrapper1 (0x100016A0): mov eax,[esi]; add eax,0x20; ... call sub_700036A0; mov [esi],eax; shl eax,5; mov [esi+0x1C],eax
  这说明 wrapper 返回的 eax（字形索引-0x20）被存回 [esi]，然后 (eax)<<5 存入 [esi+0x1C]
  但游戏中原来的代码会被 hook 替换，所以原来的 add reg, 字形表基址 是在 hook 之后还是之前？

从交接文档：
  hook @ 0x7E235D: 原始指令 mov eax,edi; shl eax,5 → 这是原始代码的开始
  hook 替换为 call sub_70003770
  
所以原始流程是：
  1. mov eax, edi      ; eax = 字形索引
  2. shl eax, 5        ; eax = 字形索引 * 32
  3. add eax, 字形表基址  ; eax = &字形[索引]
  4. fld [eax+0x18]    ; 读取宽度上限
  5. fsub [eax]        ; 减去宽度下限
  6. fstp [esi+0x20]   ; 存储宽度

hook 后：
  1. call sub_70003770  ; 替换了 mov eax,edi; shl eax,5
  2. wrapper 中：读取 edi（字形索引原始值），加 0x20，调状态机，返回新索引
  3. wrapper 返回后：eax = 新索引，shl eax,5 已在 wrapper 内完成
  4. 然后游戏继续执行 add eax, 字形表基址（这条指令不在 hook 范围内）

所以：
  零宽补丁的 0xA0D810 应该是 字形表基址 + 索引*32 + 0x18
  
  对于 fallback 索引 0xFF：
    地址 = 字形表基址 + 0xFF * 32 + 0x18 = 字形表基址 + 0x1FE0 + 0x18 = 字形表基址 + 0x1FF8
    
  如果 0xA0D810 = 字形表基址 + 0x1FF8，那么字形表基址 = 0xA0D810 - 0x1FF8 = 0xA0B818

  验证：索引 0x100（第一个中文字形）→ 字形表基址 + 0x100*32 = 0xA0B818 + 0x2000 = 0xA0D818
        字形宽度在 0xA0D818 + 0x18 = 0xA0D830

  实际上，从交接文档 3.3 节状态机说明：
    "flag=0 且字节 > 0x80 → CJK lead byte，设 flag=1，存 lead byte，返回 0xFF"
    然后在外部 eax = 0xFF - 0x20 = 0xDF（不对，原版直接返回 0xFF）
    
  让我重新理解。看原版反汇编（编译出的 MJ2_fontfix.asi）：
    _caseState0 lead path: mov eax,0xFF; sub eax,0x20 → 返回 0xDF
    _caseState1: mov eax,0xFF → 直接返回 0xFF（没有 sub 0x20）
    
  然后 wrapper 中：
    call sub_700036A0 → eax = 状态机返回值
    然后 wrapper 会做不同的事情：
    
  wrapper1 (sub_70003770, hook 0x7E235D):
    mov [esi],eax       ; 存回字形索引（0xDF 或结果）
    shl eax,5           ; eax = 0xDF*32 = 0x1BE0
    mov [esi+0x1C],eax  ; 存回 shl 后的值
    
  游戏原始代码后续：
    add eax, 字形表基址  ; eax = 字形表基址 + 0x1BE0 = &字形[0xDF]
    fld [eax+0x18]      ; 读 0x18 处的 float (宽度上限)
    fsub [eax]          ; 减去 0 处的 float (宽度下限)
    
  零宽补丁：字形表基址 + 0xDF*32 + 0x18 = ？

  如果补丁地址 0xA0D810 对应索引 0xFF（原版 _caseState1 返回的值）：
    字形表基址 + 0xFF*32 + 0x18 = 0xA0D810
    字形表基址 + 0x1FF8 = 0xA0D810
    字形表基址 = 0xA0B818
    
  如果补丁地址 0xA0D810 对应索引 0xDF（我们的 _caseState0 返回值经 sub 0x20）：
    但原版 _caseState0 lead byte 返回 0xDF 后，wrapper 做 shl eax,5 = 0xDF*32 = 0x1BE0
    字形表基址 + 0x1BE0 + 0x18 = 0xA0D810
    字形表基址 = 0xA0D810 - 0x1BF8 = 0xA0BC18

  原版 _caseState1 返回 0xFF，wrapper2 做：
    cmp eax,0xFF → 匹配 → 走 fallback 路径（不经过 shl 5）
    fallback 路径设置 [esi+0x10] 而不是 [esi+0x1C]
    
  所以原版 0xFF 有特殊处理！不需要经过 shl 5。
  而我们改 _caseState1 返回 0xDF 后：
    cmp eax,0xFF → 不匹配 → 走正常路径
    shl eax,5 = 0xDF*32 = 0x1BE0
    字形表基址 + 0x1BE0 = ??? 
    
  如果字形表基址 = 0xA0BC18：
    0xA0BC18 + 0x1BE0 = 0xA0D7F8
    宽度在 0xA0D7F8 + 0x18 = 0xA0D810 ← 这正是补丁地址！
    
  所以补丁地址 0xA0D810 对应的是 **索引 0xDF**（返回值 0xDF → shl 5 = 0x1BE0 → +基址 0xA0BC18 = 0xA0D7F8 → +0x18 = 0xA0D810）。

  这意味着：
    - _caseState0 lead byte 返回 0xDF → glyph@0xA0D7F8 宽度@0xA0D810 (已补零) ✓
    - _caseState1 返回 0xDF (我们的修改) → 同上 ✓
    - _caseState1 返回 0xFF (原版) → 触发 wrapper2 特殊路径 (不走 shl 5) 

  结论：我们的修改是对的！_caseState1 返回 0xDF 后：
    - wrapper1/3/4: shl 0xDF = 0x1BE0, + 0xA0BC18 = 0xA0D7F8, 宽度@0xA0D810 = 0.0f ✓
    - wrapper2: cmp eax,0xFF → 0xDF≠0xFF → 不走 fallback → shl 0xDF = 0x1BE0 → 同上 ✓
    
  完美！
"""
print("字形表基址 = 0xA0BC18")
print("索引 0xDF → 字形@0xA0D7F8, 宽度@0xA0D810 (已补零)")
print("索引 0xFF → 字形@0xA0D7F8+0x400=0xA0DBF8, 宽度@0xA0DC10 (未补零)")
print()
print("修改后的 _caseState1 返回 0xDF:")
print("  wrapper1/3/4: shl 0xDF,5 = 0x1BE0, +base 0xA0BC18 = 0xA0D7F8, 宽度@0xA0D810 = 0.0f ✓")
print("  wrapper2: 0xDF≠0xFF → 不触发 fallback → shl 0xDF,5 = 0x1BE0 → 同上 ✓")
print()
print("原版 _caseState1 返回 0xFF:")
print("  wrapper1/3/4: shl 0xFF,5 = 0x1FE0, +base 0xA0BC18 = 0xA0DBF8, 宽度@0xA0DC10 = 1.0f ✗ (间隙!)")
print("  wrapper2: 0xFF==0xFF → 触发 fallback 路径 (特殊处理)")
print()
print("结论：UTF-8 方案中 _caseState1 返回 0xDF 是正确选择")
