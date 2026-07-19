// Keymap Hook v8 - Clean (LDPlayer14 offsets updated 2026-07-15)
#include <windows.h>
#pragma comment(lib, "user32.lib")
#define MEMNAME L"LDKeymapSwitch_Mem"
#define CORE_NAME L"dnplycore.dll"
// Overseas LDPlayer9 offsets
#define OV_HOOK_RVA 0x2019C
#define OV_FUNC_RVA 0x9CA10
#define OV_RTRN_RVA 0x201A1
// Domestic LDPlayer9 offsets
#define DM_HOOK_RVA 0x1FD9C
#define DM_FUNC_RVA 0x9BCC0
#define DM_RTRN_RVA 0x1FDA1
// Overseas LDPlayer14 offsets (updated 2026-07-15 for newer build)
#define V14_HOOK_RVA 0x1DA53
#define V14_FUNC_RVA 0x96130
#define V14_RTRN_RVA 0x1DA58

struct SharedData {
    DWORD  magic;                        // 0x000 (0x4B4D5053)
    char   targetPath[1024];             // 0x004 - filename (ANSI)
    DWORD  flags;                        // 0x404
    WCHAR  fullPath[1024];               // 0x408 - full path
    DWORD  savedInstance;                // 0xC08 - CInputMgr this ptr
    DWORD  funcAddress;                  // 0xC0C - setKeyboardConfig address
    DWORD  hookStatus;                   // 0xC10
    DWORD  hookCount;                    // 0xC14
    DWORD  lastThis;                     // 0xC18
    DWORD  lastOriginalArg;              // 0xC1C
    DWORD  lastReplacementArg;           // 0xC20
    DWORD  lastHookEsp;                  // 0xC24
    DWORD  callTarget;                   // 0xC28
    DWORD  cfwKmpCount;                  // 0xC2C
    DWORD  cfwRedirectCount;             // 0xC30
    WCHAR  lastKmpPath[1024];            // 0xC34
    WCHAR  lastRequestedKmpPath[1024];   // 0x1434
    DWORD  kmpHistoryCount;
    WCHAR  kmpHistory[8][260];
    DWORD  kmpHistoryRedirected[8];
    // ── Plan B: GUI-thread piggyback switch (bypass Ctrl+F) ──
    DWORD  wmSwitchMsg;          // RegisterWindowMessage ID
    DWORD  guiThreadId;          // target window's thread ID
    DWORD  wndprocInstalled;     // 0=no, 1=yes
    DWORD  subclassHwnd;         // subclassed HWND (low 32 bits)
    DWORD  switchPending;        // 0=idle, 1=requested by injector
    DWORD  switchResult;          // 0=pending, 1=CFW fired, 2=called-no-CFW, 3=no-instance
    DWORD  switchThreadId;       // thread that ran SwitchKeymap
    DWORD  switchCfwBefore;      // cfwKmpCount before switch
    DWORD  switchCfwAfter;       // cfwKmpCount after switch
    DWORD  switchHookBefore;    // hookCount before switch
    DWORD  switchHookAfter;      // hookCount after switch
    DWORD  switchArgMode;        // 0=use &targetPath, 1=use 0 (cycle mode)
};

typedef HANDLE(WINAPI *CFW)(LPCWSTR,DWORD,DWORD,LPSECURITY_ATTRIBUTES,DWORD,DWORD,HANDLE);
static WCHAR g_wb[1024]; static SharedData* g_s = NULL; static HANDLE g_m = NULL;
static CFW g_r = NULL; static BYTE g_oc[5]; static BYTE g_oz[5];
static BYTE* g_cfw_addr = NULL;

// ── Plan B: GUI-thread piggyback ──
static WNDPROC g_origWndProc = NULL;
static HWND    g_subclassedHwnd = NULL;
static BOOL    g_inSwitch = FALSE;        // reentrancy guard
static UINT    g_wmSwitch = 0;            // RegisterWindowMessage ID

extern "C" {
    void* g_d = NULL; void* g_f = NULL; void* g_ret = NULL; void HookStub();
    void SwitchKeymap(void);
    void SwitchKeymapCycle(void);
    long g_hcnt = 0;
    void LogFire() { g_hcnt++; }
}

extern "C" __declspec(dllexport) DWORD WINAPI CallSwitchKeymap(LPVOID) {
    SwitchKeymap();
    return 0;
}

