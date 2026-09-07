// Majesty 2 文本Hook - 精简版 (VC6.0 DLL)
#include <windows.h>

extern "C" void __chkstk() { return; }
#pragma comment(linker, "/align:4096")

#define DICT_FILE   "DictRead.txt"
#define HASH_SIZE   65521

typedef struct { DWORD crc32; char* text; } HashEntry;
static HashEntry g_hashTable[HASH_SIZE];
static CRITICAL_SECTION g_cs;

// 快速内存复制 (内联汇编)
static void* MyMemcpy(void* d, const void* s, size_t n) {
    __asm {
        mov edi, d
        mov esi, s
        mov ecx, n
        cld
        rep movsb
    }
    return d;
}

// 字符串长度
static int StrLen(const char* s) {
    int len = 0;
    while (s[len]) ++len;
    return len;
}

// CRC32 表
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

static DWORD CRC32(const char* str) {
    BuildCRC32Table();
    DWORD crc = 0xFFFFFFFF;
    while (*str) {
        unsigned char ch = *str++;
        crc = (crc >> 8) ^ crc32_table[(crc ^ ch) & 0xFF];
    }
    return crc ^ 0xFFFFFFFF;
}

// 哈希表操作
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

// 修剪字符串
static void Trim(char* s) {
    char* p = s;
    while (*p == ' ' || *p == '\t') p++;
    if (p != s) MyMemcpy(s, p, StrLen(p) + 1);
    int len = StrLen(s);
    while (len > 0 && (s[len-1] == ' ' || s[len-1] == '\t' || s[len-1] == '\n' || s[len-1] == '\r'))
        s[--len] = '\0';
}

// 加载字典 (流式解析，无额外数组)
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

    char* p = buf;
    while (*p) {
        // 找键行
        while (*p == '\n' || *p == '\r') p++;
        if (!*p) break;
        char* key = p;
        while (*p && *p != '\n' && *p != '\r') p++;
        if (*p) { *p = '\0'; p++; }
        // 找值行
        while (*p == '\n' || *p == '\r') p++;
        if (!*p) break;
        char* val = p;
        while (*p && *p != '\n' && *p != '\r') p++;
        if (*p) { *p = '\0'; p++; }

        Trim(key);
        Trim(val);
        if (key[0] == '\0' || val[0] == '\0') continue;

        DWORD crc = CRC32(key);
        int vlen = StrLen(val);
        char* copy = (char*)HeapAlloc(GetProcessHeap(), 0, vlen + 1);
        if (copy) {
            MyMemcpy(copy, val, vlen + 1);
            HashInsert(crc, copy);
        }
    }
    HeapFree(GetProcessHeap(), 0, buf);
}

static char* FindTextByKey(const char* key) {
    if (!key) return NULL;
    DWORD crc = CRC32(key);
    EnterCriticalSection(&g_cs);
    char* res = HashFind(crc);
    LeaveCriticalSection(&g_cs);
    return res;
}

static DWORD g_hookRetAddr = 0x0077593E;

// Hook 函数
void __declspec(naked) texts() {
    __asm {
        push ebx
        push edx
        push edi
        push ebp
        mov  ecx, [esp+0x24 + 16]
        push ecx
        call FindTextByKey
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

// 安装 Hook
static BOOL InstallHook() {
    DWORD target = 0x00775939;
    DWORD func   = (DWORD)texts;
    int rel = func - (target + 5);
    BYTE jmpCode[5] = { 0xE9, (BYTE)(rel >> 0), (BYTE)(rel >> 8), (BYTE)(rel >> 16), (BYTE)(rel >> 24) };
    DWORD oldProtect;
    VirtualProtect((LPVOID)target, 5, PAGE_EXECUTE_READWRITE, &oldProtect);
    MyMemcpy((void*)target, jmpCode, 5);
    VirtualProtect((LPVOID)target, 5, oldProtect, &oldProtect);
    return TRUE;
}

// DLL 入口
BOOL WINAPI DllMain(HMODULE h, DWORD reason, LPVOID r) {
    if (reason == DLL_PROCESS_ATTACH) {
        InitializeCriticalSection(&g_cs);
        int i;
        for (i = 0; i < HASH_SIZE; i++) g_hashTable[i].text = NULL;
        LoadDict();
        InstallHook();
    } else if (reason == DLL_PROCESS_DETACH) {
        int i;
        for (i = 0; i < HASH_SIZE; i++) {
            if (g_hashTable[i].text)
                HeapFree(GetProcessHeap(), 0, g_hashTable[i].text);
        }
        DeleteCriticalSection(&g_cs);
    }
    return TRUE;
}