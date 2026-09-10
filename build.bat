@echo off
rem ============================================================
rem build.bat - MajestyII_UTF8 一键编译 + 部署（cmd 版）
rem 与 build_deploy.sh 等价；Git Bash 用那个，cmd 用这个。
rem 注意：部署名 = 游戏实际加载的 MajestyII_GB18030_2000.asi
rem ============================================================
chcp 65001 >nul
setlocal

set CL="C:\Program Files (x86)\Microsoft Visual Studio\2017\Professional\VC\Tools\MSVC\14.16.27023\bin\Hostx86\x86\cl.exe"
set MSVC_INC=C:\Program Files (x86)\Microsoft Visual Studio\2017\Professional\VC\Tools\MSVC\14.16.27023\include
set SDK_INC_UCRT=C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\ucrt
set SDK_INC_UM=C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\um
set SDK_INC_SHARED=C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\shared
set MSVC_LIB=C:\Program Files (x86)\Microsoft Visual Studio\2017\Professional\VC\Tools\MSVC\14.16.27023\lib\x86
set SDK_LIB_UCRT=C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\ucrt\x86
set SDK_LIB_UM=C:\Program Files (x86)\Windows Kits\10\Lib\10.0.26100.0\um\x86

cd /d "G:\Projects\MajestyIIExtend\MajestyII_UTF8"

echo ==^> [1/2] 编译 (cl, Release|Win32)
%CL% /nologo /LD /EHsc /Y- /utf-8 /O2 ^
  /D WIN32 /D NDEBUG /D MAJESTYIIUTF8_EXPORTS /D _WINDOWS /D _USRDLL ^
  /I. "/I%MSVC_INC%" "/I%SDK_INC_UCRT%" "/I%SDK_INC_UM%" "/I%SDK_INC_SHARED%" ^
  dllmain.cpp pch.cpp ^
  /link "/OUT:MajestyII_UTF8.dll" /SUBSYSTEM:WINDOWS ^
  "/LIBPATH:%MSVC_LIB%" "/LIBPATH:%SDK_LIB_UCRT%" "/LIBPATH:%SDK_LIB_UM%" ^
  kernel32.lib user32.lib gdi32.lib winmm.lib advapi32.lib shell32.lib ole32.lib > build_output.txt 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo BUILD FAILED - see build_output.txt
    type build_output.txt
    exit /b 1
)

echo ==^> [2/2] 部署 DLL -^> 游戏 update/MajestyII_GB18030_2000.asi
copy /Y MajestyII_UTF8.dll "I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\MajestyII_GB18030_2000.asi"

echo ==^> 完成。验证:
dir "I:\SteamLibrary\steamapps\common\Majesty 2 Collection\update\MajestyII_GB18030_2000.asi"
echo.
echo 注意: 字库走 update/localization/texts/texts.zip; 词典走 update/DictRead.txt
echo       简繁切换见 update/global.ini 的 OverloadFromFolder
