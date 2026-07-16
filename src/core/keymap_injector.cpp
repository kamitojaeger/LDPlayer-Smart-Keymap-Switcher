// LDPlayer Keymap Injector v8 - Clean
// Build: cl /O2 /MT keymap_injector.cpp /Fekeymap_injector.exe /link /NOLOGO user32.lib
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
    // ── Plan B: GUI-thread piggyback switch (bypass Ctrl+F) ──
    DWORD  wmSwitchMsg;
    DWORD  guiThreadId;
    DWORD  wndprocInstalled;
    DWORD  subclassHwnd;
    DWORD  switchPending;
    DWORD  switchResult;
    DWORD  switchThreadId;
    DWORD  switchCfwBefore;
    DWORD  switchCfwAfter;
    DWORD  switchHookBefore;
    DWORD  switchHookAfter;
    DWORD  switchArgMode;        // 0=use &targetPath, 1=use 0 (cycle mode)
};

static SharedData* OpenSharedMem();
static void PrintDiagnostics(const SharedData* p);
static DWORD FindLDPlayerPID();
static HWND FindLDPlayerHWND(DWORD pid);
static DWORD FindDLLBase(DWORD pid);
static bool InjectDLL(DWORD pid, const wchar_t* dllPath);
static bool TriggerOnceAndVerify(HWND hwnd, const wchar_t* kmpPath);
static bool TriggerUntilRequested(HWND hwnd, const wchar_t* kmpPath);
static bool SetTargetKMP(const wchar_t* filename, const wchar_t* fullPath, DWORD modeFlags);
static bool CallSwitchKeymapRemote(DWORD pid, const wchar_t* dllPath);
static bool CallExportRemote(DWORD pid, const wchar_t* dllPath, const char* exportName, const char* decoratedName);

