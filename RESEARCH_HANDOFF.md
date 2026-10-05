# Majesty 2 汉化工程技术交接文档（GBK 双字节版）

> 更新日期：2026-09-10
> 工程目录：`G:\Projects\MajestyIIExtend`
> 游戏目录：`I:\SteamLibrary\steamapps\common\Majesty 2 Collection`
> 本文档描述**当前线上方案**（GBK/GB18030 双字节），已实机验证。

---

## 0. 一句话总览

游戏（32 位 x86，基址 `0x400000`）通过一个 ASI（DLL）插件接管两件事：

1. **字形映射**：把引擎按字节遍历的 GBK 双字节流，正确映射到我们自己烘的
   CJK 贴图槽位（`slot = 在字表里的下标 + 224`）。
2. **文本替换**：在引擎构建文本的循环里拦截每个词条 KEY，用 CRC32 查表换成中文。

字库（19 套 DDS+TUV）与字表（`g_charlist_data[]`，23940 项）**顺序必须严格一致**，
这是整个工程的第一铁律。

---

## 1. ⚠️ 已被推翻的旧结论（务必不要重犯）

| 旧文档说法 | 真实情况 |
|-----------|---------|
| 「已从 GBK 双字节重构为 **UTF-8 三字节**方案」 | **错的，已回退。** 当前就是 GBK 双字节。UTF-8 三字节方案已废弃。 |
| charlist 6995 条（Unicode 码点） | 实际 **23940 项 GBK 小端字**（前 6995 = 原版序，后 16945 = 追加）。 |
| DLL 25088 字节 | 实际 **131584 字节**（`MajestyII_GB18030_2000.asi`）。 |
| charlist 存 Unicode 码点 | **错的。** 存的是「小端字」`L = 首字节 \| (次字节 << 8)`。 |
| 部署名 `majesty2_UTF8.asi` | 游戏实际加载 **`MajestyII_GB18030_2000.asi`**。见 §6。 |
| 字形索引范围 0x100~0x1B3B | 现在是 `0x100 ~ 0x100+23939 = 0x5D83`。 |

---

## 2. 核心数据模型：字表 `g_charlist_data[]`

### 2.1 顺序 = GB18030 字节序，**不是 Unicode 序**

- 共 **23940 项**（`WORD`），前 6995 项 = **原版顺序，永不改动**；后 16945 项为追加。
- 整体顺序 = **完整 GBK（即 GB18030 的双字节子集）按 lead/trail 字节序枚举**。

### 2.2 每项存「小端字」L

```c
// C 字面量写法 = 次字节<<8 | 首字节  → 内存小端 = [首字节][次字节]
L = 首字节 | (次字节 << 8)
```

**例**：
- `！` = GBK `A3 A1` → 数组存 `0xA1A3` → 内存字节 `A3 A1`。
- `單` = GBK `86 CE` → 数组存 `0xCE86` → 内存字节 `86 CE`。

⚠️ **经典陷阱**：如果存成原码（大端）`0xA3A1`，引擎按 L 查不到 →
回退到「找不到」分支 → 显示错字（不是方框，是**别的真字**）。

### 2.3 引擎取字算法（`sub_700036A0`，DLL 内 RVA `0x1A20`）

引擎原始逻辑（我们 hook 后重写并保持等价）：

```
若 flag != 0：
    若 本字节 == 0xFF：清 flag，返回 0（丢弃悬挂状态）
    否则：L = 前一字节 | (本字节 << 8)
          i = 在 g_charlist_data[] 里按值线性查找 L 的下标
          若找到：slot = i + 0x100  →  返回 slot - 0x20 = i + 224
          若找不到：slot = 0x100    →  返回 0x100 - 0x20 = 224（回退到第一个 CJK 槽）
          flag = 0
否则（flag == 0）：
    若 本字节 >= 0x80：flag = 1，记住本字节，返回 0xFF（零宽前置标记）
    否则：返回 本字节 - 0x20          （ASCII/拉丁，槽 0~223，不查表）
```

