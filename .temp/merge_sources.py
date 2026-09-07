#!/usr/bin/env python3
"""合并三个原版 ASI 源码为单一 DLL 源文件"""
import re

base = r"I:\SteamLibrary\steamapps\common\Majesty 2 Collection\汉化\Majesty2-CN\source"

# 读取三个源文件（原版可能是 GBK 编码）
with open(f"{base}\\MJ2_fontfix\\MJ2_fontfix.cpp", "r", encoding="gbk") as f:
    fontfix = f.read()

with open(f"{base}\\MJ2_TextsHook_nolog\\MJ2_TextsHook_nolog.cpp", "r", encoding="gbk") as f:
    textshook = f.read()

with open(f"{base}\\MJ2_ZipFile\\MJ2_ZipFile.cpp", "r", encoding="gbk") as f:
    zipfile = f.read()

# 去掉每个文件的 #include <windows.h>（只保留第一个）和其他重复声明
def strip_includes(code):
    # 去掉 #include <windows.h>
    code = re.sub(r'#include\s*<windows\.h>\s*\n?', '', code)
    # 去掉 extern "C" void __chkstk() { return; }
    code = re.sub(r'extern\s+"C"\s+void\s+__chkstk\(\)\s*\{\s*return;\s*\}\s*\n?', '', code)
    # 去掉 #pragma comment(linker, ...)
    code = re.sub(r'#pragma\s+comment\(linker,[^)]*\)\s*\n?', '', code)
    # 去掉 #ifndef INVALID_FILE_ATTRIBUTES ... #define ... #endif
    code = re.sub(r'#ifndef\s+INVALID_FILE_ATTRIBUTES\s*\n#define\s+INVALID_FILE_ATTRIBUTES[^\n]*\n#endif\s*\n?', '', code)
    return code

fontfix = strip_includes(fontfix)
textshook = strip_includes(textshook)
zipfile = strip_includes(zipfile)

# 去掉各文件的 DllMain，后面统一写
def strip_dllmain(code):
    # 匹配 BOOL WINAPI/APIENTRY DllMain(...) { ... } （最后一个函数）
    # 用非贪婪匹配到文件末尾
    idx = code.find('BOOL WINAPI DllMain')
    if idx == -1:
        idx = code.find('BOOL APIENTRY DllMain')
    if idx == -1:
        return code
    return code[:idx].rstrip() + '\n'

fontfix_body = strip_dllmain(fontfix)
textshook_body = strip_dllmain(textshook)
zipfile_body = strip_dllmain(zipfile)

# 合并
merged = """// MajestyII 合并版 - fontfix + TextsHook + ZipFile
// 三个原版 DLL 源码合并，v141_xp 命令行编译
// 编译: /Gz /Zp4 /Os /Gy /LD /GF /GS- /DWINDOWS_IGNORE_PACKING_MISMATCH
// 链接: /nodefaultlib /entry:DllMain@12 /ALIGN:4096 /SUBSYSTEM:WINDOWS,4.0
#include <windows.h>

#ifndef INVALID_FILE_ATTRIBUTES
#define INVALID_FILE_ATTRIBUTES ((DWORD)-1)
#endif

// ========== Part 1: fontfix (MJ2_fontfix.cpp) ==========

"""
merged += fontfix_body
merged += "\n// ========== Part 2: TextsHook (MJ2_TextsHook_nolog.cpp) ==========\n\n"
merged += textshook_body
merged += "\n// ========== Part 3: ZipFile (MJ2_ZipFile.cpp) ==========\n\n"
merged += zipfile_body

# 统一 DllMain
merged += """
// ========== 合并入口 ==========

BOOL WINAPI DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    if (ul_reason_for_call == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(hModule);

        // TextsHook 初始化
        InitializeCriticalSection(&g_cs);
        int i;
        for (i = 0; i < HASH_SIZE; i++) g_hashTable[i].text = NULL;
        LoadDict();
        InstallHook_TextsHook();

        // fontfix hook
        ApplyHooks();

        // zipfile hook
        InstallHook_ZipFile();
    }
    else if (ul_reason_for_call == DLL_PROCESS_DETACH)
    {
        int i;
        for (i = 0; i < HASH_SIZE; i++) {
            if (g_hashTable[i].text)
                HeapFree(GetProcessHeap(), 0, g_hashTable[i].text);
        }
        DeleteCriticalSection(&g_cs);
    }
    return TRUE;
}
"""

# 写入
outpath = r"G:\Projects\MajestyIIExtend\.temp\merged\MajestyII_merged.cpp"
with open(outpath, "w", encoding="utf-8") as f:
    f.write(merged)

# 验证
with open(outpath, "r", encoding="utf-8") as f:
    verify = f.read()

print(f"Lines: {len(verify.splitlines())}")
print(f"Chars: {len(verify)}")

# 检查关键符号是否存在
checks = [
    "g_charlist_data", "sub_700036A0", "ApplyHooks",
    "g_hashTable", "LoadDict", "InstallHook_TextsHook",
    "CheckAndReplaceExt", "InstallHook_ZipFile",
    "DllMain"
]
for s in checks:
    if s in verify:
        print(f"  OK: {s}")
    else:
        print(f"  MISSING: {s}")

# 检查是否有重复的 DllMain
count = verify.count("DllMain")
print(f"DllMain count: {count}")
