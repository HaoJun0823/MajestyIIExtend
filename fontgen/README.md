# fontgen — Majesty 2 中文字库生成工具链

把 TTF 字体烘成游戏可直接加载的 **PNG + DDS(DXT5) + TUV** 三件套。
本项目当前生产配置是 `font_fromscratch.yaml`（19 套字体，CJK 字表 23940 字）。

---

## 一键构建（换字体后常用）

```bash
cd fontgen
python build_font_atlas.py font_fromscratch.yaml
```

- **耗时约 3m30s**，输出到 `out_fromscratch/`。
- 成功判据：末行 `✅ 处理完成：启用 19 套（跳过 0 套），成功 19 套。`
- **换字体只需改 yaml 里的 `font_path`**，无需改脚本。

### 内置自检（正常必全过）

贴图 CJK 槽 `224 + k` 的字符 **必须 == decode(`g_charlist_data[k]`)**（23940 项逐项校验）。
这条检查保证「贴图顺序 == DLL 字表顺序」这一铁律不被破坏。

---

## 两种运行模式

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| **追加模式** | 配置里**有** `source_dds` + `source_tuv` | 读游戏原版 DDS 作底图，保留原 224 个拉丁字符，在下方追加 CJK。不做 DXT 压缩（保画质）。 |
| **从零生成** | 配置里**没有**上面两键（本项目当前用的就是这种） | 从空白图集全新打包 0x20–0xFF + CJK。 |

`font_fromscratch.yaml` 用的是 **从零生成**；其中部分字体仍用
`special_from_original: [0x24]` 从原图抠「钱」图标（`0xFF` 抠「饼干」图标）。

---

## 配置文件（`font_fromscratch.yaml`）

```yaml
defaults:
  font_path: "SourceHanSansHWSC-VF.ttf"   # ← 换字体改这里
  zero_space_width: false
  # ★ 空格槽 slot0 的目标步进（px）。字典里每个汉字后面都补了 ASCII 空格，
  #   而引擎「步进 = 下一槽 x0 − 本槽 x0」→ 不压窄的话界面会变成「学 习 治 理」。
  #   2 = 实机验证值。设 null 或删掉 = 保持自然格宽。
  space_advance: 2

charlist_source: dll          # 字表来源 = dllmain.cpp 的 g_charlist_data[]（权威）
fonts:
  - { prefix: "small",  size: 16, special_from_original: [0x24], ... }
  ...
```

### 关键字段

| 字段 | 说明 |
|------|------|
| `font_path` | TTF/OTF/TTC 路径（相对于本目录） |
| `size` | **该字体的 CJK 格宽 px**，须与该字体在原版里的格宽一致（见下） |
| `bold` / `outline` | 加粗 / 黑线描边（对应 `_b` / `_c` 变体） |
| `special_from_original` | 需要从原版 DDS 抠出来的码点（`0x24` 钱 / `0xFF` 饼干） |
| `source_dds` / `source_tuv` | 追加模式用；本项目未用 |
| `tuv_out` | 同族共享 TUV 名（如 `font12a`/`font12b` 都写 `font12`） |
| `charlist_source: dll` | 从 `dllmain.cpp` 读字表（**当前权威源**，保证顺序一致） |

### ★ 各字体 CJK 格宽必须对齐原版

原版是**按字体区分格宽**的，烘错会导致长串消失 / 换行异常：

| 字体 | 原版 CJK | 原版空格步进 |
|------|---------|-------------|
| `small_c` | 16 | 7 |
| `paragraph_c` | 20 | 16 |
| `med_caption_c` | 19 | 16 |
| `big_caption_c` | 24 | — |
| `font12` | 12 | — |
| `font14` | 14 | — |
| `font18` | 18 | — |

---

## TUV 格式

```
TUVTXT
TUVCOUNT 24164
TUVBASE 4096 4096
<x1> <y1> <x2> <y2>     ← 行号 = slot 号（从 0 开始）
...
```

- 坐标整数，左闭右开；原版用 Tab 分隔。
- **引擎每字符步进 = 下一槽 x0 − 本槽 x0**（不是矩形宽度！）。
- `slot 223`（字符 `0xFF`）中文库必须写 `0 0 0 0`（引擎每个中文字前会先画一次前置标记）。
  纯拉丁库（`TUVCOUNT ≤ 224`）禁止留空。

---

## 其他脚本

| 脚本 | 用途 |
|------|------|
| `build_font_atlas.py` | ★ 主生成器 |
| `repack_texts.py` | 重打包 `texts.zip`；**内置 slot0 步进压缩**（幂等、双保险） |
| `fix_charlist_endian.py` | 字表端序修正（小端字 `L = 首字节 \| 次字节<<8`） |
| `gen_full_gb18030.py` | 生成完整 GB18030 追加段 |
| `fix_space_wrap.py` | 字典补空格 + 压空格步进 + 重打包（简繁通用） |
| `blank_slot223_tuv.py` | 修补 TUV 的 `slot 223` |
| `audit_coverage.py` / `final_audit.py` | 覆盖率 / 终检 |
| `verify_atlas_slots.py` | 校验贴图槽顺序 == DLL 字表顺序 |
| `_archive/` | 一次性脚本与旧日志（考古用） |

---

## 依赖

- Python 3 + `Pillow` + `pyyaml`
- `texconv.exe`（微软 DirectXTex，放本目录；用于 DXT5 压缩）
- 字体文件（`.ttf`）—— 体积大，**未纳入 git**，请自行放置

---

## 相关文档

- 项目总览：[`../README.md`](../README.md)
- 完整技术文档：[`../RESEARCH_HANDOFF.md`](../RESEARCH_HANDOFF.md)
