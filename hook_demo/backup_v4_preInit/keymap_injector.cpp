/**
 * LDPlayer Keymap Switch Injector v3
 *
 * Command modes (after HookStub stack-layout fix):
 *   keymap_injector.exe <target.kmp>       DEFAULT  - modeFlags=3, one Ctrl+F
 *                                                    CALL hook replaces arg=0
 *                                                    with &targetPath, CFW hook
 *                                                    redirects .kmp read.
 *   keymap_injector.exe --loop <target.kmp> FALLBACK - modeFlags=0, cycle Ctrl+F
 *                                                    relying on LDPlayer native
 *                                                    next-keymap rotation until
 *                                                    the requested .kmp matches.
 *   keymap_injector.exe --direct <target.kmp> DIAG   - modeFlags=3, CreateRemoteThread
 *                                                    direct call (does not trigger
 *                                                    .kmp reload; diagnostic only).
 *   keymap_injector.exe --status             STATUS  - print diagnostics and exit.
 *
 * Build:
 *   call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"
 *   cl /O2 /MT keymap_injector.cpp /Fekeymap_injector.exe
 */

#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>

#pragma comment(lib, "user32.lib")

#define SHARED_MEM_NAME  L"LDKeymapSwitch_Mem"
#define SWITCH_EXPORT    "CallSwitchKeymap"
#define SWITCH_EXPORT_DECORATED "_CallSwitchKeymap@4"

struct SharedData {
    DWORD  magic;
    char   targetPath[1024];
    DWORD  flags;
    WCHAR  fullPath[1024];
    DWORD  savedInstance;
    DWORD  funcAddress;
    DWORD  hookStatus;
    DWORD  hookCount;
    DWORD  lastThis;
    DWORD  lastOriginalArg;
    DWORD  lastReplacementArg;
    DWORD  lastHookEsp;
    DWORD  callTarget;
    DWORD  cfwKmpCount;
    DWORD  cfwRedirectCount;
    WCHAR  lastKmpPath[1024];
    WCHAR  lastRequestedKmpPath[1024];
    DWORD  kmpHistoryCount;
    WCHAR  kmpHistory[8][260];
    DWORD  kmpHistoryRedirected[8];
};

static SharedData* OpenSharedMem();

static void PrintDiagnostics(const SharedData* p) {
    printf("HookStatus: 0x%08X", p->hookStatus);
    if ((p->hookStatus & 0x1F) == 0x1E) {
        printf(" (core loaded, call verified, hook installed)");
    }
    printf("\n");
    printf("FuncAddress: 0x%08X  DecodedCallTarget: 0x%08X\n",
        p->funcAddress, p->callTarget);
    printf("HookCount: %u  LastThis: 0x%08X\n", p->hookCount, p->lastThis);
    printf("LastOriginalArg: 0x%08X  LastReplacementArg: 0x%08X  LastHookEsp: 0x%08X\n",
        p->lastOriginalArg, p->lastReplacementArg, p->lastHookEsp);
    printf("CreateFileW .kmp count: %u  redirects: %u\n",
        p->cfwKmpCount, p->cfwRedirectCount);
    if (p->lastRequestedKmpPath[0]) printf("Last requested .kmp path: %ws\n", p->lastRequestedKmpPath);
    if (p->lastKmpPath[0]) printf("Last redirected .kmp path: %ws\n", p->lastKmpPath);
    if (p->kmpHistoryCount > 0) {
        printf(".kmp read history (%u entries):\n", p->kmpHistoryCount);
        for (DWORD i = 0; i < p->kmpHistoryCount && i < 8; i++) {
            printf("  [%u] %ws %s\n", i, p->kmpHistory[i],
                p->kmpHistoryRedirected[i] ? "(REDIRECTED)" : "");
        }
    }
}