**slot 公式**：`slot = 下标 i + 224`（`224 = 0x100 - 0x20`）。
- 拉丁单字节：`slot = 字节 - 0x20`，取值 0~223，**不查表**。
- CJK：`slot = i + 224`，取值 224 ~ 24163。

⚠️ **阈值陷阱（2026-09-10 已修）**：`flag == 0` 分支判据必须是 **`0x80`**，不能是 `0xA0`。
- 上游 `0x7D95A2` / `0x7E22F6` 用的是 `mov al,[edx+4]; test al,al; jle`（**有符号**），
  即「原字节 ≥ `0x80` → 走 CJK 分支」。
- 若这里用 `0xA0`，则 GBK lead `0x81..0xA0` 的字（`單`=86CE、`務`=84D5 等）
  不进配对、被当单字节吞掉 → **整串从次字节开始错位** → `單人任務` 显示成 `躓稳巳蝿`。
- 现象特征：**错字都是真实的汉字，数量与原文一致，不出现多字符** —— 就是错位配对。

### 2.4 `pushad` 栈布局（写 naked asm 时必记）

```
[esi+0x00] = EDI
[esi+0x04] = ESI
[esi+0x08] = EBP
[esi+0x0C] = ESP_orig
[esi+0x10] = EBX
[esi+0x14] = EDX
[esi+0x18] = ECX
[esi+0x1C] = EAX
```
（`esi` 指 `pushad` 之后、`push esp` 得到的那个指针。）

---

## 3. Hook 点清单（32 位 x86，主程序基址 `0x400000`）

### 3.1 字形映射（4 个 call hook + 1 个 NOP）

| 地址 | 类型 | 替换目标 | 备注 |
|------|------|---------|------|
| `0x7D95F7` | 5 字节 `call` | `sub_70003870` | 渲染路径 |
| `0x7D9DAA` | 5 字节 `call` | `sub_70003870_B` | **独立状态**（adder7/8），避免与上一行互踩 |
| `0x7E1A53` | 5 字节 `call` | `sub_70003810` | 宽度缓存路径 |
| `0x7E235D` | 5 字节 `call` | `sub_700037A0` | 主渲染路径 |
| `0x7E1A2F` | 2 字节 → `90 90` | — | **NOP 掉 `jge short`**，禁用宽度缓存快路径 |

`sub_700036A0` 是共用的状态机入口；各 wrapper 的唯一区别是**各自持有独立的状态变量**
（`adder1..adder8` 之类），因为引擎会在同一帧里穿插调用不同路径。

### 3.2 文本替换（1 个 jmp hook）

| 地址 | 类型 | 作用 |
|------|------|------|
| `0x775939` | 5 字节 `jmp` | 拦截 `texts()` 文本构建循环，返回地址 `0x77593E` |

处理逻辑：读到词条 KEY → **CRC32** 查哈希表（开放寻址，表大小 `65521`，
`CRITICAL_SECTION` 保护）→ 命中则用 DLL 内 `HeapAlloc` 出的永久块替换文本。

### 3.3 补丁

| 地址 | 原始 | 新值 | 作用 |
|------|------|------|------|
| `0x7E1A2F` | `jge short` | `90 90` | 禁用宽度缓存快路径（见上） |

> 注：旧文档里的「零宽补丁 `0xA0D810`：`1.0f → 0.0f`」是 **UTF-8 三字节方案**的遗留，
> 当前 GBK 方案**不再使用这个补丁**（GBK 方案的零宽靠 `slot 223 = 0xFF` 的 TUV 处理，见 §4.3）。

---

## 4. TUV 贴图坐标格式（决定「字怎么排」）

### 4.1 文件格式

```
TUVTXT
TUVCOUNT 24164
TUVBASE 4096 4096
<slot0 的 x1> <y1> <x2> <y2>
<slot1 的 ...>
...
```

- 第 3 行后，**每行对应一个 slot，行号 = slot 号**（从 0 开始）。
- 坐标整数，`x1,y1` 左上闭，`x2,y2` 右下开。原始游戏文件用 **Tab** 分隔。

### 4.2 ★ 步进（advance）公式 —— 最容易踩的坑