int wmain(int argc, wchar_t* argv[]) {
    SetConsoleOutputCP(CP_UTF8);
    
    if (argc < 2) {
        printf("Usage:\n");
        printf("  keymap_injector.exe init                    Install hooks\n");
        printf("  keymap_injector.exe <target.kmp>            Default: Ctrl+F + CALL hook\n");
        printf("  keymap_injector.exe --loop <target.kmp>     Loop mode: hold Ctrl+F\n");
        printf("  keymap_injector.exe --direct <target.kmp>   Direct: CreateRemoteThread\n");
        printf("  keymap_injector.exe --gui <target.kmp>       GUI-thread: WndProc dispatch (no Ctrl+F)\n");
        printf("  keymap_injector.exe --status                Print diagnostics\n");
        return 1;
    }

    const wchar_t* kmpPath = NULL;
    enum class Mode { Default, Loop, Direct, Status, Init, Gui, GuiCycle };
    Mode mode = Mode::Default;

    if (wcscmp(argv[1], L"init") == 0) {
        mode = Mode::Init;
    } else if (wcscmp(argv[1], L"--status") == 0) {
        mode = Mode::Status;
    } else if (argc >= 3 && wcscmp(argv[1], L"--loop") == 0) {
        mode = Mode::Loop; kmpPath = argv[2];
    } else if (argc >= 3 && wcscmp(argv[1], L"--direct") == 0) {
        mode = Mode::Direct; kmpPath = argv[2];
    } else if (argc >= 3 && wcscmp(argv[1], L"--gui") == 0) {
        mode = Mode::Gui; kmpPath = argv[2];
    } else if (argc >= 3 && wcscmp(argv[1], L"--gui-cycle") == 0) {
        mode = Mode::GuiCycle; kmpPath = argv[2];
    } else if (argv[1][0] == L'-' && argv[1][1] == L'-') {
        printf("Unknown option: %ws\n", argv[1]); return 1;
    } else {
        kmpPath = argv[1];
    }

    DWORD pid = FindLDPlayerPID();
    if (!pid) { printf("dnplayer.exe not found.\n"); return 1; }

    // Build DLL path relative to EXE
    wchar_t exeDir[MAX_PATH], dllPath[MAX_PATH];
    GetModuleFileNameW(NULL, exeDir, MAX_PATH);
    wchar_t* lastSlash = wcsrchr(exeDir, L'\\');
    if (lastSlash) *lastSlash = 0;
    swprintf(dllPath, MAX_PATH, L"%s\\keymap_hook.dll", exeDir);

    // Status mode – just print diagnostics
    if (mode == Mode::Status) {
        SharedData* p = OpenSharedMem();
        if (p) { PrintDiagnostics(p); UnmapViewOfFile(p); }
        else { printf("Shared memory not found. Run init first.\n"); }
        return 0;
    }

    // Init mode – inject DLL
    if (mode == Mode::Init) {
        if (FindDLLBase(pid)) {
            printf("DLL already injected.\n");
        } else {
            printf("Injecting DLL: %ws\n", dllPath);
            DWORD base = 0;
            if (!InjectDLL(pid, dllPath)) { printf("Injection failed.\n"); return 1; }
        }
        SharedData* p = OpenSharedMem();
        if (p) { PrintDiagnostics(p); UnmapViewOfFile(p); }
        return 0;
    }

    // All other modes need a kmp path
    if (!kmpPath) { return 1; }

    HWND hwnd = FindLDPlayerHWND(pid);
    if (!hwnd) { printf("LDPlayer window not found.\n"); return 1; }
    printf("LDPlayer PID=%u HWND=0x%p\n", pid, hwnd);

    // Inject DLL if needed
    if (!FindDLLBase(pid)) {
        printf("DLL not injected. Run init first.\n"); return 1;
    }
    printf("DLL already injected.\n");

    // Get full path
    wchar_t fullPath[MAX_PATH];
    GetFullPathNameW(kmpPath, MAX_PATH, fullPath, NULL);
    wchar_t* fname = wcsrchr(fullPath, L'\\');
    if (!fname) fname = fullPath; else fname++;

    DWORD modeFlags = (mode == Mode::Loop) ? 0u : 3u;
    if (!SetTargetKMP(fname, fullPath, modeFlags)) {
        printf("Failed to set target .kmp.\n"); return 1;
    }

    // Set switchArgMode: GuiCycle uses arg=0 (cycle mode), all others use &targetPath
    {
        SharedData* p = OpenSharedMem();
        if (p) { p->switchArgMode = (mode == Mode::GuiCycle) ? 1u : 0u; UnmapViewOfFile(p); }
    }

    printf("Filename: %ws\nModeFlags: 0x%08X\n", fname, modeFlags);
    PrintDiagnostics(OpenSharedMem());

    switch (mode) {
        case Mode::Default:
            return TriggerOnceAndVerify(hwnd, fullPath) ? 0 : 1;
        case Mode::Loop:
            return TriggerUntilRequested(hwnd, fullPath) ? 0 : 1;
        case Mode::Direct: {
            // Diagnostic only: CreateRemoteThread route
            printf("\n--- Direct switch ---\n");
            SharedData* p = OpenSharedMem();
            if (!p) return 1;
            if (p->savedInstance == 0) {
                printf("No saved instance. Press Ctrl+F once first.\n");
                UnmapViewOfFile(p); return 1;
            }
            printf("Instance: 0x%08X\n", p->savedInstance);
            UnmapViewOfFile(p);
            if (CallSwitchKeymapRemote(pid, dllPath)) {
                printf("SwitchKeymap completed.\n");
            } else {
                printf("SwitchKeymap failed.\n");
            }
            return 0;
        }
        case Mode::Gui:
        case Mode::GuiCycle: {
            printf("\n--- GUI-thread %s switch (no Ctrl+F) ---\n",
                mode == Mode::GuiCycle ? "CYCLE" : "PATH");

            // 1. Install WndProc subclass via CreateRemoteThread → PrepareGuiSwitch
            if (!CallExportRemote(pid, dllPath, "PrepareGuiSwitch", "_PrepareGuiSwitch@4")) {
                printf("PrepareGuiSwitch call failed.\n"); return 1;
            }

            SharedData* p = OpenSharedMem();
            if (!p) { printf("No shared mem.\n"); return 1; }
            if (!p->wndprocInstalled) {
                printf("Subclass not installed.\n"); UnmapViewOfFile(p); return 1;
            }

            printf("GUI thread ID: %u\n", p->guiThreadId);
            printf("HWND: 0x%08X\n", p->subclassHwnd);
            printf("savedInstance: 0x%08X\n", p->savedInstance);
            if (!p->savedInstance) {
                printf("\nNo savedInstance (CInputMgr this not captured).\n");
                printf("For this test: run a normal switch first to prime it:\n");
                printf("  keymap_injector.exe \"<walk.kmp>\"\n");
                UnmapViewOfFile(p); return 1;
            }

            HWND targetHwnd = (HWND)(uintptr_t)p->subclassHwnd;
            UINT wmSwitch = p->wmSwitchMsg;
            if (!wmSwitch) {
                wmSwitch = RegisterWindowMessageW(L"LDKeymapSwitch_GuiSwitch");
                printf("(wmSwitchMsg was 0, registered locally: %u)\n", wmSwitch);
            }
            DWORD cfwBefore = p->cfwKmpCount;
            p->switchPending = 1;
            p->switchResult = 0;
            UnmapViewOfFile(p);

            // 2. PostMessage to dispatch SwitchKeymap on the GUI thread
            printf("\nPosting WM_SWITCH (%u) to HWND 0x%p...\n", wmSwitch, targetHwnd);
            BOOL posted = PostMessageW(targetHwnd, wmSwitch, 0, 0);
            printf("PostMessage returned: %d\n", posted);
            if (!posted) {
                printf("PostMessage failed (err %lu). Window may be unresponsive.\n", GetLastError());
            }

            // 3. Poll for result (5s timeout)
            bool done = false;
            for (int i = 0; i < 50; i++) {
                Sleep(100);
                p = OpenSharedMem();
                if (!p) continue;
                if (p->switchResult != 0) {
                    printf("\n======= RESULT =======\n");
                    const char* meanings[] = {"pending", "CFW FIRED - file read happened!",
                                              "called but NO file read", "no savedInstance"};
                    DWORD r = p->switchResult;
                    printf("switchResult: %d (%s)\n", r, r <= 3 ? meanings[r] : "unknown");
                    printf("switchThreadId: %u  (GUI thread: %u)  -> %s\n",
                        p->switchThreadId, p->guiThreadId,
                        p->switchThreadId == p->guiThreadId ? "MATCH" : "MISMATCH");
                    printf("cfwKmpCount: %u -> %u  (delta %+d)\n",
                        p->switchCfwBefore, p->switchCfwAfter,
                        (int)p->switchCfwAfter - (int)p->switchCfwBefore);
                    printf("hookCount:   %u -> %u  (delta %+d)\n",
                        p->switchHookBefore, p->switchHookAfter,
                        (int)p->switchHookAfter - (int)p->switchHookBefore);
                    done = true;
                    UnmapViewOfFile(p);
                    break;
                }
                UnmapViewOfFile(p);
            }
            if (!done) printf("\nTIMEOUT: switchResult still 0 after 5s.\n");

            PrintDiagnostics(OpenSharedMem());
            return done ? 0 : 1;
        }
        default: return 0;
    }
}

