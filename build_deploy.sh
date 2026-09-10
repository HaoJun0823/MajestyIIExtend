#!/bin/bash
# ============================================================
# build_deploy.sh — MajestyII_UTF8 一键编译 + 部署（Git Bash）
# 用法: bash build_deploy.sh
#
# 说明:
#   - 用 cl.exe 命令行编译（MSBuild 在自动化环境可能被拦）
#     ⚠️ 本机 PowerShell 调不动 cl.exe（"无法在管道中间运行文档"），
#        所以务必用 Git Bash 跑本脚本，或改用 build.bat。
#   - 部署目标名 = 游戏实际加载的名字 MajestyII_GB18030_2000.asi
#     （★ 不是 majesty2_UTF8.asi / MajestyII_UTF8.asi —— 那两个游戏不读）
#
# 游戏目录: I:\SteamLibrary\steamapps\common\Majesty 2 Collection
# ============================================================
set -e

# 让脚本里的中文提示在 cmd/Git Bash 控制台正常显示（脚本本身是 UTF-8）
chcp.com 65001 >/dev/null 2>&1 || true

PROJ_DIR="G:/Projects/MajestyIIExtend"
SRC_DIR="$PROJ_DIR/MajestyII_UTF8"
GAME_DIR="I:/SteamLibrary/steamapps/common/Majesty 2 Collection"
DEPLOY_NAME="MajestyII_GB18030_2000.asi"

CL="/c/Program Files (x86)/Microsoft Visual Studio/2017/Professional/VC/Tools/MSVC/14.16.27023/bin/Hostx86/x86/cl.exe"
VCROOT="/c/Program Files (x86)/Microsoft Visual Studio/2017/Professional/VC/Tools/MSVC/14.16.27023"
SDKROOT="/c/Program Files (x86)/Windows Kits/10"
SDKVER="10.0.26100.0"

# ★ 路径必须转成 Windows 形式（C:\...）再交给 cl.exe。
#   原因：cl.exe 是原生 Windows 程序，看不懂 Git Bash 的 /c/... 路径，
#   直接用会报 "fatal error C1083: 无法打开包括文件 windows.h"。
#   用 cygpath -w 转换；INCLUDE/LIB 用 ';' 连接（Windows 分隔符）。
WIN() { cygpath -w "$1"; }
export INCLUDE="$(WIN "$VCROOT/include");$(WIN "$SDKROOT/Include/$SDKVER/ucrt");$(WIN "$SDKROOT/Include/$SDKVER/um");$(WIN "$SDKROOT/Include/$SDKVER/shared")"
export LIB="$(WIN "$VCROOT/lib/x86");$(WIN "$SDKROOT/Lib/$SDKVER/ucrt/x86");$(WIN "$SDKROOT/Lib/$SDKVER/um/x86")"

echo "==> [1/2] 编译 (cl, Release|Win32)"
cd "$SRC_DIR"

"$CL" /nologo /LD /EHsc /Y- /utf-8 /O2 \
  /D WIN32 /D NDEBUG /D MAJESTYIIUTF8_EXPORTS /D _WINDOWS /D _USRDLL \
  /I. \
  dllmain.cpp pch.cpp \
  /link "/OUT:MajestyII_UTF8.dll" /SUBSYSTEM:WINDOWS \
  kernel32.lib user32.lib gdi32.lib winmm.lib advapi32.lib shell32.lib ole32.lib

echo "==> [2/2] 部署 DLL -> 游戏 update/$DEPLOY_NAME"
cp -f "$SRC_DIR/MajestyII_UTF8.dll" "$GAME_DIR/update/$DEPLOY_NAME"

echo "==> 完成。验证:"
ls -lh "$GAME_DIR/update/$DEPLOY_NAME"
echo
echo "注意: 字库走 update/localization/texts/texts.zip；词典走 update/DictRead.txt"
echo "      （简繁切换见 update/global.ini 的 OverloadFromFolder）"
