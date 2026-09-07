/*
 * MJ2_ZipFile.cpp
 * 编译环境：VC6.0 → Win32 Release DLL
 * 完全使用 Windows API，无 C 运行时库
 * 功能：将 .pak 文件路径替换为同名的 .zip（如果存在）
 */
#include <windows.h>

#define CALL_ORIG_INSTR_ADDR  0x007311B1
#define ORIG_FUNC_ADDR        0x00731410

#ifndef INVALID_FILE_ATTRIBUTES
#define INVALID_FILE_ATTRIBUTES ((DWORD)-1)
#endif

// IAT 条目地址
DWORD g_CtorIAT = 0x0087D2F8;   // eFileStream::eFileStream 构造函数指针
DWORD g_OpenIAT  = 0x0087D2F4;   // eFileStream::Open 函数指针

static void* pOrigFunc = (void*)ORIG_FUNC_ADDR;

// ------------------------------------------------------------
// 检查路径扩展名，若为 .pak 且对应的 .zip 文件存在，则返回 .zip 路径
// 返回：原路径（不需要替换）或静态缓冲区中的新路径
const char* CheckAndReplaceExt(const char* path)
{
    static char zipPath[MAX_PATH];   // 260 字节缓冲区
    int len = 0;

    // 1. 安全复制路径到 zipPath（手动拷贝，不依赖 CRT）
    while (path[len] != '\0' && len < MAX_PATH - 1) {
        zipPath[len] = path[len];
        len++;
    }
    zipPath[len] = '\0';

    // 2. 长度不足 4 或长度已超过 MAX_PATH-4（防止截断后误判）
    if (len <= 4 || len >= MAX_PATH - 4) {
        return path;   // 无法安全替换，返回原路径
    }

    // 3. 忽略大小写检查最后 4 个字符是否为 .pak 或 .PAK 等组合
    if (zipPath[len - 4] != '.' ||
        (zipPath[len - 3] != 'p' && zipPath[len - 3] != 'P') ||
        (zipPath[len - 2] != 'a' && zipPath[len - 2] != 'A') ||
        (zipPath[len - 1] != 'k' && zipPath[len - 1] != 'K'))
    {
        return path;
    }

    // 4. 替换扩展名为 .zip（不修改原字符串，只改 zipPath 缓冲区）
    zipPath[len - 4] = '.';
    zipPath[len - 3] = 'z';
    zipPath[len - 2] = 'i';
    zipPath[len - 1] = 'p';

    // 5. 检查 .zip 文件是否存在
    if (GetFileAttributesA(zipPath) == INVALID_FILE_ATTRIBUTES)
        return path;   // 不存在则使用原 .pak

    return zipPath;    // 存在则使用 .zip
}

// ------------------------------------------------------------
__declspec(naked) void HookEntry()
{
    __asm {
        push ebp
        mov  ebp, esp
        push ebx
        push esi
        push edi

        mov  edi, ecx               // 保存流对象 this

        // 取原路径并检查是否替换
        mov  eax, [ebp+8]           // eName 对象指针
        mov  eax, [eax+4]           // 原路径指针
        push eax
        call CheckAndReplaceExt
        mov  ebx, eax               // ebx = 新路径（可能与原路径相同）

        mov  eax, [ebp+8]
        mov  eax, [eax+4]           // 重新获取原路径指针
        cmp  ebx, eax
        jne  use_custom

        // 路径相同 → 跳转原始函数
        mov  ecx, edi
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        jmp  dword ptr [pOrigFunc]

use_custom:
        // 1. 调用基类构造函数 (IAT 间接)
        mov  ecx, edi               // this
        mov  eax, g_CtorIAT         // IAT 条目地址
        call dword ptr [eax]        // 调用 eFileStream::eFileStream

        // 2. 修改 eName 对象中的路径指针为 zip 路径
        mov  eax, [ebp+8]           // eName 对象指针
        mov  [eax+4], ebx           // 替换路径指针

        // 3. 调用 Open(this, eName, flags, bufsize) (IAT 间接)
        push dword ptr [ebp+14h]    // a5 (bufsize)
        push dword ptr [ebp+10h]    // a4 (flags)
        push eax                    // eName 对象
        mov  ecx, edi               // this
        mov  eax, g_OpenIAT         // IAT 条目地址
        call dword ptr [eax]        // 调用 eFileStream::Open

        // 4. 返回流对象 this
        mov  eax, edi

        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret  10h
    }
}

// ------------------------------------------------------------
void InstallHook()
{
    DWORD oldProt;
    // 修改目标地址处的 5 字节指令为 jmp relative
    VirtualProtect((LPVOID)CALL_ORIG_INSTR_ADDR, 5, PAGE_EXECUTE_READWRITE, &oldProt);
    DWORD rel = (DWORD)HookEntry - (CALL_ORIG_INSTR_ADDR + 5);
    *(DWORD*)((BYTE*)CALL_ORIG_INSTR_ADDR + 1) = rel;
    VirtualProtect((LPVOID)CALL_ORIG_INSTR_ADDR, 5, oldProt, &oldProt);
}

// ------------------------------------------------------------
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    if (ul_reason_for_call == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(hModule);
        InstallHook();
    }
    return TRUE;
}