// ── Shared Memory ─────────────────────────────
static SharedData* OpenSharedMem() {
    HANDLE hMap = OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, FALSE, SHARED_MEM_NAME);
    if (!hMap) return NULL;
    SharedData* p = (SharedData*)MapViewOfFile(hMap, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, 0);
    CloseHandle(hMap);
    return p;
}

// ── Diagnostics ───────────────────────────────
static void PrintDiagnostics(const SharedData* p) {
    if (!p) return;
    printf("HookStatus: 0x%08X", p->hookStatus);
    if ((p->hookStatus & 0x1F) == 0x1E) printf(" (CALL OK)");
    if (p->hookStatus & 0x40) printf(" (CFW)");
    printf("\n");
    printf("FuncAddress: 0x%08X  DecodedCallTarget: 0x%08X\n", p->funcAddress, p->callTarget);
    printf("HookCount: %u  LastThis: 0x%08X\n", p->hookCount, p->lastThis);
    printf("LastOriginalArg: 0x%08X  LastReplacementArg: 0x%08X  LastHookEsp: 0x%08X\n",
        p->lastOriginalArg, p->lastReplacementArg, p->lastHookEsp);
    printf("CreateFileW .kmp count: %u  redirects: %u\n", p->cfwKmpCount, p->cfwRedirectCount);
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

// ── Process/Window finding ────────────────────
static DWORD FindLDPlayerPID() {
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnap == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32W pe = { sizeof(pe) };
    DWORD pid = 0;
    if (Process32FirstW(hSnap, &pe)) {
        do { if (_wcsicmp(pe.szExeFile, L"dnplayer.exe") == 0) { pid = pe.th32ProcessID; break; }
        } while (Process32NextW(hSnap, &pe));
    }
    CloseHandle(hSnap);
    return pid;
}

static HWND FindLDPlayerHWND(DWORD pid) {
    struct Ctx { DWORD pid; HWND hwnd; } ctx = { pid, NULL };
    EnumWindows([](HWND h, LPARAM lp) -> BOOL {
        auto* c = (Ctx*)lp;
        DWORD p; GetWindowThreadProcessId(h, &p);
        if (p == c->pid && IsWindowVisible(h) && GetWindowTextLengthW(h) > 0) {
            c->hwnd = h; return FALSE;
        }
        return TRUE;
    }, (LPARAM)&ctx);
    return ctx.hwnd;
}

// ── DLL injection ─────────────────────────────
static DWORD FindDLLBase(DWORD pid) {
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
    if (hSnap == INVALID_HANDLE_VALUE) return 0;
    MODULEENTRY32W me = { sizeof(me) };
    DWORD base = 0;
    if (Module32FirstW(hSnap, &me)) {
        do { if (_wcsicmp(me.szModule, L"keymap_hook.dll") == 0) { base = (DWORD)(uintptr_t)me.modBaseAddr; break; }
        } while (Module32NextW(hSnap, &me));
    }
    CloseHandle(hSnap);
    return base;
}

static bool InjectDLL(DWORD pid, const wchar_t* dllPath) {
    HANDLE hProc = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (!hProc) return false;
    size_t len = (wcslen(dllPath) + 1) * sizeof(wchar_t);
    void* remoteMem = VirtualAllocEx(hProc, NULL, len, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remoteMem) { CloseHandle(hProc); return false; }
    WriteProcessMemory(hProc, remoteMem, dllPath, len, NULL);
    HANDLE hThread = CreateRemoteThread(hProc, NULL, 0,
        (LPTHREAD_START_ROUTINE)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "LoadLibraryW"),
        remoteMem, 0, NULL);
    if (!hThread) { VirtualFreeEx(hProc, remoteMem, 0, MEM_RELEASE); CloseHandle(hProc); return false; }
    WaitForSingleObject(hThread, 5000);
    CloseHandle(hThread);
    VirtualFreeEx(hProc, remoteMem, 0, MEM_RELEASE);
    CloseHandle(hProc);
    return true;
}