> **引擎每字符的横向步进 = 下一槽的 `x0` − 本槽的 `x0`。**
> TUV 矩形本身的宽度**不影响绘制**（矩形决定「取哪块贴图」，不决定「占多宽」）。

也就是说：

- `slot0`（空格 `0x20`）的宽度 = `slot1.x0 − slot0.x0`。
- 想把空格压窄，**必须把 `slot0.x0` 前移**，只收窄矩形（`x2=x1`）是**没用的**。

### 4.3 slot 223（字符 `0xFF`）必须写 `0 0 0 0`

引擎**每画一个中文字之前，会先画一次 `0xFF` 前置标记**。
若 `slot 223` 有真实墨迹 → 每个汉字前面都会糊上一块 → 视觉上像重影/乱码。

- 中文 TUV：`slot 223` **必须** 写成 `0 0 0 0`（零尺寸，配合上面「步进=差分」公式，
  零尺寸也不影响宽度，安全）。
- **纯拉丁字库**（`TUVCOUNT ≤ 224`）：`0xFF` 是**真实字符 `ÿ`**，**禁止留空**。
- 修补工具：`fontgen/blank_slot223_tuv.py`。

### 4.4 空格槽压缩（`space_advance`）

**背景**：字典里每个汉字之间必须有 ASCII 空格（见 §5），所以界面每个字后面都跟一个空格。
若空格用自然宽度（约 7~9 px），界面会变成 `学 习 治 理` 的大间距。

**解法**（`font_fromscratch.yaml` 的 `defaults.space_advance: 2`）：
把 `slot0.x0` 设为 `slot1.x0 − 2`，让空格只占 2 px。

**双保险**（防止某个环节漏掉）：
1. `build_font_atlas.py` 的 `build_from_scratch()` → `write_tuv_scratch()` 支持 `space_advance`。
2. `repack_texts.py` 在**重打包 zip 时**对每个 `.tuv` 自动再跑一次 `compress_slot0()`（幂等）。

> ⚠️ **历史事故**：2026-09-10 13:16 修好 zip 里的 slot0，13:18 又跑了一次**旧版**
> `repack_texts.py`，把修复**覆盖回自然宽度**了。现在压缩逻辑已内建进脚本，
> 不可能再被覆盖 —— 这就是「双保险」的由来。

---

## 5. 词典：`DictRead.txt` 与断行机制

### 5.1 格式

```
#KEY_ENTRY
中文值
#NEXT_KEY
另一个值
```

- **KEY 行以 `#` 开头，VALUE 是紧接着的下一行**（两行一组）。
- 编码：**GBK**（`DictRead.txt`）。⚠️ `DictRead_V7*.txt` 是 **UTF-8**，别搞混。
  编码自动识别在 DLL 里做（BOM / 内容启发式）。
- 行尾：CRLF 或 LF 都能读（`LoadDict()` 把 `\n` 和 `\r` 都当行尾）。

### 5.2 ★★ 为什么每个汉字后面必须有空格（本轮最关键结论）

> **引擎只在「空格」处断行。**

- 若字典是 **compact**（汉字连排、无空格）→ 超长串**没有任何断点** →
  换行/悬挂缩进算法失效 → **文字只渲染首次，后续消失**（看起来像「闪烁一下就不见了」）。
- 修复：**每个汉字后面补 1 个 ASCII 空格**。老版 V2 / V2.6 字典本来就是这样。
- 现象验证：用户实测「在文本中间随便加个空格就没事了」→ 直接指向此根因。

同理，`<...>` 标签内**不要加空格**（会被当成断行点破坏标签）。

### 5.3 相关工具

| 工具 | 作用 |
|------|------|
| `fontgen/apply_respace.py` | 标签感知地补空格 |
| `fontgen/space_rule2.py` | 验证空格规则 |
| `fontgen/dict_space_stats.py` | 统计字典空格情况 |
| `fontgen/fix_space_wrap.py` | **批量修**：补空格 → 压空格步进 → 重打包 zip（简繁通用，`--dict` 指定路径） |

### 5.4 ❌ 已失败并回退的尝试（不要重试）

