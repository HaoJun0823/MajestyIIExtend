---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '2034ab36-2293-4c82-b1f0-f1152f37e2dc'
  PropagateID: '2034ab36-2293-4c82-b1f0-f1152f37e2dc'
  ReservedCode1: '36de0091-c818-4438-b944-64ef811ddacb'
  ReservedCode2: '36de0091-c818-4438-b944-64ef811ddacb'
---

# Majesty 2 汉化工程交接文档（UTF-8 版）

> 更新日期：2026-09-07
> 工程目录：`G:\Projects\MajestyIIExtend`
> 游戏目录：`I:\SteamLibrary\steamapps\common\Majesty 2 Collection\`

---

## 一、项目总览

Majesty 2（王权2）汉化 DLL，合并 MJ2_fontfix + MJ2_TextsHook 为单一 DLL。
**当前版本从 GBK 双字节方案重构为 UTF-8 三字节方案**，已编译验证通过。

### 时间线

| 日期 | 里程碑 |
|------|--------|
| 2026-08-31 | 俄译中完成：M2_mod.loctable.xml col5 写入 2260 行译文 |
| 2026-09-03 | 词典校对：V0/V1/Eng 三方比对，7264 条 KEY 一致 |
| 2026-09-06 | 8 个过场视频简体/繁体中文字幕完成并部署 |
| 2026-09-06 | MajestyIIExtend DLL 工程创建（GBK 合并版） |
| 2026-09-07 | **UTF-8 重构完成，编译验证通过** |

---

## 二、UTF-8 方案核心设计

### 2.1 与原版 GBK 方案的区别

| 项目 | 原版 GBK | 当前 UTF-8 |
|------|----------|------------|
| 编码 | GBK 双字节 (lead+cont) | UTF-8 三字节 (E0-EF)(80-BF)(80-BF) |
| 状态机 | 2 状态 (flag=0/1) | 3 状态 (flag=0/1/2) |
| charlist | GBK 组合值 `((tail+0x20)<<8)|(lead+0x20)` | Unicode 码点 |
| 状态存储 | BYTE flag + BYTE lead = 2 字节 | BYTE flag + DWORD b1 + DWORD b2 = 12 字节 |
| 词典编码 | GBK | UTF-8（自动检测，兼容 GBK 输入） |
| lead byte 返回 | 0xDF (0xFF-0x20) | 0xDF（同） |
| 第二字节返回 | 0xFF（原版，触发 wrapper2 fallback） | **0xDF**（统一零宽，不触发 wrapper2 fallback） |

### 2.2 为什么 _caseState1 返回 0xDF 而非 0xFF

原版 GBK 方案中 `_caseState1` 返回 0xFF（未经 `sub 0x20`），这是有意设计：
- wrapper2（宽度缓存路径）中 `cmp eax,0xFF` 匹配 → 走特殊 fallback 路径设置宽度缓存
- 其他 wrapper 中 0xFF → `shl 0xFF,5 = 0x1FE0` → 访问字形表偏移 0x1FE0 处的字形

UTF-8 方案改为返回 0xDF：
- 字形表基址 = 0xA0BC18
- 索引 0xDF → 字形@0xA0D7F8，宽度@0xA0D810（**已通过零宽补丁设为 0.0f**）
- 索引 0xFF → 字形@0xA0DBF8，宽度@0xA0DC10（**未补零，1.0f，会产生间隙**）
- 返回 0xDF 使前两个 UTF-8 字节都使用已补零的零宽字形
- wrapper2 中 `cmp eax,0xFF` 不匹配（0xDF≠0xFF）→ 不走 fallback → 正常 `shl 0xDF,5` → 同一零宽字形

### 2.3 状态机返回值汇总

| 状态 | 输入 | 返回值 | glyph_index | 字形地址 | 宽度地址 | 宽度 |
|------|------|--------|-------------|----------|----------|------|
| state=0 | ≤0xA0 (ASCII) | byte-0x20 | byte | 基址+byte*32 | — | 正常 |
| state=0 | >0xA0 (lead) | 0xDF | 0xFF | 0xA0D7F8 | 0xA0D810 | **0.0f** |
| state=1 | 任意 | 0xDF | 0xFF | 0xA0D7F8 | 0xA0D810 | **0.0f** |
| state=2 | 任意 | index+0x100-0x20 | index+0x100 | 基址+(index+0x100)*32 | — | 正常 |
| state=2 | 未找到 | 0xE0 | 0x100 | 基址+0x2000 | — | 正常 |

### 2.4 UTF-8 解码逻辑

```
codepoint = ((b1-0x20)&0x0F)<<12 | ((b2-0x20)&0x3F)<<6 | ((b3-0x20)&0x3F)
```

其中 b1/b2 存储的是 arg1（原始字节+0x20），b3 = 当前字节的 arg1。

验证示例：
- "中" = U+4E2D → UTF-8: E4 B8 AD
  - b1=E4+0x20=0x104, (0x104-0x20)&0x0F=0x04, 0x04<<12=0x4000
  - b2=B8+0x20=0xD8, (0xD8-0x20)&0x3F=0x38, 0x38<<6=0x0E00
  - b3=AD+0x20=0xCD, (0xCD-0x20)&0x3F=0x2D
  - codepoint = 0x4000 | 0x0E00 | 0x2D = 0x4E2D ✓

---

## 三、Hook 点清单

全部为 32 位 x86，游戏主程序基址 0x400000：

### FontFix（字形映射）
| 地址 | 类型 | wrapper | 状态变量 | 用途 |
|------|------|---------|----------|------|
| 0x7E235D | 5字节 call | sub_700037A0 → sub_70003770 | g_state1 | 主渲染路径 |
| 0x7E1A53 | 5字节 call | sub_70003810 → sub_700037B0 | g_state2 | 宽度缓存路径 |
| 0x7D95F7 | 5字节 call | sub_70003870 → sub_70003820 | g_state3 | 渲染路径2 |
| 0x7D9DAA | 5字节 call | sub_70003870 → sub_70003820 | g_state3 | 渲染路径3 |

### TextsHook（文本替换）
| 地址 | 类型 | 作用 |
|------|------|------|
| 0x775939 | 5字节 jmp | 文本构建循环拦截，CRC32 查词典替换 |
| 返回地址 | — | 0x77593E |

### 补丁
| 地址 | 类型 | 原始值 | 新值 | 作用 |
|------|------|--------|------|------|
| 0x7E1A2F | 2字节 NOP | `jge short` (7x xx) | `90 90` | 禁用宽度缓存快路径 |
| 0xA0D810 | 4字节 | `0x3F800000` (1.0f) | `0x00000000` (0.0f) | 零宽字形（索引 0xDF/0xFF 共用） |

---

## 四、编译验证结果

### 4.1 编译配置

- 工具集：VS2017 v141（14.16.27023）
- 平台：Win32（x86 32位）
- 字符集：Unicode
- 输出：DLL（25088 字节）
- 基址：0x10000000（无 ASLR，有 .reloc）
- 编译选项：`/utf-8`（处理源码中的中文注释）

### 4.2 反汇编验证

用 capstone 反汇编编译出的 DLL，验证关键函数：

**状态机**（@0x10001600）：
- `cmp byte ptr [ecx],0` / `cmp byte ptr [ecx],1` → 3 状态分支 ✓
- `movzx ebx,byte ptr [edx]; sub ebx,0x20; and ebx,0xf; shl ebx,0xc` → UTF-8 首字节解码 ✓
- `movzx ecx,byte ptr [edx+4]; sub ecx,0x20; and ecx,0x3f; shl ecx,6` → 第二字节解码 ✓
- `movzx ecx,al; sub ecx,0x20; and ecx,0x3f; or ebx,ecx` → 第三字节解码 ✓
- `mov ecx,dword ptr [0x10008018]` → g_pCharlist 指针 ✓
- `_caseState1` 返回 0xDF ✓（修正后）
- `_caseState0` lead byte 返回 0xFF→0xDF（经 sub 0x20） ✓

**Hook 安装**（@0x10001780）：
- 4 个 call hook → 0x7D95F7, 0x7D9DAA, 0x7E1A53, 0x7E235D ✓
- 2 字节 NOP → 0x7E1A2F ✓
- 5 字节 jmp → 0x775939 ✓

**零宽补丁**（@0x10001914）：
- `mov dword ptr [0xa0d810], 0` → 1.0f 改为 0.0f ✓

**pushad wrappers**：
- 3 个 pushad wrapper（@0x100016D0, 0x10001730, 0x10001770）✓
- 每个调用对应的内层 wrapper ✓

**g_state 变量地址**：
- g_state3 = 0x10008390 (hook 3&4)
- g_state2 = 0x1000839C (hook 2)
- g_state1 = 0x100083A8 (hook 1)
- 每组 12 字节：[0]=flag, [4]=b1(DWORD), [8]=b2(DWORD)

---

## 五、charlist 数据

- 文件：`charlist_data.h`（自动生成，885 行）
- 内容：6995 个 Unicode 码点 + 0x0000 终止符
- 字形索引范围：0x100 ~ 0x1B3B（数组位置 + 0x100）
- 生成工具：`.temp/gen_charlist_unicode.py`
- 转换链：原版 GBK 组合值 → GBK 双字节码 → GB18030 解码 → Unicode 码点
- 顺序与原版完全一致 → 字形索引不变

---

## 六、词典系统

- 词典文件：`DictRead.txt`（运行时由 DLL 读取）
- 自动检测编码：UTF-8（BOM 或内容启发式）或 GBK
- GBK 词典自动转换为 UTF-8 后加载
- 格式：KEY 行 + VALUE 行交替
- 哈希：CRC32，表大小 65521（开放寻址法）
- 线程安全：CRITICAL_SECTION 保护

---

## 七、文件清单

```
G:\Projects\MajestyIIExtend\
├── .gitignore
├── .gitattributes
├── MajestyIIExtend.sln
├── RESEARCH_HANDOFF.md                    # 本文件
├── MajestyII_UTF8\
│   ├── MajestyII_UTF8.vcxproj             # VS2017 项目（v141, Win32, DLL, /utf-8）
│   ├── MajestyII_UTF8.vcxproj.filters
│   ├── MajestyII_UTF8.vcxproj.user
│   ├── dllmain.cpp                        # UTF-8 版主代码（~524行）
│   ├── charlist_data.h                    # Unicode charlist（6995条）
│   ├── framework.h
│   ├── pch.h
│   ├── pch.cpp
│   └── Release\
│       └── MajestyII_UTF8.dll             # 编译输出（25088字节）
├── .temp\
│   ├── extract_charlist.py                # 原 GBK charlist 提取
│   ├── gen_charlist_unicode.py            # Unicode charlist 生成
│   ├── verify_dll.py                     # DLL 反汇编验证
│   ├── verify_pushad.py                  # pushad wrapper 验证
│   ├── verify_fix.py                     # 状态机修正验证
│   ├── analyze_glyph_addr.py             # 字形表地址分析
│   └── stat_translation_state.py         # 翻译状态统计
```

---

## 八、待办事项

### 8.1 部署测试
1. 将 DLL 改扩展名为 `.asi`，放入游戏 update 目录
2. 部署 UTF-8 编码的 DictRead.txt
3. 启动游戏验证：
   - 中文连续显示无间隙（零宽字形生效）
   - 词典替换生效（UI/任务/单位名称）
   - 无崩溃/卡顿

### 8.2 加载方式
当前 DLL 需要通过代理 DLL 注入（原版使用 winmm.dll 代理，或 binkw64.dll 代理）。
release 包中已有 winmm.dll（2.3MB 代理 DLL）。

### 8.3 词典定稿
基于 V0 版本修复 P0 条目（350条），生成 UTF-8 编码的最终版 DictRead.txt。

### 8.4 字库覆盖缺口
词典中 2708 个不同汉字中，约 940~1015 个不在 charlist（6995 字）中。
这些字会 fallback 到索引 0x100（第一个中文字形），显示为错误的字。
需要扩展 charlist 或更换更完整的字库。

---

## 九、关键技术细节

### 9.1 状态机状态布局

```
g_stateN[12 字节]:
  [0]  flag  (BYTE)   - 0=等待lead, 1=等待byte2, 2=等待byte3
  [4]  b1    (DWORD)  - 第一字节+0x20（UTF-8 lead 0xE0~0xEF+0x20 溢出 8 位，需 DWORD）
  [8]  b2    (DWORD)  - 第二字节+0x20
```

### 9.2 wrapper 传参模式

```asm
; inner wrapper (e.g. sub_70003770):
push offset g_stateN      ; arg2 = 状态指针
push eax                  ; arg1 = 字节+0x20
mov edx, offset g_stateN+4 ; edx = b1 存储指针
call sub_700036A0         ; 状态机
; 返回 eax = 字形索引 - 0x20
```

### 9.3 pushad wrapper 模式

```asm
; outer wrapper (e.g. sub_700037A0):
pushad
push esp           ; pushad 后的 esp 指向 pushad 保存区
call inner_wrapper ; inner 读取 [esp+8] = pushad 区 = 原始 esi/edi
popad
ret
```

### 9.4 字形表地址计算

```
字形表基址 = 0xA0BC18
每个字形 = 32 字节 (shl 5)
字形地址 = 基址 + glyph_index * 32
宽度 = float[字形地址+0x18] - float[字形地址+0]

索引 0xDF → 字形@0xA0D7F8, 宽度@0xA0D810 (零宽补丁目标)
索引 0xFF → 字形@0xA0DBF8, 宽度@0xA0DC10 (未补零)
索引 0x100 → 字形@0xA0DC18 (第一个中文字形)
```