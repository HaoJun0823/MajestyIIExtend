# MajestyIIExtend — 王权 2（Majesty 2）简体/繁体中文汉化工程

通过一个 ASI（DLL）插件给 32 位《Majesty 2》注入 GBK/GB18030 中文字形与词典替换，
实现**简体 / 繁体**双语言汉化。

> 📖 **第一次接触本项目，请先读 [`RESEARCH_HANDOFF.md`](RESEARCH_HANDOFF.md)** ——
> 那是完整的技术交接文档：数据模型、Hook 点、构建链、踩过的坑全在里面。

---

## 快速开始

### 只想改字体、重烘字库

```bash
cd fontgen
# 1. 改 font_fromscratch.yaml 里的 font_path（换字体）
# 2. 一键构建（19 套，约 3.5 分钟）
python build_font_atlas.py font_fromscratch.yaml
```

成功输出：`✅ 处理完成：启用 19 套（跳过 0 套），成功 19 套。`

### 改了 DLL 源码，要编译 + 部署

```bash
# Git Bash
bash build_deploy.sh

# 或 cmd
build.bat
```

### 字典处理（补空格 / 压空格步进 / 重打包 zip）

> `fix_space_wrap.py` 已退役并移入 `archives/fontgen_archive/oneoff_scripts/`。
> 现行机制是 **DLL 侧动态补空格**：`dllmain.cpp` 的 `RespaceCJK_GBK()`
> 在 `LoadDict` 时给每个汉字后插入 ASCII 空格，提供引擎断行点（提交 `ef06f46`）。

### 改了字体配置，要重烘字库（必需的第一步）

```bash
cd fontgen
python build_font_atlas.py font_fromscratch.yaml   # 约 3m30s，产出 out_fromscratch/
```

> ⚠️ `out_fromscratch/` 属构建产物，2026-10-02 整理时已删除（省 544MB）。
> `repack_texts.py` 依赖它，重打包 texts.zip 前**必须先烘**。

---

## 两个必须知道的铁律

1. **字表顺序 = GB18030 字节序，绝不是 Unicode 序。**
   `dllmain.cpp` 的 `g_charlist_data[]`（23940 项）与贴图槽位**必须严格一一对应**：
   `slot = 下标 + 224`。任何一侧重排都会导致整体乱码。

2. **字典里每个汉字后面必须有 1 个 ASCII 空格。**
   引擎只在空格处断行；compact 字典会让长文本「只渲染首次、后续消失」。

---

## 目录导航

| 目录 / 文件 | 说明 |
|------------|------|
| `RESEARCH_HANDOFF.md` | ★ 完整技术文档（先读这个） |
| `MajestyII_UTF8/` | DLL 源码（`dllmain.cpp` / `charlist_data.h` / vcxproj） |
| `fontgen/` | 字库生成工具链（Python） |
| `build_deploy.sh` / `build.bat` | 一键编译 + 部署 |
| `archives/` | 归档区：历史脚本 / 旧日志 / 已退役的 QA 工具链（考古用，不参与构建、不入 git） |
| `.workbuddy/memory/` | 项目工作记忆 |

## 环境依赖

- **Python 3** + `Pillow` + `pyyaml`
- **VS2017 Professional**（MSVC 14.16.27023）+ **Windows SDK 10.0.26100.0**
- **texconv.exe**（DirectXTex，用于 DXT5 压缩；放在 `fontgen/` 下）

## 游戏路径

```
I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\
```

游戏实际加载的插件名是 **`MajestyII_GB18030_2000.asi`**（不是 `MajestyII_UTF8.asi`）。