曾在 `0x7D96E5` 处 `HookJmp`，想在 `0x7D95F7` 文本函数内 `add ecx,ebx` 处
「把 CJK 步进翻倍」来模拟空格宽度 → **加的是真实宽度**，界面变成 `学 习 治 理`，已回退。
**正解还是补空格 + `space_advance` 压窄空格槽。**

---

## 6. 部署与语言切换

### 6.1 游戏实际加载的文件（★ 与脚本不符，已确认）

`update/` 目录下的真实文件名：

| 文件 | 说明 |
|------|------|
| **`MajestyII_GB18030_2000.asi`** | **游戏真正加载的插件**（131584 B）。**不是** `MajestyII_UTF8.asi`。 |
| `DictRead.txt` | 简体词典（GBK）。**文件名硬编码在 DLL 里**（`#define DICT_FILE`）。 |
| `localization/texts/texts.zip` | **字库实际加载路径**（44 条目，前缀 `enGUIne/Fonts/`）。 |

⚠️ `update/localization/texts/` 下的散装 `small_c.tuv` / `small_c.dds`（若存在）
**只是工作副本，不是加载路径** —— 曾经误导过一次结论，建议删除或改名。

### 6.2 简繁切换机制（`global.ini`）

`update/global.ini`（约 43 字节）：

```ini
[FileLoader]
OverloadFromFolder=update_cht
```

- 游戏支持**多文件夹语言覆盖**：`OverloadFromFolder` 指定一个覆盖目录。
- 繁体方案：建 `update_cht/`，内含繁体 `DictRead.txt` + 繁体 ASI + 繁体 `texts.zip`。
- **汉字字形本身简繁共用同一套 `texts.zip`**（charlist 已含 GB18030 全部）
  → 简繁的区别只在**词典文本**。
- 实测证据：`update_cht/MJ2_log.txt` 时间戳正常，`hit=1713 / miss=0` → 机制真实生效。

### 6.3 简繁关系

- 简体 = master 词典（`update/DictRead.txt` ↔ `DictRead_V7.txt`）。
- 繁体 = 由简体经 **OpenCC** 派生（`DictRead_V7_CHT.txt`），**同样需要补空格**。
- 两者都已补空格（2026-09-10）：
  - 简：`DictRead_V7.txt` 1105734 B
  - 繁：`DictRead_V7_CHT.txt` 1105905 B（补 122496 个空格，7258 条被改）

---

## 7. 构建链（★ 换字体后「直接 build 就能成功」）

### 7.1 字库构建（Python，19 套一次搞定）

```bash
cd G:\Projects\MajestyIIExtend\fontgen
python build_font_atlas.py font_fromscratch.yaml
```

- **实测耗时约 3m30s**，输出 19 套（16 个 `.tuv` + 19 个 `.dds` + 19 个 `.png`）。
- 成功判据（脚本末行）：`✅ 处理完成：启用 19 套（跳过 0 套），成功 19 套。`
- 输出目录：`fontgen/out_fromscratch/`
- **换字体只需改 `font_fromscratch.yaml` 里的 `font_path`**，其余不用动。

**自检**（脚本内置，正常必全过）：贴图 CJK 槽 `224+k` 的字符
**必须 == `decode(g_charlist_data[k])`**（23940 项逐项校验）。

### 7.2 全链顺序（改字表时）

```
fix_charlist_endian.py
   └─ 生成/校正 charlist_data.h（23940 项小端字）
        ↓
build_font_atlas.py font_fromscratch.yaml
   └─ 19 套 DDS/TUV（顺序 == charlist_data.h）
        ↓
cl.exe 编译 dllmain.cpp → MajestyII_UTF8.dll
        ↓
部署为 update/MajestyII_GB18030_2000.asi
        ↓
重打包 texts.zip（repack_texts.py，内置 slot0 压缩）
```

> 🔴 **源码改了必须重编重部署。** 曾出现 `MajestyII_UTF8.asi` 长期是**早于源码的旧构建**
> （`.text` 逐字节相同，只差 `.rdata` 追加段）。

### 7.3 编译（cl.exe，Release|Win32）