// ── Find LDPlayer process ─────────────────────
static DWORD FindLDPlayerPID() {
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnap == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32W pe = { sizeof(PROCESSENTRY32W) };
    DWORD pid = 0;
    if (Process32FirstW(hSnap, &pe)) {
        do {
            // Support both overseas (dnplayer.exe) and domestic (dnplayer.exe / dnplayer2.exe)
            if (_wcsicmp(pe.szExeFile, L"dnplayer.exe") == 0 ||
                _wcsicmp(pe.szExeFile, L"dnplayer2.exe") == 0 ||
                _wcsicmp(pe.szExeFile, L"ldplayer.exe") == 0) {
                pid = pe.th32ProcessID;
                break;
            }
        } while (Process32NextW(hSnap, &pe));
    }
    CloseHandle(hSnap);
    return pid;
}

// ── Find HWND ─────────────────────────────────
static HWND FindLDPlayerHWND(DWORD pid) {
    struct Ctx { HWND hwnd; HWND fallback; DWORD pid; } ctx = { NULL, NULL, pid };
    EnumWindows([](HWND hwnd, LPARAM lp) -> BOOL {
        Ctx* p = (Ctx*)lp;
        DWORD pid; GetWindowThreadProcessId(hwnd, &pid);
        if (pid == p->pid && IsWindowVisible(hwnd)) {
            wchar_t cls[64]; GetClassNameW(hwnd, cls, 64);
            wchar_t title[256]; GetWindowTextW(hwnd, title, 256);
            if (cls[0] == L'L' && cls[1] == 0) { p->hwnd = hwnd; return FALSE; }
            if (!p->fallback && title[0]) p->fallback = hwnd;
        }
        return TRUE;
    }, (LPARAM)&ctx);
    return ctx.hwnd ? ctx.hwnd : ctx.fallback;
}

static void SendCtrlF(HWND hwnd) {
    // Method 1: PostMessage (works even if window is not foreground)
    if (hwnd) {
        ShowWindow(hwnd, SW_RESTORE);
        // Try to bring to foreground
        DWORD fgThread = GetWindowThreadProcessId(GetForegroundWindow(), NULL);
        DWORD targetThread = GetWindowThreadProcessId(hwnd, NULL);
        if (fgThread != targetThread) {
            AttachThreadInput(targetThread, fgThread, TRUE);
        }
        SetForegroundWindow(hwnd);
        Sleep(200);
        // Send Ctrl+F via PostMessage
        PostMessageW(hwnd, WM_KEYDOWN, VK_CONTROL, 0x001D0001);
        PostMessageW(hwnd, WM_KEYDOWN, 'F', 0x00210001);
        Sleep(50);
        PostMessageW(hwnd, WM_KEYUP, 'F', 0xC0210001);
        PostMessageW(hwnd, WM_KEYUP, VK_CONTROL, 0xC01D0001);
        if (fgThread != targetThread) {
            AttachThreadInput(targetThread, fgThread, FALSE);
        }
        Sleep(300);
    }

    // Method 2: SendInput (backup, needs foreground)
    INPUT in[4] = {};
    for (int i = 0; i < 4; ++i) in[i].type = INPUT_KEYBOARD;
    in[0].ki.wVk = VK_CONTROL;
    in[1].ki.wVk = 'F';
    in[2].ki.wVk = 'F';        in[2].ki.dwFlags = KEYEVENTF_KEYUP;
    in[3].ki.wVk = VK_CONTROL; in[3].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(4, in, sizeof(INPUT));
}

static const wchar_t* BaseName(const wchar_t* path) {
    const wchar_t* slash = wcsrchr(path, L'\\');
    return slash ? slash + 1 : path;
}

static bool SameFileName(const wchar_t* a, const wchar_t* b) {
    return _wcsicmp(BaseName(a), BaseName(b)) == 0;
}

static int CountSiblingKeymaps(const wchar_t* kmpPath) {
    wchar_t dir[MAX_PATH], pattern[MAX_PATH], prefix[MAX_PATH];
    wcscpy_s(dir, MAX_PATH, kmpPath);
    wchar_t* slash = wcsrchr(dir, L'\\');
    if (!slash) return 8;
    *slash = 0;

    const wchar_t* name = slash + 1;
    const wchar_t* us = wcschr(name, L'_');
    if (!us) return 8;
    size_t prefixLen = us - name;
    wcsncpy_s(prefix, MAX_PATH, name, prefixLen);
    prefix[prefixLen] = 0;

    swprintf_s(pattern, MAX_PATH, L"%s\\%s_*.kmp", dir, prefix);

    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE) return 8;

    int count = 0;
    do {
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) count++;
    } while (FindNextFileW(h, &fd));
    FindClose(h);

    if (count < 1) count = 1;
    if (count > 32) count = 32;
    return count;
}