// ── Plan B: GUI-thread piggyback ──────────────────────────────
// SwitchWndProc runs on the GUI thread (dispatched by the message pump).
// When it receives WM_SWITCH, it calls SwitchKeymap → setKeyboardConfig
// directly on the GUI thread, bypassing Ctrl+F entirely.
static LRESULT CALLBACK SwitchWndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == g_wmSwitch && g_s && g_s->magic == 0x4B4D5053 && !g_inSwitch) {
        g_inSwitch = TRUE;
        g_s->switchThreadId = GetCurrentThreadId();
        g_s->switchCfwBefore  = g_s->cfwKmpCount;
        g_s->switchHookBefore = g_s->hookCount;
        g_s->switchResult = 0;

        if (!g_s->savedInstance) {
            g_s->switchResult = 3;                     // no CInputMgr captured
        } else {
            // switchArgMode: 0=use &targetPath (load specific), 1=use 0 (cycle to next)
            if (g_s->switchArgMode == 1)
                SwitchKeymapCycle();                    // → setKeyboardConfig(this, 0)
            else
                SwitchKeymap();                        // → setKeyboardConfig(this, path)
            g_s->switchCfwAfter  = g_s->cfwKmpCount;
            g_s->switchHookAfter = g_s->hookCount;
            g_s->switchResult = (g_s->switchCfwAfter > g_s->switchCfwBefore) ? 1 : 2;
        }
        g_s->switchPending = 0;
        g_inSwitch = FALSE;
        return 0;
    }
    return CallWindowProcW(g_origWndProc, hwnd, msg, wp, lp);
}

// EnumWindows callback — finds this process's top-level visible window
static BOOL CALLBACK FindMainWindowProc(HWND h, LPARAM lp) {
    DWORD pid;
    GetWindowThreadProcessId(h, &pid);
    if (pid == GetCurrentProcessId() && IsWindowVisible(h) && GetWindowTextLengthW(h) > 0) {
        *(HWND*)lp = h;
        return FALSE;
    }
    return TRUE;
}

// Export: called via CreateRemoteThread from injector.
// Finds the LDPlayer main window, records its thread ID, and installs
// the SwitchWndProc subclass so PostMessage(WM_SWITCH) dispatches to GUI thread.
extern "C" __declspec(dllexport) DWORD WINAPI PrepareGuiSwitch(LPVOID) {
    if (!g_s || g_s->magic != 0x4B4D5053) return 1;

    if (!g_wmSwitch) {
        g_wmSwitch = RegisterWindowMessageW(L"LDKeymapSwitch_GuiSwitch");
        g_s->wmSwitchMsg = g_wmSwitch;
    }

    HWND hwnd = NULL;
    EnumWindows(FindMainWindowProc, (LPARAM)&hwnd);
    if (!hwnd) { g_s->wndprocInstalled = 0; return 2; }

    g_s->guiThreadId = GetWindowThreadProcessId(hwnd, NULL);

    if (g_subclassedHwnd != hwnd) {
        // Restore previous window if we subclassed a different one
        if (g_origWndProc && g_subclassedHwnd)
            SetWindowLongPtrW(g_subclassedHwnd, GWLP_WNDPROC, (LONG_PTR)g_origWndProc);
        g_origWndProc = (WNDPROC)SetWindowLongPtrW(hwnd, GWLP_WNDPROC, (LONG_PTR)SwitchWndProc);
        if (g_origWndProc) {
            g_subclassedHwnd = hwnd;
            g_s->subclassHwnd = (DWORD)(uintptr_t)hwnd;
            g_s->wndprocInstalled = 1;
        } else {
            g_s->wndprocInstalled = 0;
            return 3;
        }
    } else {
        g_s->wndprocInstalled = 1;  // already subclassed
    }
    return 0;
}

static HANDLE WINAPI HkCW(LPCWSTR n,DWORD a,DWORD s,LPSECURITY_ATTRIBUTES sa,DWORD c,DWORD f,HANDLE t){
    if(g_s&&g_s->magic==0x4B4D5053){
        if(n){
        int L=lstrlenW(n);
        if(L>=4&&n[L-4]==L'.'&&(n[L-3]=='k'||n[L-3]=='K')&&(n[L-2]=='m'||n[L-2]=='M')&&(n[L-1]=='p'||n[L-1]=='P')){
            g_s->cfwKmpCount++;
            lstrcpynW(g_s->lastRequestedKmpPath, n, 1024);
            lstrcpynW(g_s->lastKmpPath, n, 1024);
            DWORD idx = g_s->kmpHistoryCount;
            if(idx < 8){
                lstrcpynW(g_s->kmpHistory[idx], n, 260);
                g_s->kmpHistoryRedirected[idx] = 0;
                g_s->kmpHistoryCount = idx + 1;
            }
            if(idx >= 1 && (g_s->flags&1) && g_s->fullPath[0] &&
               GetFileAttributesW(g_s->fullPath) != INVALID_FILE_ATTRIBUTES){
                g_s->cfwRedirectCount++;
                lstrcpynW(g_s->lastKmpPath, g_s->fullPath, 1024);
                if(idx < 8) g_s->kmpHistoryRedirected[idx] = 1;
                n = g_s->fullPath;
            }
            // Clear CFW redirect flag after the expected 2 redirects
            // of a switch cycle (indices 1 and 2 of kmpHistory).
            // Also catches stale reads (idx >= 3) from previous injector
            // sessions, preventing cross-game .kmp overwrite.
            // This runs inside the DLL CFW hook itself, independent of
            // HookStub timing — works even if post-call .kmp I/O differs
            // between LDPlayer versions.
            if((g_s->flags & 1) && idx >= 2)
                g_s->flags &= ~1u;
        }
        }
    }
    DWORD op;
    VirtualProtect(g_cfw_addr, 5, PAGE_EXECUTE_READWRITE, &op);
    memcpy(g_cfw_addr, g_oc, 5);
    VirtualProtect(g_cfw_addr, 5, op, &op);
    HANDLE result = g_r(n,a,s,sa,c,f,t);
    VirtualProtect(g_cfw_addr, 5, PAGE_EXECUTE_READWRITE, &op);
    g_cfw_addr[0] = 0xE9;
    *(DWORD*)(g_cfw_addr+1) = (DWORD)((BYTE*)HkCW - g_cfw_addr - 5);
    VirtualProtect(g_cfw_addr, 5, op, &op);
    return result;
}

