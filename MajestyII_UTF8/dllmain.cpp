// MajestyIIExtend - 合并字库修复 + 文本替换的 DLL（GBK 版）
// 基于 MJ2_fontfix 原版 GBK 2字节状态机 + MJ2_TextsHook 文本替换
//
// 核心策略：
// 1. 使用原版 GBK 2字节状态机（已验证可靠，无去同步问题）
// 2. 词典加载时将 UTF-8 译文转码为 GBK 编码（WideCharToMultiByte CP_ACP）
// 3. charlist 使用原版 GBK 编码表（6996 条）
// 4. 零宽字形补丁：修补 fallback 字形宽度
//
// 为什么放弃 UTF-8 3字节状态机：
//   游戏引擎有多个独立渲染遍次（主渲染、宽度缓存等），每个遍次独立遍历文本字节
//   UTF-8 中文占 3 字节，不同遍次在字符中间交替导致状态机永远无法累积完整序列
//   GBK 中文占 2 字节，每个 hook 点能独立完成解码，所以原版方案有效
//   方案改为：词典输出 GBK 编码文本，状态机使用原版 GBK 2字节逻辑

#include "pch.h"
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include "charlist_data.h"

// ============================================================
// GBK 状态变量（6 个 BYTE，对应 3 对 hook 点，与原版完全一致）
// ============================================================
BYTE adder1=0,adder2=0,adder3=0,adder4=0,adder5=0,adder6=0;

// g_charlist[] and g_charlist_count defined in charlist_data.h
PWORD g_pCharlist = (PWORD)g_charlist;

// ============================================================
// 字典系统 (TextsHook)
// ============================================================
#define DICT_FILE   "DictRead.txt"
#define HASH_SIZE   65521

typedef struct { DWORD crc32; char* text; } HashEntry;
static HashEntry g_hashTable[HASH_SIZE];
static CRITICAL_SECTION g_cs;

static unsigned int crc32_table[256];
static int crc32_table_built = 0;

static void BuildCRC32Table(void) {
    if (crc32_table_built) return;
    unsigned int poly = 0xEDB88320;
    for (unsigned int i = 0; i < 256; i++) {
        unsigned int crc = i;
        for (int j = 0; j < 8; j++)
            crc = (crc >> 1) ^ ((crc & 1) ? poly : 0);
        crc32_table[i] = crc;
    }
    crc32_table_built = 1;
}

static DWORD CalcCRC32(const char* str) {
    BuildCRC32Table();
    DWORD crc = 0xFFFFFFFF;
    while (*str) {
        unsigned char ch = *str++;
        crc = (crc >> 8) ^ crc32_table[(crc ^ ch) & 0xFF];
    }
    return crc ^ 0xFFFFFFFF;
}

static void HashInsert(DWORD crc32, char* text) {
    unsigned int idx = crc32 % HASH_SIZE;
    while (g_hashTable[idx].text)
        idx = (idx + 1) % HASH_SIZE;
    g_hashTable[idx].crc32 = crc32;
    g_hashTable[idx].text = text;
}

static char* HashFind(DWORD crc32) {
    unsigned int idx = crc32 % HASH_SIZE;
    unsigned int start = idx;
    while (g_hashTable[idx].text) {
        if (g_hashTable[idx].crc32 == crc32)
            return g_hashTable[idx].text;
        idx = (idx + 1) % HASH_SIZE;
        if (idx == start) break;
    }
    return NULL;
}

static void Trim(char* s) {
    char* p = s;
    while (*p == ' ' || *p == '\t') p++;
    if (p != s) memmove(s, p, strlen(p) + 1);
    int len = (int)strlen(s);
    while (len > 0 && (s[len-1] == ' ' || s[len-1] == '\t' || s[len-1] == '\n' || s[len-1] == '\r'))
        s[--len] = '\0';
}