static bool TriggerUntilRequested(HWND hwnd, const wchar_t* targetKmp) {
    int maxPresses = CountSiblingKeymaps(targetKmp) + 1;
    for (int i = 0; i < maxPresses; ++i) {
        printf("\n--- Trigger Ctrl+F on GUI thread (%d/%d) ---\n", i + 1, maxPresses);

        DWORD beforeCount = 0;
        DWORD beforeRedirect = 0;
        SharedData* before = OpenSharedMem();
        if (before) {
            beforeCount = before->cfwKmpCount;
            beforeRedirect = before->cfwRedirectCount;
            UnmapViewOfFile(before);
        }

        SendCtrlF(hwnd);
        Sleep(1000);

        SharedData* p = OpenSharedMem();
        if (!p) return false;
        PrintDiagnostics(p);

        bool sawNewRead = p->cfwKmpCount != beforeCount;
        bool matched = sawNewRead && SameFileName(p->lastRequestedKmpPath, targetKmp);
        UnmapViewOfFile(p);

        if (matched) {
            printf("Target keymap requested by LDPlayer; stopping.\n");
            return true;
        }
    }

    printf("Target keymap was not requested within one full cycle.\n");
    return false;
}

// Trigger exactly one Ctrl+F and verify the CALL hook + CFW redirect chain
// consumed the target. This is the default path after the HookStub fix:
// modeFlags=3 makes the CALL hook replace arg=0 with &targetPath, and the
// CFW hook redirects the subsequent .kmp read to fullPath.
static bool TriggerOnceAndVerify(HWND hwnd, const wchar_t* targetKmp) {
    DWORD beforeHook = 0, beforeKmp = 0, beforeRedirect = 0;
    SharedData* before = OpenSharedMem();
    if (before) {
        beforeHook = before->hookCount;
        beforeKmp = before->cfwKmpCount;
        beforeRedirect = before->cfwRedirectCount;
        UnmapViewOfFile(before);
    }

    printf("\n--- Trigger one Ctrl+F (CALL hook + CFW redirect) ---\n");
    SendCtrlF(hwnd);
    Sleep(1000);

    SharedData* p = OpenSharedMem();
    if (!p) { printf("Shared memory lost.\n"); return false; }
    PrintDiagnostics(p);

    bool hookFired = p->hookCount != beforeHook;
    bool kmpRead = p->cfwKmpCount != beforeKmp;
    bool redirected = p->cfwRedirectCount != beforeRedirect;
    bool pathMatch = redirected && SameFileName(p->lastKmpPath, targetKmp);
    // CRITICAL: disable redirect now that the Ctrl+F cycle is complete, so
    // subsequent Ctrl+F / F12 operations read the real .kmp files unaffected.
    // (Strategy v2 does not clear bit0 inside the hook so that reads [1] and
    // [2] both get redirected; we must turn it off here.)
    p->flags &= ~1u;
    UnmapViewOfFile(p);

    printf("\n[");
    printf(hookFired  ? "x" : " ");
    printf("] CALL hook fired      ");
    printf(kmpRead    ? "x" : " ");
    printf("] .kmp read attempted  ");
    printf(redirected ? "x" : " ");
    printf("] CFW redirected       ");
    printf(pathMatch  ? "x" : " ");
    printf("] redirected to target\n");

    if (pathMatch) {
        printf("SUCCESS: target .kmp delivered to setKeyboardConfig.\n");
        return true;
    }
    if (hookFired && !kmpRead) {
        printf("NOTE: hook fired but no .kmp read. setKeyboardConfig may not have\n");
        printf("      honoured the filename arg, or the file lookup failed.\n");
    }
    if (kmpRead && !redirected) {
        printf("NOTE: .kmp read happened but was not redirected. Check fullPath\n");
        printf("      exists and CFW flag (bit0) is set.\n");
    }
    return false;
}

