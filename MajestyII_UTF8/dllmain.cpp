// MajestyIIExtend - 合并字库修复 + 文本替换的 DLL（UTF-8 版）
// 基于 MJ2_fontfix (1078行) 和 MJ2_TextsHook_nolog (200行) 重构
//
// 核心改进（相对原版 GBK 方案）：
// 1. 状态机改为 UTF-8 3字节解码：1110xxxx 10xxxxxx 10xxxxxx → Unicode 码点
// 2. charlist 改为 Unicode 码点数组（顺序与原版 GBK 完全一致 → 字形索引不变）
// 3. 字典支持 UTF-8（带/不带 BOM），同时兼容原 GBK 词典
// 4. 零宽字形补丁：修补 fallback 字形宽度，消除 UTF-8 前缀字节产生的间隙
//
// 字库映射原理：
//   UTF-8 中文 = 3 字节 (E0-EF)(80-BF)(80-BF)，解码为 Unicode 码点 U+4E00~U+9FFF
//   状态机 3 个状态：等待 lead → 等待 byte2 → 等待 byte3 → 组合查表
//   前两个字节返回 fallback（宽度清零），第三个字节返回实际字形索引
//
// 状态机与 wrapper 参数约定（对齐原版已编译 DLL 反汇编验证）：
//   子函数 sub_700036A0:
//     [esp+4]  = arg1 (字形索引 + 0x20)
//     [esp+8]  = arg2 (状态指针)
//     edx      = b1 存储指针
//   返回 eax = 字形索引 - 0x20
//
//   原版: arg2 = &adderN, edx = &adderN+1 (flag 和 lead 相邻字节)
//   本版: arg2 = &g_stateN[0] (flag), edx = &g_stateN[4] (b1, DWORD)
//   状态布局: [0]=flag(BYTE), [4]=b1(DWORD), [8]=b2(DWORD)
//   因为 UTF-8 首字节 0xE0~0xEF + 0x20 = 0x100~0x10F 溢出 8 位，必须存完整 DWORD

#include "pch.h"
#include <windows.h>
#include "charlist_data.h"

// ============================================================
// 全局状态（3 对，对应 4 个 hook 点）
// ============================================================
// [0]=flag, [4]=b1, [8]=b2
BYTE g_state1[12] = {0,0,0,0, 0,0,0,0, 0,0,0,0};   // hook 1 主渲染
BYTE g_state2[12] = {0,0,0,0, 0,0,0,0, 0,0,0,0};   // hook 2 宽度缓存
BYTE g_state3[12] = {0,0,0,0, 0,0,0,0, 0,0,0,0};   // hook 3&4 渲染

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

// GBK → UTF-8 转换（HeapAlloc 返回，调用者释放）
static char* GbkToUtf8(const char* gbk, int len) {
    int wlen = MultiByteToWideChar(CP_ACP, 0, gbk, len, NULL, 0);
    if (wlen <= 0) return NULL;
    wchar_t* w = (wchar_t*)HeapAlloc(GetProcessHeap(), 0, (wlen + 1) * sizeof(wchar_t));
    if (!w) return NULL;
    MultiByteToWideChar(CP_ACP, 0, gbk, len, w, wlen);
    w[wlen] = 0;
    int ulen = WideCharToMultiByte(CP_UTF8, 0, w, wlen, NULL, 0, NULL, NULL);
    char* out = (char*)HeapAlloc(GetProcessHeap(), 0, ulen + 1);
    if (out) {
        WideCharToMultiByte(CP_UTF8, 0, w, wlen, out, ulen, NULL, NULL);
        out[ulen] = 0;
    }
    HeapFree(GetProcessHeap(), 0, w);
    return out;
}

static void LoadDict(void) {
    HANDLE h = CreateFileA(DICT_FILE, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return;

    DWORD sz = GetFileSize(h, NULL);
    if (sz == 0 || sz == 0xFFFFFFFF) { CloseHandle(h); return; }
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
        toFree = GbkToUtf8(buf, (int)sz);
        if (toFree) src = toFree;
    }
    if ((BYTE)src[0] == 0xEF && (BYTE)src[1] == 0xBB && (BYTE)src[2] == 0xBF)
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
        int vlen = (int)strlen(val);
        char* copy = (char*)HeapAlloc(GetProcessHeap(), 0, vlen + 1);
        if (copy) {
            memcpy(copy, val, vlen + 1);
            HashInsert(crc, copy);
        }
    }
    if (toFree) HeapFree(GetProcessHeap(), 0, toFree);
    HeapFree(GetProcessHeap(), 0, buf);
}