// 判断文本是否 UTF-8（BOM 或内容启发式）
static int IsLikelyUTF8(const char* buf, DWORD sz) {
    if (sz >= 3 && (BYTE)buf[0] == 0xEF && (BYTE)buf[1] == 0xBB && (BYTE)buf[2] == 0xBF)
        return 1;
    int utf8_seq = 0, other_seq = 0;
    int i = 0;
    int scan = sz > 200000 ? 200000 : (int)sz;
    while (i < scan) {
        BYTE c = (BYTE)buf[i];
        if (c < 0x80) { i++; continue; }
        if (c >= 0xC2 && c <= 0xDF) {
            if (i+1 < scan && (BYTE)buf[i+1] >= 0x80 && (BYTE)buf[i+1] <= 0xBF) {
                utf8_seq++; i += 2; continue;
            }
        } else if (c >= 0xE0 && c <= 0xEF) {
            if (i+2 < scan && (BYTE)buf[i+1] >= 0x80 && (BYTE)buf[i+1] <= 0xBF &&
                (BYTE)buf[i+2] >= 0x80 && (BYTE)buf[i+2] <= 0xBF) {
                utf8_seq++; i += 3; continue;
            }
        }
        other_seq++; i++;
    }
    return utf8_seq > other_seq;
}

// UTF-8 → GBK 转换（HeapAlloc 返回，调用者释放）
// 词典文件是 UTF-8 编码，但游戏渲染管线需要 GBK 字节流
static char* Utf8ToGbk(const char* utf8, int len) {
    int wlen = MultiByteToWideChar(CP_UTF8, 0, utf8, len, NULL, 0);
    if (wlen <= 0) return NULL;
    wchar_t* w = (wchar_t*)HeapAlloc(GetProcessHeap(), 0, (wlen + 1) * sizeof(wchar_t));
    if (!w) return NULL;
    MultiByteToWideChar(CP_UTF8, 0, utf8, len, w, wlen);
    w[wlen] = 0;
    int glen = WideCharToMultiByte(CP_ACP, 0, w, wlen, NULL, 0, NULL, NULL);
    char* out = (char*)HeapAlloc(GetProcessHeap(), 0, glen + 1);
    if (out) {
        WideCharToMultiByte(CP_ACP, 0, w, wlen, out, glen, NULL, NULL);
        out[glen] = 0;
    }
    HeapFree(GetProcessHeap(), 0, w);
    return out;
}

// ============================================================
// 调试日志
// ============================================================
static int g_dictLoaded = -1;
static int g_dictCount = 0;

static void LogWrite(const char* fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsprintf_s(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    char path[MAX_PATH] = {0};
    HMODULE hm = NULL;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)&LogWrite, &hm)) {
        GetModuleFileNameA(hm, path, MAX_PATH);
        char* slash = strrchr(path, '\\');
        if (slash) { slash[1] = '\0'; lstrcatA(path, "hook_debug.log"); }
        else { lstrcpyA(path, "update\\hook_debug.log"); }
    } else {
        lstrcpyA(path, "update\\hook_debug.log");
    }
    HANDLE h = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    SetFilePointer(h, 0, NULL, FILE_END);
    DWORD wr;
    WriteFile(h, buf, (DWORD)strlen(buf), &wr, NULL);
    CloseHandle(h);
}

static void LogHookHit(const char* key, const char* res) {
    static int count = 0;
    if (count++ < 200) {
        if (res)
            LogWrite("HIT  key=[%s] -> [%s]\n", key, res);
        else
            LogWrite("MISS key=[%s]\n", key);
    } else if (count == 201) {
        LogWrite("...(log truncated)\n");
    }
}

