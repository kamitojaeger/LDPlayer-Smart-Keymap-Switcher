// Keymap Hook v9 - Dual field SharedData + SDL framebuffer capture
#include <windows.h>
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
// Overseas LDPlayer14 offsets
#define V14_HOOK_RVA 0x1DD33
#define V14_FUNC_RVA 0x959F0
#define V14_RTRN_RVA 0x1DD38

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
    // ── Framebuffer capture (v9) ──
    DWORD  fbMagic;        // 0x46425200 = 'FB\0\0'
    DWORD  fbWidth;
    DWORD  fbHeight;
    DWORD  fbFormat;       // SDL pixel format
    DWORD  fbPitch;        // row pitch in bytes
    DWORD  fbFrameSeq;     // incremental frame counter
    DWORD  fbReady;        // 1 = new frame available
    BYTE   fbPixels[1920*1080*4];  // RGBA buffer
};

typedef HANDLE(WINAPI *CFW)(LPCWSTR,DWORD,DWORD,LPSECURITY_ATTRIBUTES,DWORD,DWORD,HANDLE);
static WCHAR g_wb[1024]; static SharedData* g_s = NULL; static HANDLE g_m = NULL;
static CFW g_r = NULL; static BYTE g_oc[5]; static BYTE g_oz[5];
static BYTE* g_cfw_addr = NULL;  // address of hooked CreateFileW (kernelbase)

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

// ── SDL framebuffer capture (v9) ──
typedef unsigned int Uint32;
struct SDL_Tex;
struct SDL_Rct { int x, y, w, h; };
typedef int (__cdecl *PFN_SDL_UpdateTex)(SDL_Tex*, const SDL_Rct*, const void*, int);
typedef int (__cdecl *PFN_SDL_QueryTex)(SDL_Tex*, Uint32*, int*, int*, int*);
static PFN_SDL_UpdateTex g_pRealUpdateTex = NULL;
static PFN_SDL_QueryTex  g_pQueryTex = NULL;

static int __cdecl HOOK_SDL_UpdateTexture(SDL_Tex* tex, const SDL_Rct* r, const void* px, int pitch) {
    if (g_s && g_pQueryTex && px && pitch > 0 && g_s->fbMagic == 0x46425200) {
        Uint32 fmt = 0; int acc = 0, w = 0, h = 0;
        g_pQueryTex(tex, &fmt, &acc, &w, &h);
        if (w == 1920 && h == 1080) {
            int sz = h * pitch;
            if (sz > (int)sizeof(g_s->fbPixels)) sz = sizeof(g_s->fbPixels);
            g_s->fbWidth = w; g_s->fbHeight = h;
            g_s->fbFormat = fmt; g_s->fbPitch = pitch;
            g_s->fbFrameSeq++;
            memcpy(g_s->fbPixels, px, sz);
            g_s->fbReady = 1;
        }
    }
    return g_pRealUpdateTex(tex, r, px, pitch);
}