static char* FindTextByKey(const char* key) {
    if (!key) return NULL;
    DWORD crc = CalcCRC32(key);
    EnterCriticalSection(&g_cs);
    char* res = HashFind(crc);
    LeaveCriticalSection(&g_cs);
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
        mov  ecx, [esp+0x24 + 16]
        push ecx
        call FindTextByKey
        add  esp, 4              ; 清理 cdecl 参数 (push ecx)
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
// FontFix - UTF-8 三字节解码状态机
// ============================================================
// sub_700036A0 (naked)
// 参数: [esp+4]=arg1(字节+0x20), [esp+8]=arg2(状态指针), edx=b1指针
// 返回: eax = 字形索引 - 0x20
//
// 状态布局: [flag(BYTE)][b1(DWORD)][b2(DWORD)]
//   state=0: 字节<=0xA0 → ASCII 返回字节; 字节>0xA0 → 存 b1, state=1, 返回 0xDF
//   state=1: 存 b2, state=2, 返回 0xDF
//   state=2: 组合 UTF-8 码点, 查 charlist, 返回 index+0x100-0x20
//   (首字节 0xE0~0xEF + 0x20 = 0x100~0x10F, 必须存完整 DWORD)
//
// 解码: codepoint = ((b1-0x20)&0x0F)<<12 | ((b2-0x20)&0x3F)<<6 | ((b3-0x20)&0x3F)
//   其中 b3 = arg1(当前字节+0x20); b1/b2 存的是 arg1 (字节+0x20)

__declspec(naked) void sub_700036A0()
{
    __asm {
        mov ecx,[esp+8]        ; arg2 = 状态指针
        mov eax,[esp+4]        ; arg1 = 字节+0x20
        cmp byte ptr [ecx],0
        push ebx
        je _caseState0         ; state=0
        cmp byte ptr [ecx],1
        je _caseState1         ; state=1 → 等第二字节
        ; ---- state=2: 第三字节组合 ----
        ; b1 = [edx] (DWORD), b2 = [edx+4] (DWORD), b3 = eax
        ; codepoint = ((b1-0x20)&0x0F)<<12 | ((b2-0x20)&0x3F)<<6 | ((b3-0x20)&0x3F)
        movzx ebx, byte ptr [edx]     ; b1 低字节
        sub ebx, 0x20
        and ebx, 0x0F
        shl ebx, 12
        movzx ecx, byte ptr [edx+4]   ; b2 低字节
        sub ecx, 0x20
        and ecx, 0x3F
        shl ecx, 6
        or  ebx, ecx
        movzx ecx, al
        sub ecx, 0x20
        and ecx, 0x3F
        or  ebx, ecx                  ; ebx = Unicode 码点
        ; 搜索 charlist
        mov ecx,g_pCharlist
        xor eax,eax
_search:
        cmp bx, word ptr [ecx+eax]
        je _found
        add eax,2
        cmp word ptr [ecx+eax],0
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
        mov eax,0x100          ; 未找到 → 0x100 (第一个中文字形)
        mov byte ptr [edx],0
        sub eax,0x20
        pop ebx
        ret
_caseState1:
        ; 第二字节: 存 b2 = arg1, state=2
        mov [edx+4], eax
        mov ecx,[esp+12]       ; 重新加载状态指针
        mov byte ptr [ecx],2
        mov eax,0xDF           ; fallback 字形 0xFF（0xFF-0x20=0xDF）
                                ; 与 lead byte 相同。不能返回 0（渲染循环会把字符值0当终止符/死循环）
        pop ebx
        ret
_caseState0:
        cmp eax,0xA0
        jbe _leave             ; 字节 <= 0x80 → ASCII
        mov byte ptr [ecx],1   ; state=1
        mov [edx],eax          ; 存 b1 = arg1 (完整 DWORD)
        mov eax,0xFF           ; 返回 0xFF，然后跳 _leave 减 0x20 = 0xDF
_leave:
        sub eax,0x20
        pop ebx
        ret
    }
}

// ============================================================
// FontFix - 4 个 Hook Wrapper 函数
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
        push offset g_state1
        push eax
        mov edx, offset g_state1+4   ; b1 指针
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
        push offset g_state2
        push eax
        mov edx, offset g_state2+4
        call sub_700036A0
        add esp,8
        cmp eax,0xFF
        jne _skip
        ; 原版此分支（死代码，与二进制验证一致）
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
        push offset g_state3
        push eax
        mov edx, offset g_state3+4
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
    PatchWord(0x7E1A2F, 0x9090);
    HookJmp(0x775939, (DWORD)texts_hook);
    HookCall(0x7D95F7, (DWORD)sub_70003870);
    HookCall(0x7D9DAA, (DWORD)sub_70003870);
    HookCall(0x7E1A53, (DWORD)sub_70003810);
    HookCall(0x7E235D, (DWORD)sub_700037A0);
}

// ============================================================
// 零宽字形补丁
// ============================================================
// fallback 字形 @ 0xA0D7F8 (32字节), 宽度 = [0x18]-[0]
// 0xA0D7F8+0x18 = 0xA0D810: 1.0f → 0.0f，UTF-8 前缀字节零宽

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
        ApplyZeroWidthPatch();  // patch fallback 字形宽度为 0，消除 UTF-8 前缀字节的 fallback 宽字形（超大横线）
                                // 不能改状态机返回 0（渲染循环把字符值0当终止符→卡死），只能让 fallback 字形零宽
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