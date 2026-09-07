import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
PROCESS_ALL_ACCESS = 0x1F0FFF

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
                ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', ctypes.c_long),
                ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_char * 260)]

hSnap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
entry = PROCESSENTRY32()
entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
pid = None
if kernel32.Process32First(hSnap, ctypes.byref(entry)):
    while True:
        name = entry.szExeFile.decode('ascii', errors='ignore')
        if 'majesty2' in name.lower():
            pid = entry.th32ProcessID
            break
        if not kernel32.Process32Next(hSnap, ctypes.byref(entry)):
            break
kernel32.CloseHandle(hSnap)
print(f"PID={pid}")

hProc = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)

# Read b1/b2 at edx = 0x66A083A4
buf = (ctypes.c_byte * 8)()
bytesRead = ctypes.c_size_t(0)
kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(0x66A083A4), buf, 8, ctypes.byref(bytesRead))
b1 = buf[0] & 0xFF
b2 = buf[4] & 0xFF
b3 = 0x98  # eax
cp = ((b1 & 0x0F) << 12) | ((b2 & 0x3F) << 6) | (b3 & 0x3F)
print(f"b1=0x{b1:02X} b2=0x{b2:02X} b3=0x{b3:02X} -> U+{cp:04X} ({chr(cp)})")

# Read g_pCharlist pointer
ptrbuf = (ctypes.c_byte * 4)()
kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(0x66A08018), ptrbuf, 4, ctypes.byref(bytesRead))
charlist_addr = int.from_bytes(bytes(ptrbuf), 'little')
print(f"g_pCharlist = 0x{charlist_addr:08X}")

# Search charlist for U+6218
target = cp
found = False
for i in range(8000):
    wbuf = (ctypes.c_byte * 2)()
    kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(charlist_addr + i*2), wbuf, 2, ctypes.byref(bytesRead))
    val = int.from_bytes(bytes(wbuf), 'little')
    if val == 0:
        print(f"End of charlist at index {i}")
        break
    if val == target:
        print(f"FOUND U+{target:04X} at charlist index {i}")
        print(f"Returned glyph index = {i} + 0x100 = 0x{i + 0x100:04X}")
        print(f"After sub 0x20: eax = 0x{i + 0x100 - 0x20:04X}")
        found = True
        break

if not found:
    print(f"U+{target:04X} NOT FOUND in charlist!")

# Show first 10 and entries around U+6218
print("First 10 charlist entries:")
for i in range(10):
    wbuf = (ctypes.c_byte * 2)()
    kernel32.ReadProcessMemory(hProc, ctypes.c_void_p(charlist_addr + i*2), wbuf, 2, ctypes.byref(bytesRead))
    val = int.from_bytes(bytes(wbuf), 'little')
    ch = chr(val) if val > 0x20 else "?"
    print(f"  [{i}] = 0x{val:04X} ({ch})")

kernel32.CloseHandle(hProc)