static void LoadDict(void) {
    char dllDir[MAX_PATH] = {0};
    HMODULE hm = NULL;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)&LoadDict, &hm)) {
        GetModuleFileNameA(hm, dllDir, MAX_PATH);
        char* slash = strrchr(dllDir, '\\');
        if (slash) { slash[1] = '\0'; }
    }

    HANDLE h = INVALID_HANDLE_VALUE;
    char fullPath[MAX_PATH];
    if (dllDir[0]) {
        lstrcpyA(fullPath, dllDir);
        lstrcatA(fullPath, DICT_FILE);
        h = CreateFileA(fullPath, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    }
    if (h == INVALID_HANDLE_VALUE)
        h = CreateFileA(DICT_FILE, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) { LogWrite("LoadDict: FAILED to open dict (dllDir=[%s])\n", dllDir); return; }

    DWORD sz = GetFileSize(h, NULL);
    if (sz == 0 || sz == 0xFFFFFFFF) { CloseHandle(h); LogWrite("LoadDict: FAILED size=%u\n", sz); return; }
    char* buf = (char*)HeapAlloc(GetProcessHeap(), 0, sz + 1);
    if (!buf) { CloseHandle(h); return; }

    DWORD rd;
    ReadFile(h, buf, sz, &rd, NULL);
    buf[sz] = '\0';
    CloseHandle(h);

    int is_utf8 = IsLikelyUTF8(buf, (int)sz);
    char* src = buf;
    char* toFree = NULL;
    if (!is_utf8) {
        // 词典已经是 GBK 编码，直接使用
        // 但仍需检查是否有 BOM
    } else {
        // UTF-8 词典：值（译文）需要转为 GBK 编码
        // 跳过 BOM
        if ((BYTE)src[0] == 0xEF && (BYTE)src[1] == 0xBB && (BYTE)src[2] == 0xBF)
            src += 3;
    }
    // 注意：is_utf8=0 时也检查 BOM（GBK 不会有 BOM，但以防万一）
    if (!is_utf8 && (BYTE)src[0] == 0xEF && (BYTE)src[1] == 0xBB && (BYTE)src[2] == 0xBF)
        src += 3;

    char* p = src;
    while (*p) {
        while (*p == '\n' || *p == '\r') p++;
        if (!*p) break;
        char* key = p;
        while (*p && *p != '\n' && *p != '\r') p++;
        if (*p) { *p = '\0'; p++; }
        while (*p == '\n' || *p == '\r') p++;
        if (!*p) break;
        char* val = p;
        while (*p && *p != '\n' && *p != '\r') p++;
        if (*p) { *p = '\0'; p++; }

        Trim(key);
        Trim(val);
        if (key[0] == '\0' || val[0] == '\0') continue;

        DWORD crc = CalcCRC32(key);

        // 如果词典是 UTF-8，将译文从 UTF-8 转为 GBK
        char* finalVal = val;
        char* gbkVal = NULL;
        if (is_utf8) {
            gbkVal = Utf8ToGbk(val, (int)strlen(val));
            if (gbkVal) finalVal = gbkVal;
        }

        int vlen = (int)strlen(finalVal);
        char* copy = (char*)HeapAlloc(GetProcessHeap(), 0, vlen + 1);
        if (copy) {
            memcpy(copy, finalVal, vlen + 1);
            HashInsert(crc, copy);
            g_dictCount++;
        }
        if (gbkVal) HeapFree(GetProcessHeap(), 0, gbkVal);
    }
    HeapFree(GetProcessHeap(), 0, buf);
    g_dictLoaded = 1;
    LogWrite("LoadDict: OK count=%d is_utf8=%d\n", g_dictCount, is_utf8);
}

static char* FindTextByKey(const char* key) {
    if (!key) { LogHookHit("(null)", NULL); return NULL; }
    char upperKey[256];
    int i;
    for (i = 0; key[i] && i < 255; i++) {
        char c = key[i];
        if (c >= 'a' && c <= 'z') c -= 32;
        upperKey[i] = c;
    }
    upperKey[i] = '\0';
    DWORD crc = CalcCRC32(upperKey);
    EnterCriticalSection(&g_cs);
    char* res = HashFind(crc);
    LeaveCriticalSection(&g_cs);
    LogHookHit(key, res);
    return res;
}

// ============================================================
// TextsHook - 文本构建循环拦截 (hook @ 0x775939)
// ============================================================
static DWORD g_hookRetAddr = 0x0077593E;

void __declspec(naked) texts_hook() {
    __asm {
        push ebx
        push edx
        push edi
        push ebp
        mov  ecx, [esp+0x6C]
        push ecx
        call FindTextByKey
        add  esp, 4
        test eax, eax
        jz   no_change
        mov  esi, eax
    no_change:
        pop  ebp
        pop  edi
        pop  edx
        pop  ebx
        movzx eax, byte ptr [esi]
        test al, al
        jmp  dword ptr [g_hookRetAddr]
    }
}