// ── Target KMP Setup ──────────────────────────
static bool SetTargetKMP(const wchar_t* filename, const wchar_t* fullPath, DWORD modeFlags) {
    SharedData* p = OpenSharedMem();
    if (!p) return false;
    WideCharToMultiByte(CP_ACP, 0, filename, -1, p->targetPath, 1024, NULL, NULL);
    lstrcpynW(p->fullPath, fullPath, 1024);
    p->flags = (p->flags & ~7u) | (modeFlags & 7u);
    p->kmpHistoryCount = 0;
    UnmapViewOfFile(p);
    return true;
}

// ── Trigger Modes ─────────────────────────────
static bool TriggerOnceAndVerify(HWND hwnd, const wchar_t* kmpPath) {
    printf("\n--- Trigger one Ctrl+F (CALL hook + CFW redirect) ---\n");
    SetForegroundWindow(hwnd);
    Sleep(200);
    keybd_event(VK_CONTROL, 0, 0, 0);
    Sleep(50);
    keybd_event('F', 0, 0, 0);
    Sleep(50);
    keybd_event('F', 0, KEYEVENTF_KEYUP, 0);
    keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0);
    Sleep(300);

    SharedData* p = OpenSharedMem();
    if (!p) return false;
    PrintDiagnostics(p);
    bool hookFired = p->hookCount > 0;
    bool kmpRead = p->cfwKmpCount > 0;
    bool redirected = p->cfwRedirectCount > 0;
    bool targetMatched = false;
    if (redirected && p->lastKmpPath[0]) {
        wchar_t target[MAX_PATH];
        GetFullPathNameW(kmpPath, MAX_PATH, target, NULL);
        targetMatched = (_wcsicmp(p->lastKmpPath, target) == 0);
    }
    printf("\n[%c] CALL hook fired      [%c] .kmp read attempted  [%c] CFW redirected       [%c] redirected to target\n",
        hookFired ? 'x' : ' ', kmpRead ? 'x' : ' ', redirected ? 'x' : ' ', targetMatched ? 'x' : ' ');
    if (hookFired && kmpRead && redirected && targetMatched) {
        printf("SUCCESS: target .kmp delivered to setKeyboardConfig.\n");
    } else {
        printf("FAILED: ensure LDPlayer is running a game, then retry.\n");
    }
    UnmapViewOfFile(p);
    return true;
}