// ── Inject DLL ────────────────────────────────
static bool InjectDLL(DWORD pid, const wchar_t* dllPath) {
    HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!hProcess) { printf("OpenProcess failed (%d)\n", GetLastError()); return false; }

    size_t sz = (wcslen(dllPath) + 1) * sizeof(wchar_t);
    void* mem = VirtualAllocEx(hProcess, NULL, sz, MEM_COMMIT, PAGE_READWRITE);
    if (!mem) { printf("VirtualAllocEx failed (%d)\n", GetLastError()); CloseHandle(hProcess); return false; }

    if (!WriteProcessMemory(hProcess, mem, dllPath, sz, NULL)) {
        printf("WriteProcessMemory failed (%d)\n", GetLastError());
        VirtualFreeEx(hProcess, mem, 0, MEM_RELEASE);
        CloseHandle(hProcess); return false;
    }

    FARPROC loadLibW = GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW");
    HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0,
        (LPTHREAD_START_ROUTINE)loadLibW, mem, 0, NULL);
    if (!hThread) { printf("CreateRemoteThread failed (%d)\n", GetLastError()); VirtualFreeEx(hProcess, mem, 0, MEM_RELEASE); CloseHandle(hProcess); return false; }

    WaitForSingleObject(hThread, INFINITE);
    DWORD ec = 0; GetExitCodeThread(hThread, &ec);
    CloseHandle(hThread);
    VirtualFreeEx(hProcess, mem, 0, MEM_RELEASE);
    CloseHandle(hProcess);
    printf("Injection result: 0x%08X\n", ec);
    return (ec != 0);
}

// ── Shared memory helpers ─────────────────────
static SharedData* OpenSharedMem() {
    HANDLE hMap = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, SHARED_MEM_NAME);
    if (!hMap) return NULL;
    SharedData* p = (SharedData*)MapViewOfFile(hMap, FILE_MAP_ALL_ACCESS, 0, 0, 0);
    CloseHandle(hMap);
    return p;
}

static bool SetTargetKMP(const wchar_t* kmpPath, DWORD modeFlags) {
    SharedData* p = OpenSharedMem();
    if (!p) { printf("Shared memory not found.\n"); return false; }
    const wchar_t* name = wcsrchr(kmpPath, L'\\');
    name = name ? name + 1 : kmpPath;
    wcstombs_s(NULL, p->targetPath, 1024, name, _TRUNCATE);
    wcscpy_s(p->fullPath, 1024, kmpPath);
    p->flags = (p->flags & ~3u) | (modeFlags & 3u);
    p->magic = 0x4B4D5053;
    p->kmpHistoryCount = 0;  // reset history so the redirect strategy restarts
    printf("Filename: %s\n", p->targetPath);
    printf("ModeFlags: 0x%08X\n", p->flags & 3u);
    printf("SavedInstance: 0x%08X\n", p->savedInstance);
    PrintDiagnostics(p);
    UnmapViewOfFile(p);
    return true;
}