// ============================================================
// FontFix - 原版 GBK 2字节状态机
// ============================================================
// sub_700036A0 (naked) - 与原版 MJ2_fontfix.cpp 完全一致
// 参数: [esp+4]=arg1(字节+0x20), [esp+8]=arg2(状态指针), edx=adder指针
// 返回: eax = 字形索引 - 0x20
//
// GBK 状态机：
//   state=0 (flag=0): 字节<=0xA0 → ASCII; 字节>0xA0 → 存 lead, state=1, 返回 0xFF-0x20
//   state=1 (flag=1): 取 lead from [edx], 组合 (lead<<8)|trail, 查 charlist

__declspec(naked) void sub_700036A0()
{
    __asm {
        mov ecx,[esp+8]        ; arg2 = 状态指针
        mov eax,[esp+4]        ; arg1 = 字节+0x20
        cmp byte ptr [ecx],0
        push ebx
        je _caseB7            ; state=0
        ; ---- state=1: 第二字节，组合 GBK 码 ----
        mov cl,[edx]           ; lead byte (存在 adder 里)
        cmp cl,0xFF
        je _caseA9            ; 无效 lead
        movzx edx,al           ; trail byte (arg1)
        shl edx,8
        mov dl,cl             ; edx = (trail << 8) | lead → 注意字节序！
        ; 原版逻辑: 组合 (al<<8 | cl) 作为 GBK combo 查表
        ; al = arg1 = 第二字节+0x20-0x20 = 原始第二字节 (因为游戏对>0xA0的byte做signed+224=-32, wrapper +0x20, 抵消)
        ; cl = [edx] = 第一字节 (存在 adder 里)
        ; 查表: g_charlist[i] == (second<<8 | first) → 注意这里原版就是 first在低字节, second在高字节
        mov [esp+8],edx        ; 写回组合码到栈
        xor eax,eax
        mov ebx,g_pCharlist
_search:
        cmp dx,[ebx+eax]
        je _found
        add eax,2
        cmp word ptr [ebx+eax],0
        je _notFound
        jmp _search
_found:
        shr eax,1
        add eax,0x100          ; 字形索引 = position + 0x100
        mov edx,[esp+12]       ; arg2 = 状态指针
        mov byte ptr [edx],0   ; 清 state
        sub eax,0x20
        pop ebx
        ret
_notFound:
        mov edx,[esp+12]
        mov eax,0x100
        mov byte ptr [edx],0
        sub eax,0x20
        pop ebx
        ret
_caseA9:
        ; lead byte 是 0xFF → 返回 0（不渲染）
        xor eax,eax
        pop ebx
        ret
_caseB7:
        ; ---- state=0: 第一字节 ----
        cmp eax,0xA0
        jbe _leave             ; ASCII (<=0x80 after +0x20, 即原始字节<=0xA0)
        mov byte ptr [ecx],1   ; state=1
        mov [edx],al            ; 存 lead byte 到 adder
        mov eax,0xFF            ; 返回 0xFF
_leave:
        sub eax,0x20
        pop ebx
        ret
    }
}

// ============================================================
// FontFix - 4 个 Hook Wrapper 函数（与原版完全一致）
// ============================================================
// pushad 布局:
//   [esp+0x00] = edi    [esp+0x10] = ebx
//   [esp+0x04] = esi    [esp+0x14] = edx
//   [esp+0x08] = ebp    [esp+0x18] = ecx
//   [esp+0x0C] = orig   [esp+0x1C] = eax

// Hook 1: 主渲染 (0x7E235D)
__declspec(naked) void sub_70003770()
{
    __asm {
        push esi
        mov esi,[esp+8]
        mov eax,[esi]
        add eax,0x20
        push offset adder1
        push eax
        mov edx, offset adder2
        call sub_700036A0
        mov [esi],eax
        shl eax,5
        add esp,8
        mov [esi+0x1C],eax
        pop esi
        ret 4
    }
}

__declspec(naked) void sub_700037A0()
{
    __asm {
        pushad
        push esp
        call sub_70003770
        popad
        ret
    }
}