- 工具链：**VS2017 Professional** MSVC `14.16.27023`（x86）+ Windows SDK `10.0.26100.0`。
- 关键选项：`/nologo /LD /EHsc /Y- /utf-8 /O2`（`/utf-8` 必须有，源码注释是中文）。
- MSVC 内联汇编**不接受 `jmp imm32`** → 用 `push <addr>; ret`。
- ⚠️ **本机 PowerShell 工具不能调 cl.exe**（报「无法在管道中间运行文档」）
  → 用 **Git Bash** 跑 `build_deploy.sh`，或用 cmd 跑 `build.bat`。
- 生产物 `MajestyII_GB18030_2000.asi` ≈ 14 万字节（视源码而定，实测 143872 B）。

**★ Git Bash 调用 cl.exe 的路径陷阱（已修）**：
cl.exe 是原生 Windows 程序，**看不懂 `/c/...` 风格路径**。
早期脚本用 `MSYS_NO_PATHCONV=1 "$CL" ... "/I$MSVC_INC"` 会报
`fatal error C1083: 无法打开包括文件 "windows.h"`。
正解：用 **`cygpath -w` 把路径转成 `C:\...`**，再放进 `INCLUDE` / `LIB` 环境变量
（`;` 分隔）。见 `build_deploy.sh` 里的 `WIN()` 函数。

**控制台中文乱码**：脚本里的中文提示在 GBK 控制台会显示成乱码，
脚本开头加 `chcp.com 65001`（或 `chcp 65001`）切到 UTF-8 即可。

---

## 8. 目录结构（整理后）

```
G:\Projects\MajestyIIExtend\
├── README.md                     # 项目导航（新）
├── RESEARCH_HANDOFF.md           # 本文件（技术文档）
├── build_deploy.sh               # ★ 一键编译 + 部署（Git Bash）
├── build.bat                     # ★ 同上的 cmd 版
├── MajestyIIExtend.sln
├── MajestyII_UTF8\
│   ├── dllmain.cpp               # 主代码（GBK 双字节 + texts hook + zip hook）
│   ├── charlist_data.h           # 字表（23940 项小端字，自动生成）
│   ├── MajestyII_UTF8.vcxproj    # v141 / Win32 / DLL / /utf-8
│   ├── framework.h / pch.h / pch.cpp
│   └── (旧 .bak 已并入 archives/)
├── fontgen\
│   ├── build_font_atlas.py       # ★ 字库生成器（追加 / from_scratch 双模式）
│   ├── font_fromscratch.yaml     # ★ 当前生产配置（19 套字体）
│   ├── repack_texts.py           # ★ 重打包 texts.zip（内置 slot0 压缩）
│   ├── fix_charlist_endian.py    # 字表端序修正
│   ├── out_fromscratch\          # 构建产物（不入 git；★2026-10-02 已清理，需重烘）
│   └── original_dds\             # 原版参考字库（不入 git，25MB）
├── archives\                     # ★ 统一归档区（不入 git，25MB）
│   ├── .temp_hist\               # 历史 .temp 脚本 + merged 源码/DLL
│   ├── fontgen_archive\          # fontgen 一次性脚本 / 旧日志
│   ├── loc_qa\                   # 词典 QA 工具链（172 文件，2026-10-02 归档）
│   └── pakcrypt\                 # pak 解密探针
├── packages\                     # NuGet（MinHook）缓存，不入 git
└── .workbuddy\memory\            # 项目记忆（不入 git）
```

> ★ **2026-10-02 仓库整理**：`_archive/` 统一改名为 `archives/`，原
> `fontgen/_archive/`、`loc_qa/`、`pakcrypt/` 一并归入该区。
> 同时删除了纯垃圾：`.vs/`(128M)、`Release/`、`MajestyII_UTF8/Release/`、
> `*.obj`/`*.dll`、两个 `__pycache__`、以及 `fontgen/out_fromscratch*`（544MB）。
> ⚠️ **字库产物已删** —— `repack_texts.py` 依赖 `out_fromscratch/` 里的 TUV+DDS，
> 需先跑 `python fontgen/build_font_atlas.py font_fromscratch.yaml`（约 3m30s）
> 才能重打包 texts.zip。仓库体积 852MB → 178MB。