// ── Call SwitchKeymap via CreateRemoteThread ──
static bool CallSwitchKeymapRemote(DWORD pid, const wchar_t* dllPath) {
    HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!hProcess) { printf("OpenProcess failed (%d)\n", GetLastError()); return false; }

    // Load DLL locally to find export RVA
    HMODULE hLocal = LoadLibraryW(dllPath);
    if (!hLocal) { printf("Local LoadLibraryW failed (%d)\n", GetLastError()); CloseHandle(hProcess); return false; }

    FARPROC pfn = GetProcAddress(hLocal, SWITCH_EXPORT);
    if (!pfn) pfn = GetProcAddress(hLocal, SWITCH_EXPORT_DECORATED);
    if (!pfn) {
        printf("GetProcAddress failed (%d)\n", GetLastError());
        FreeLibrary(hLocal); CloseHandle(hProcess); return false;
    }

    DWORD rva = (DWORD)(uintptr_t)pfn - (DWORD)(uintptr_t)hLocal;
    FreeLibrary(hLocal);

    // Find DLL base in target process via module snapshot
    DWORD dllBase = 0;
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
    if (hSnap != INVALID_HANDLE_VALUE) {
        MODULEENTRY32W me = { sizeof(MODULEENTRY32W) };
        if (Module32FirstW(hSnap, &me)) {
            do {
                if (wcsstr(me.szModule, L"keymap_hook") != NULL ||
                    wcsstr(me.szExePath, L"keymap_sw") != NULL) {
                    dllBase = (DWORD)(uintptr_t)me.modBaseAddr;
                    break;
                }
            } while (Module32NextW(hSnap, &me));
        }
        CloseHandle(hSnap);
    }

    if (!dllBase) {
        printf("Could not find keymap_hook.dll in target process.\n");
        CloseHandle(hProcess); return false;
    }

    void* pfnTarget = (void*)(uintptr_t)(dllBase + rva);
    printf("DLL base in target: 0x%08X, Export: 0x%p\n", dllBase, pfnTarget);

    HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0,
        (LPTHREAD_START_ROUTINE)pfnTarget, NULL, 0, NULL);
    if (!hThread) { printf("CreateRemoteThread failed (%d)\n", GetLastError()); CloseHandle(hProcess); return false; }

    printf("Waiting for SwitchKeymap...\n");
    DWORD wr = WaitForSingleObject(hThread, 5000);
    if (wr == WAIT_OBJECT_0) {
        DWORD ec = 0; GetExitCodeThread(hThread, &ec);
        printf("SwitchKeymap exit code: %u\n", ec);
        CloseHandle(hThread); CloseHandle(hProcess);
        return true;
    } else {
        printf("Wait result: %u (error %d)\n", wr, GetLastError());
        if (wr == WAIT_TIMEOUT) TerminateThread(hThread, 0);
        CloseHandle(hThread); CloseHandle(hProcess);
        return false;
    }
}