static void InitSdlHook() {
    HMODULE hSdl2 = LoadLibraryA("SDL2.dll");
    if (!hSdl2) return;
    g_pRealUpdateTex = (PFN_SDL_UpdateTex)GetProcAddress(hSdl2, "SDL_UpdateTexture");
    g_pQueryTex = (PFN_SDL_QueryTex)GetProcAddress(hSdl2, "SDL_QueryTexture");
    if (!g_pRealUpdateTex || !g_pQueryTex) return;

    // Patch IAT of dnplayer.exe
    HMODULE hExe = GetModuleHandleA(NULL);
    if (!hExe) return;
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)hExe;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE*)hExe + dos->e_lfanew);
    IMAGE_DATA_DIRECTORY& dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir.VirtualAddress) return;
    PIMAGE_IMPORT_DESCRIPTOR imp = (PIMAGE_IMPORT_DESCRIPTOR)((BYTE*)hExe + dir.VirtualAddress);
    for (; imp->Name; imp++) {
        const char* dllName = (const char*)((BYTE*)hExe + imp->Name);
        if (dllName[0] != 'S' || dllName[1] != 'D' || dllName[2] != 'L') continue;
        PIMAGE_THUNK_DATA thunk = (PIMAGE_THUNK_DATA)((BYTE*)hExe + imp->FirstThunk);
        DWORD ort = imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk;
        PIMAGE_THUNK_DATA orig = (PIMAGE_THUNK_DATA)((BYTE*)hExe + ort);
        for (int i = 0; thunk[i].u1.Function; i++) {
            if (!orig[i].u1.AddressOfData) continue;
            PIMAGE_IMPORT_BY_NAME name = (PIMAGE_IMPORT_BY_NAME)((BYTE*)hExe + orig[i].u1.AddressOfData);
            const char* fn = (const char*)name->Name;
            if (fn[0] != 'S' || fn[1] != 'D') continue;
            if (lstrcmpA(fn, "SDL_UpdateTexture") != 0) continue;
            DWORD op;
            VirtualProtect(&thunk[i].u1.Function, sizeof(void*), PAGE_READWRITE, &op);
            thunk[i].u1.Function = (DWORD_PTR)HOOK_SDL_UpdateTexture;
            VirtualProtect(&thunk[i].u1.Function, sizeof(void*), op, &op);
            if (g_s) { g_s->fbMagic = 0x46425200; g_s->hookStatus |= 0x80; }
            return;
        }
    }
}

static HANDLE WINAPI HkCW(LPCWSTR n,DWORD a,DWORD s,LPSECURITY_ATTRIBUTES sa,DWORD c,DWORD f,HANDLE t){
    if(g_s&&g_s->magic==0x4B4D5053){
        g_s->hookStatus |= 0x20; // CFW hook is being called (debug flag)
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
    }
    // Restore-call-reinstall to avoid recursion (hook is on kernelbase.CreateFileW)
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
        // CFW hook — hook kernelbase.CreateFileW (actual implementation)
        // kernel32.CreateFileW may be a thin thunk; hooking kernelbase is more reliable
        HMODULE kb=GetModuleHandleW(L"kernelbase.dll");
        if(kb){
            BYTE* e=(BYTE*)GetProcAddress(kb,"CreateFileW");
            g_r=(CFW)e;  // save original for restore-call-reinstall pattern
            g_cfw_addr = e;
            if(e){
                memcpy(g_oc,e,5); DWORD op;
                VirtualProtect(e,5,PAGE_EXECUTE_READWRITE,&op);
                intptr_t o=(intptr_t)HkCW-(intptr_t)(e+5); e[0]=0xE9;memcpy(e+1,&o,4);
                VirtualProtect(e,5,op,&op);
                if(g_s) g_s->hookStatus |= 0x40; // CFW hook installed on kernelbase
            }
        }
        // CALL hook — auto-detect overseas vs domestic offsets
        HMODULE c=GetModuleHandleW(CORE_NAME);
        if(c){
            // Try all known version offsets: LDPlayer9 overseas, LDPlayer9 domestic, LDPlayer14
            DWORD hookRvas[] = {OV_HOOK_RVA, DM_HOOK_RVA, V14_HOOK_RVA};
            DWORD funcRvas[] = {OV_FUNC_RVA, DM_FUNC_RVA, V14_FUNC_RVA};
            DWORD rtrnRvas[] = {OV_RTRN_RVA, DM_RTRN_RVA, V14_RTRN_RVA};
            int sel = -1;
            for(int i = 0; i < 3; i++) {
                BYTE* s = (BYTE*)c + hookRvas[i];
                if(s[0] == 0xE8) {
                    DWORD target = (DWORD)(uintptr_t)(s + 5 + *(LONG*)(s + 1));
                    if(target == (DWORD)(uintptr_t)((BYTE*)c + funcRvas[i])) {
                        sel = i;
                        break;
                    }
                }
            }
            if(sel >= 0) {
                BYTE* s=(BYTE*)c+hookRvas[sel];
                g_f=(BYTE*)c+funcRvas[sel];
                g_ret=(BYTE*)c+rtrnRvas[sel];
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
            } // end if(sel >= 0)
        }
        // ── Init SDL framebuffer capture hook (v9) ──
        InitSdlHook();
    }
    return TRUE;
}
