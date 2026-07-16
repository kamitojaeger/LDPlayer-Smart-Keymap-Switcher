// Keymap Hook v7 - Dual field SharedData
#include <windows.h>
#define MEMNAME L"LDKeymapSwitch_Mem"
#define CORE_NAME L"dnplycore.dll"
#define HOOK_RVA 0x2019C
#define FUNC_RVA 0x9CA10
#define RTRN_RVA 0x201A1

struct SharedData {
    DWORD  magic;                        // 0x000 (0x4B4D5053)
    char   targetPath[1024];             // 0x004 - filename (ANSI)
    DWORD  flags;                        // 0x404
    WCHAR  fullPath[1024];               // 0x408 - full path
    DWORD  savedInstance;                // 0xC08 - CInputMgr this ptr (captured by hook)
    DWORD  funcAddress;                  // 0xC0C - setKeyboardConfig address
    DWORD  hookStatus;                   // 0xC10 - diagnostic bitfield
    DWORD  hookCount;                    // 0xC14 - CALL hook hit count
    DWORD  lastThis;                     // 0xC18 - ECX seen by CALL hook
    DWORD  lastOriginalArg;              // 0xC1C - stack arg before replacement
    DWORD  lastReplacementArg;           // 0xC20 - stack arg after replacement
    DWORD  lastHookEsp;                  // 0xC24 - ESP after stub scratch pushes
    DWORD  callTarget;                   // 0xC28 - decoded CALL target at HOOK_RVA
    DWORD  cfwKmpCount;                  // 0xC2C - .kmp CreateFileW attempts
    DWORD  cfwRedirectCount;             // 0xC30 - redirected .kmp opens
    WCHAR  lastKmpPath[1024];            // 0xC34 - last redirected .kmp path
    WCHAR  lastRequestedKmpPath[1024];   // 0x1434 - original .kmp path requested by LDPlayer
    // ── path history (appended, does not shift existing offsets) ──
    DWORD  kmpHistoryCount;              // number of recorded .kmp reads (max 8)
    WCHAR  kmpHistory[8][260];           // first 8 .kmp read paths (requested, original)
    DWORD  kmpHistoryRedirected[8];      // 1 if that read was redirected
};

typedef HANDLE(WINAPI *CFW)(LPCWSTR,DWORD,DWORD,LPSECURITY_ATTRIBUTES,DWORD,DWORD,HANDLE);
static WCHAR g_wb[1024]; static SharedData* g_s = NULL; static HANDLE g_m = NULL;
static CFW g_r = NULL; static BYTE g_oc[5]; static BYTE g_oz[5];

extern "C" {
    void* g_d = NULL; void* g_f = NULL; void* g_ret = NULL; void HookStub();
    void SwitchKeymap(void);
    long g_hcnt = 0;
    void LogFire() { g_hcnt++; }
}

// ── Export: called via CreateRemoteThread ──
// Must match LPTHREAD_START_ROUTINE signature for correct stack cleanup.
extern "C" __declspec(dllexport) DWORD WINAPI CallSwitchKeymap(LPVOID) {
    SwitchKeymap();
    return 0;
}

static HANDLE WINAPI HkCW(LPCWSTR n,DWORD a,DWORD s,LPSECURITY_ATTRIBUTES sa,DWORD c,DWORD f,HANDLE t){
    // Always observe .kmp reads regardless of redirect flag.
    // Redirect strategy (v2): the first .kmp read is the CURRENT scheme
    // (used by LDPlayer to identify the current index) — skip it so LDPlayer
    // correctly identifies the current position. Redirect SUBSEQUENT reads
    // (the "next" scheme content) to fullPath, so the applied keymap content
    // is our target even though the internal index advances to the next slot.
    if(g_s&&g_s->magic==0x4B4D5053&&n){
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
            // idx==0: first read = current scheme, do NOT redirect.
            // idx>=1: subsequent reads = next scheme content, redirect to target.
            if(idx >= 1 && (g_s->flags&1) && g_s->fullPath[0] &&
               GetFileAttributesW(g_s->fullPath) != INVALID_FILE_ATTRIBUTES){
                n = g_s->fullPath;
                g_s->cfwRedirectCount++;
                lstrcpynW(g_s->lastKmpPath, n, 1024);
                if(idx < 8) g_s->kmpHistoryRedirected[idx] = 1;
                // Do NOT clear bit0 — keep redirecting all subsequent reads.
            }
        }
    }
    return g_r(n,a,s,sa,c,f,t);
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
        // CFW hook
        HMODULE k=GetModuleHandleW(L"kernel32.dll"),kb=GetModuleHandleW(L"kernelbase.dll");
        if(k&&kb){
            BYTE* e=(BYTE*)GetProcAddress(k,"CreateFileW");
            g_r=(CFW)GetProcAddress(kb,"CreateFileW");
            if(e&&g_r){
                memcpy(g_oc,e,5); DWORD op;
                VirtualProtect(e,5,PAGE_EXECUTE_READWRITE,&op);
                intptr_t o=(intptr_t)HkCW-(intptr_t)(e+5); e[0]=0xE9;memcpy(e+1,&o,4);
                VirtualProtect(e,5,op,&op);
            }
        }
        // CALL hook
        HMODULE c=GetModuleHandleW(CORE_NAME);
        if(c){
            BYTE* s=(BYTE*)c+HOOK_RVA; g_f=(BYTE*)c+FUNC_RVA; g_ret=(BYTE*)c+RTRN_RVA;
            // Store funcAddress in shared memory so SwitchKeymap can use it
            if(g_s) {
                g_s->funcAddress = (DWORD)(uintptr_t)g_f;
                g_s->hookStatus |= 2; // dnplycore loaded
            }

            DWORD decodedTarget = 0;
            if(s[0] == 0xE8) {
                decodedTarget = (DWORD)(uintptr_t)(s + 5 + *(LONG*)(s + 1));
                if(g_s) {
                    g_s->hookStatus |= 4; // hook site is CALL rel32
                    g_s->callTarget = decodedTarget;
                }
            }

            if(decodedTarget == (DWORD)(uintptr_t)g_f) {
                if(g_s) g_s->hookStatus |= 8; // CALL target matches FUNC_RVA
                memcpy(g_oz,s,5); DWORD op;
                VirtualProtect(s,5,PAGE_EXECUTE_READWRITE,&op);
                intptr_t o=(intptr_t)HookStub-(intptr_t)(s+5);
                s[0]=0xE9;memcpy(s+1,&o,4);
                VirtualProtect(s,5,op,&op);
                if(g_s) g_s->hookStatus |= 0x10; // CALL hook installed
            }
        }
    }
    return TRUE;
}