// ── Main ──────────────────────────────────────
int wmain(int argc, wchar_t* argv[]) {
    if (argc < 2) {
        printf("LDPlayer Keymap Switch Injector v3\n");
        printf("Usage:\n");
        printf("  keymap_injector.exe init                  (pre-inject DLL for fast switching)\n");
        printf("  keymap_injector.exe <target.kmp>         (default: hook + one Ctrl+F)\n");
        printf("  keymap_injector.exe --loop <target.kmp>  (fallback: cycle Ctrl+F)\n");
        printf("  keymap_injector.exe --direct <target.kmp>(diag: CreateRemoteThread)\n");
        printf("  keymap_injector.exe --status             (print diagnostics only)\n");
        return 1;
    }

    enum class Mode { Default, Loop, Direct, Status, Init };
    Mode mode = Mode::Default;

    if (wcscmp(argv[1], L"init") == 0 || wcscmp(argv[1], L"--init") == 0) {
        mode = Mode::Init;
    } else if (wcscmp(argv[1], L"--status") == 0) {
        mode = Mode::Status;
    } else if (argc >= 3 && wcscmp(argv[1], L"--loop") == 0) {
        mode = Mode::Loop; argv[1] = argv[2];
    } else if (argc >= 3 && wcscmp(argv[1], L"--direct") == 0) {
        mode = Mode::Direct; argv[1] = argv[2];
    } else if (argv[1][0] == L'-' && argv[1][1] == L'-') {
        printf("Unknown option: %ws\n", argv[1]);
        return 1;
    }

    // init: pre-inject DLL so subsequent commands are fast (no 2s wait)
    if (mode == Mode::Init) {
        DWORD pid = FindLDPlayerPID();
        if (!pid) { printf("LDPlayer not running!\n"); return 1; }
        wchar_t dllPath[MAX_PATH];
        GetModuleFileNameW(NULL, dllPath, MAX_PATH);
        wchar_t* ls = wcsrchr(dllPath, L'\\');
        if (ls) wcscpy(ls + 1, L"keymap_hook.dll");
        if (OpenSharedMem()) {
            printf("DLL already injected.\n");
        } else {
            printf("Injecting DLL: %ws\n", dllPath);
            if (!InjectDLL(pid, dllPath)) { printf("Injection failed!\n"); return 1; }
            Sleep(2000);
        }
        SharedData* p = OpenSharedMem();
        if (p) { PrintDiagnostics(p); UnmapViewOfFile(p); }
        printf("Init complete. Subsequent commands will be fast.\n");
        return 0;
    }

    // --status: just print and exit
    if (mode == Mode::Status) {
        SharedData* p = OpenSharedMem();
        if (!p) { printf("DLL not injected (shared memory not found).\n"); return 1; }
        PrintDiagnostics(p);
        UnmapViewOfFile(p);
        return 0;
    }

    // Resolve paths
    wchar_t dllPath[MAX_PATH], kmpPath[MAX_PATH];
    GetModuleFileNameW(NULL, dllPath, MAX_PATH);
    wchar_t* ls = wcsrchr(dllPath, L'\\');
    if (ls) wcscpy(ls + 1, L"keymap_hook.dll");

    wchar_t inputPath[MAX_PATH];
    if (wcschr(argv[1], L'\\') || wcschr(argv[1], L':')) {
        wcscpy_s(inputPath, MAX_PATH, argv[1]);
    } else {
        wchar_t buf[MAX_PATH];
        GetModuleFileNameW(NULL, buf, MAX_PATH);
        ls = wcsrchr(buf, L'\\');
        if (ls) wcscpy(ls + 1, argv[1]);
        wcscpy_s(inputPath, MAX_PATH, buf);
    }

    if (!GetFullPathNameW(inputPath, MAX_PATH, kmpPath, NULL)) {
        wcscpy_s(kmpPath, MAX_PATH, inputPath);
    }

    if (GetFileAttributesW(kmpPath) == INVALID_FILE_ATTRIBUTES) {
        printf("WARNING: target .kmp not found: %ws\n", kmpPath);
        printf("         CFW redirect will be skipped (GetFileAttributes fails).\n");
    }

    // Find LDPlayer
    DWORD pid = FindLDPlayerPID();
    if (!pid) { printf("LDPlayer not running!\n"); return 1; }
    HWND hwnd = FindLDPlayerHWND(pid);
    printf("LDPlayer PID=%u HWND=%p\n", pid, hwnd);

    // Check if DLL already injected
    bool alreadyInjected = (OpenSharedMem() != NULL);
    if (alreadyInjected) {
        printf("DLL already injected.\n");
    } else {
        printf("Injecting DLL: %ws\n", dllPath);
        if (!InjectDLL(pid, dllPath)) {
            printf("Injection failed!\n");
            return 1;
        }
        Sleep(2000);
    }

    // Mode flags:
    //   bit0 = CFW redirect, bit1 = CALL arg replacement
    //   Default/Direct use 3 (both on). Loop uses 0 (observe only).
    DWORD modeFlags = (mode == Mode::Loop) ? 0u : 3u;
    if (!SetTargetKMP(kmpPath, modeFlags)) return 1;

    switch (mode) {
        case Mode::Default:
            return TriggerOnceAndVerify(hwnd, kmpPath) ? 0 : 1;
        case Mode::Loop:
            return TriggerUntilRequested(hwnd, kmpPath) ? 0 : 1;
        case Mode::Direct:
            break;  // fall through to direct-call block below
        default:
            return 0;
    }

    // Direct mode is kept only for diagnostics. It does not currently
    // trigger .kmp reloads because CreateRemoteThread runs on a worker
    // thread, not the GUI message-loop thread.
    {
        SharedData* p = OpenSharedMem();
        if (!p) return 1;

        if (p->savedInstance == 0) {
            printf("No saved instance. Press Ctrl+F once in LDPlayer so the\n");
            printf("CALL hook captures CInputMgr, then rerun --direct.\n");
            PrintDiagnostics(p);
            UnmapViewOfFile(p);
            return 1;
        }
        printf("Instance found: 0x%08X\n", p->savedInstance);
        PrintDiagnostics(p);
        UnmapViewOfFile(p);
    }

    printf("\n--- Direct switch ---\n");
    if (CallSwitchKeymapRemote(pid, dllPath)) {
        printf("SwitchKeymap completed.\n");
        SharedData* p = OpenSharedMem();
        if (p) {
            PrintDiagnostics(p);
            UnmapViewOfFile(p);
        }
    } else {
        printf("SwitchKeymap failed.\n");
        return 1;
    }
    return 0;
}