---

## 9. 关键文件速查

| 路径 | 说明 |
|------|------|
| `MajestyII_UTF8/dllmain.cpp` | 主代码。`g_charlist_data[]` 在 478 行起；状态机 3476 行；`ApplyHooks()` 3726 行 |
| `MajestyII_UTF8/charlist_data.h` | 字表（自动生成，勿手改） |
| `fontgen/font_fromscratch.yaml` | 19 套字体配置，`space_advance: 2` |
| `fontgen/out_fromscratch/*.tuv` | 16 个 TUV，`TUVCOUNT 24164` |
| `update/MajestyII_GB18030_2000.asi` | 线上插件 |
| `update/DictRead.txt` | 简体词典（GBK，已补空格） |
| `update/DictRead_V7_CHT.txt` | 繁体词典（UTF-8，已补空格） |
| `update/localization/texts/texts.zip` | 字库加载路径 |
| `update/global.ini` | `OverloadFromFolder=update_cht` 简繁开关 |

---

## 10. 常用命令

```bash
# 构建字库（19 套，~3.5min）
cd G:/Projects/MajestyIIExtend/fontgen
python build_font_atlas.py font_fromscratch.yaml

# 编译 + 部署（Git Bash）
cd G:/Projects/MajestyIIExtend && bash build_deploy.sh

# 编译 + 部署（cmd）
cd /d G:\Projects\MajestyIIExtend && build.bat

# 字典补空格 + 压空格步进 + 重打包 zip
python fontgen/fix_space_wrap.py --dict <路径>

# 只重打包 texts.zip（会重新压 slot0，幂等）
python fontgen/repack_texts.py <路径>/texts.zip

# 空槽统计
python fontgen/audit_coverage.py
```

---

## 11. 已知遗留 / 待办

1. **空槽 2151**：`build_font_atlas.py` 自检报「空槽(无字形/缺失码点)数：2151」。
   疑似一批规律区间码点（如 `0x1C53~0x1C63`）在字表里有、但字体缺字。
   **待分析**：是 charlist 冗余区，还是所选字体确实缺这些码点。
   （影响：这些字写空槽，不显示方框，但也不显示内容。）
2. **`update/` 目录里 .bak 与其他语言文件混杂**：属游戏目录，未纳入本仓库。
3. **`fontgen/original_dds` / `texconv.exe` 不入 git**：体积原因（25MB / 第三方工具）。
4. **构建脚本已统一**：`build_deploy.sh`（Git Bash，**已实测通过**）与
   `build.bat`（cmd，结构等价）是仅有的两套入口，
   `MajestyII_UTF8/build_asi.ps1` 为冗余第三套（用 BuildTools 路径 + SDK 19041），
   **已归档到 `archives/build_asi.ps1.redundant`**，不建议再用。

> 注：本机环境无法从自动化工具直接调 `cmd.exe` / PowerShell 跑 cl.exe，
> 所以 `build.bat` 只做了结构复核（与 `.sh` 同一 cl、同一 flags、同一 Windows 路径），
> 未做端到端实测。**日常建议用 `bash build_deploy.sh`**（已实测）。

---

## 12. 历史时间线

| 日期 | 里程碑 |
|------|--------|
| 2026-08-31 | 俄译中完成：`M2_mod.loctable.xml` col5 写入 2260 行译文 |
| 2026-09-03 | 词典校对：V0/V1/Eng 三方比对，7264 条 KEY 一致 |
| 2026-09-06 | 8 个过场视频简繁字幕完成并部署 |
| 2026-09-06 | DLL 工程创建 |
| 2026-09-07 | ~~UTF-8 三字节重构~~（后已回退） |
| 2026-09-10 | 字表端序修正（追加段原码 → 小端）；状态机阈值 `0xA0 → 0x80`；
|             | 字典 compact 断行根因定位 + 补空格；`space_advance: 2` 空格槽压缩；
|             | 繁体字典同步；仓库整理 + 本文档重写 |