BOOL APIENTRY DllMain(HMODULE h,DWORD r,LPVOID){
    if(r==DLL_PROCESS_ATTACH){
        DisableThreadLibraryCalls(h);
        HANDLE hm=CreateFileMappingW(INVALID_HANDLE_VALUE,NULL,PAGE_READWRITE,0,sizeof(SharedData),MEMNAME);
        if(!hm)hm=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,MEMNAME);
        if(!hm)return TRUE;
        g_s=(SharedData*)MapViewOfFile(hm,FILE_MAP_ALL_ACCESS,0,0,0);
        if(!g_s){CloseHandle(hm);return TRUE;}
        g_m=hm; g_d=g_s;
        if(g_s->magic!=0x4B4D5053){ZeroMemory(g_s,sizeof(SharedData));g_s->magic=0x4B4D5053;}
        // CFW hook — kernelbase.CreateFileW
        HMODULE kb=GetModuleHandleW(L"kernelbase.dll");
        if(kb){
            BYTE* e=(BYTE*)GetProcAddress(kb,"CreateFileW");
            g_r=(CFW)e; g_cfw_addr = e;
            if(e){
                memcpy(g_oc,e,5); DWORD op;
                VirtualProtect(e,5,PAGE_EXECUTE_READWRITE,&op);
                intptr_t o=(intptr_t)HkCW-(intptr_t)(e+5); e[0]=0xE9;memcpy(e+1,&o,4);
                VirtualProtect(e,5,op,&op);
                if(g_s) g_s->hookStatus |= 0x40;
            }
        }
        // CALL hook — auto-detect offsets
        HMODULE c=GetModuleHandleW(CORE_NAME);
        if(c){
            DWORD hookRvas[] = {OV_HOOK_RVA, DM_HOOK_RVA, V14_HOOK_RVA};
            DWORD funcRvas[] = {OV_FUNC_RVA, DM_FUNC_RVA, V14_FUNC_RVA};
            DWORD rtrnRvas[] = {OV_RTRN_RVA, DM_RTRN_RVA, V14_RTRN_RVA};
            int sel = -1;
            for(int i = 0; i < 3; i++) {
                BYTE* s = (BYTE*)c + hookRvas[i];
                if(s[0] == 0xE8) {
                    DWORD target = (DWORD)(uintptr_t)(s + 5 + *(LONG*)(s + 1));
                    if(target == (DWORD)(uintptr_t)((BYTE*)c + funcRvas[i])) {
                        sel = i; break;
                    }
                }
            }
            if(sel >= 0) {
                BYTE* s=(BYTE*)c+hookRvas[sel];
                g_f=(BYTE*)c+funcRvas[sel];
                g_ret=(BYTE*)c+rtrnRvas[sel];
                if(g_s) { g_s->funcAddress = (DWORD)(uintptr_t)g_f; g_s->hookStatus |= 2; }
                DWORD decodedTarget = 0;
                if(s[0] == 0xE8) {
                    decodedTarget = (DWORD)(uintptr_t)(s + 5 + *(LONG*)(s + 1));
                    if(g_s) { g_s->hookStatus |= 4; g_s->callTarget = decodedTarget; }
                }
                if(decodedTarget == (DWORD)(uintptr_t)g_f) {
                    if(g_s) g_s->hookStatus |= 8;
                    memcpy(g_oz,s,5); DWORD op;
                    VirtualProtect(s,5,PAGE_EXECUTE_READWRITE,&op);
                    intptr_t o=(intptr_t)HookStub-(intptr_t)(s+5);
                    s[0]=0xE9;memcpy(s+1,&o,4);
                    VirtualProtect(s,5,op,&op);
                    if(g_s) g_s->hookStatus |= 0x10;
                }
            }
        }
    }
    else if(r==DLL_PROCESS_DETACH){
        // Restore original WndProc if we subclassed a window
        if(g_origWndProc && g_subclassedHwnd)
            SetWindowLongPtrW(g_subclassedHwnd, GWLP_WNDPROC, (LONG_PTR)g_origWndProc);
    }
    return TRUE;
}