// Hook 2: 宽度缓存 (0x7e1a53)
__declspec(naked) void sub_700037B0()
{
    __asm {
        push esi
        mov esi,[esp+8]
        mov eax,[esi+0x14]
        add eax,0x20
        push offset adder3
        push eax
        mov edx, offset adder4
        call sub_700036A0
        add esp,8
        cmp eax,0xFF
        jne _skip
        mov [esi+0x14],eax
        mov ecx,[esi+0x18]
        mov edx,[ecx+0x34]
        add edx,0x3FC
        mov [esi+0x10],edx
_skip:
        shl eax,5
        mov [esi+0x1C],eax
        pop esi
        ret 4
    }
}

__declspec(naked) void sub_70003810()
{
    __asm {
        pushad
        push esp
        call sub_700037B0
        popad
        ret
    }
}

// Hook 3&4: 渲染路径 (0x7d95f7, 0x7d9daa)
__declspec(naked) void sub_70003820()
{
    __asm {
        push esi
        mov esi,[esp+8]
        mov eax,[esi]
        add eax,0x20
        push offset adder5
        push eax
        mov edx, offset adder6
        call sub_700036A0
        mov [esi],eax
        shl eax,5
        add esp,8
        mov [esi+0x18],eax
        pop esi
        ret 4
    }
}

__declspec(naked) void sub_70003870()
{
    __asm {
        pushad
        push esp
        call sub_70003820
        popad
        ret
    }
}

// ============================================================
// Hook 安装
// ============================================================
void HookCall(DWORD addr, DWORD func)
{
    DWORD op;
    BYTE *p = (BYTE*)addr;
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &op);
    *p = 0xE8;
    *(DWORD*)(p+1) = func - (DWORD)p - 5;
    VirtualProtect(p, 5, op, &op);
}

void PatchWord(DWORD addr, WORD data)
{
    DWORD op;
    BYTE *p = (BYTE*)addr;
    VirtualProtect(p, 2, PAGE_EXECUTE_READWRITE, &op);
    *(WORD*)p = data;
    VirtualProtect(p, 2, op, &op);
}

void PatchDword(DWORD addr, DWORD data)
{
    DWORD op;
    BYTE *p = (BYTE*)addr;
    VirtualProtect(p, 4, PAGE_EXECUTE_READWRITE, &op);
    *(DWORD*)p = data;
    VirtualProtect(p, 4, op, &op);
}

void HookJmp(DWORD addr, DWORD func)
{
    DWORD op;
    BYTE *p = (BYTE*)addr;
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &op);
    *p = 0xE9;
    *(DWORD*)(p+1) = func - (DWORD)p - 5;
    VirtualProtect(p, 5, op, &op);
}

static void ApplyHooks()
{
    HookCall(0x7D95F7, (DWORD)sub_70003870);
    HookCall(0x7D9DAA, (DWORD)sub_70003870);
    HookCall(0x7E1A53, (DWORD)sub_70003810);
    HookCall(0x7E235D, (DWORD)sub_700037A0);
    PatchWord(0x7E1A2F, 0x9090);
    HookJmp(0x775939, (DWORD)texts_hook);
}

// ============================================================
// 零宽字形补丁
// ============================================================
static void ApplyZeroWidthPatch()
{
    PatchDword(0xA0D810, 0x00000000);
}

// ============================================================
// DLL 入口
// ============================================================
BOOL WINAPI DllMain(HMODULE hModule, DWORD reason, LPVOID lpReserved)
{
    switch (reason)
    {
    case DLL_PROCESS_ATTACH:
        InitializeCriticalSection(&g_cs);
        for (int i = 0; i < HASH_SIZE; i++) g_hashTable[i].text = NULL;
        LoadDict();
        ApplyHooks();
        ApplyZeroWidthPatch();
        break;
    case DLL_PROCESS_DETACH:
        for (int i = 0; i < HASH_SIZE; i++) {
            if (g_hashTable[i].text)
                HeapFree(GetProcessHeap(), 0, g_hashTable[i].text);
        }
        DeleteCriticalSection(&g_cs);
        break;
    }
    return TRUE;
}