static bool TriggerUntilRequested(HWND hwnd, const wchar_t* kmpPath) {
    printf("\n--- Loop mode: holding Ctrl+F. Press Enter to stop. ---\n");
    SetForegroundWindow(hwnd);
    Sleep(200);
    keybd_event(VK_CONTROL, 0, 0, 0);
    keybd_event('F', 0, 0, 0);
    getchar();
    keybd_event('F', 0, KEYEVENTF_KEYUP, 0);
    keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0);
    SharedData* p = OpenSharedMem();
    if (p) { PrintDiagnostics(p); UnmapViewOfFile(p); }
    return true;
}

// ── CreateRemoteThread helper (generic) ─────────────
static bool CallExportRemote(DWORD pid, const wchar_t* dllPath, const char* exportName, const char* decoratedName) {
    DWORD dllBase = FindDLLBase(pid);
    if (!dllBase) return false;

    HMODULE hLocal = LoadLibraryW(dllPath);
    if (!hLocal) return false;

    FARPROC pfn = GetProcAddress(hLocal, exportName);
    if (!pfn && decoratedName) pfn = GetProcAddress(hLocal, decoratedName);
    if (!pfn) { FreeLibrary(hLocal); return false; }

    DWORD rva = (DWORD)((BYTE*)pfn - (BYTE*)hLocal);
    FreeLibrary(hLocal);
    DWORD target = dllBase + rva;

    HANDLE hProc = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (!hProc) return false;

    HANDLE hThread = CreateRemoteThread(hProc, NULL, 0, (LPTHREAD_START_ROUTINE)(uintptr_t)target, NULL, 0, NULL);
    if (!hThread) { CloseHandle(hProc); return false; }

    WaitForSingleObject(hThread, 5000);
    DWORD exitCode = 0;
    GetExitCodeThread(hThread, &exitCode);
    CloseHandle(hThread);
    CloseHandle(hProc);
    return exitCode == 0;
}

// ── CreateRemoteThread helper (legacy) ─────────────────
static bool CallSwitchKeymapRemote(DWORD pid, const wchar_t* dllPath) {
    DWORD dllBase = FindDLLBase(pid);
    if (!dllBase) return false;

    HMODULE hLocal = LoadLibraryW(dllPath);
    if (!hLocal) return false;

    FARPROC pfn = GetProcAddress(hLocal, SWITCH_EXPORT);
    if (!pfn) pfn = GetProcAddress(hLocal, SWITCH_EXPORT_DECORATED);
    if (!pfn) { FreeLibrary(hLocal); return false; }

    DWORD rva = (DWORD)((BYTE*)pfn - (BYTE*)hLocal);
    FreeLibrary(hLocal);
    DWORD target = dllBase + rva;

    HANDLE hProc = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (!hProc) return false;

    HANDLE hThread = CreateRemoteThread(hProc, NULL, 0, (LPTHREAD_START_ROUTINE)(uintptr_t)target, NULL, 0, NULL);
    if (!hThread) { CloseHandle(hProc); return false; }

    WaitForSingleObject(hThread, 5000);
    DWORD exitCode = 0;
    GetExitCodeThread(hThread, &exitCode);
    CloseHandle(hThread);
    CloseHandle(hProc);
    return exitCode == 0;
}
