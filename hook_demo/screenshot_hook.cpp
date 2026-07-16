// Screenshot Hook DLL v2 - IAT hook approach (no inline asm needed)
// Hooks SDL_UpdateTexture in dnplayer.exe via IAT patching to capture
// the Android framebuffer at native resolution without triggering
// Android screenshot flash/notification.

#include <windows.h>

#define FB_MEM_NAME L"LDKeymapSwitch_FB"
#define MAX_FB_SIZE (1920 * 1080 * 4)

// SDL types
typedef unsigned int Uint32;
struct SDL_Texture;
struct Rect { int x, y, w, h; };

typedef int (__cdecl *PFN_SDL_UpdateTexture)(SDL_Texture*, const Rect*, const void*, int);
typedef int (__cdecl *PFN_SDL_QueryTexture)(SDL_Texture*, Uint32*, int*, int*, int*);

#pragma pack(push, 1)
struct FBData {
    DWORD magic;      // 0x46425200
    DWORD width;
    DWORD height;
    DWORD format;
    DWORD pitch;
    DWORD frameSeq;
    DWORD ready;      // 1=new frame
    BYTE  pixels[MAX_FB_SIZE];
};
#pragma pack(pop)

static PFN_SDL_UpdateTexture g_RealUpdate = NULL;
static PFN_SDL_QueryTexture  g_Query = NULL;
static HANDLE                g_fbMap = NULL;
static FBData*               g_fb = NULL;
static HMODULE               g_hSdl2 = NULL;

// ============================================================
// Our hooked SDL_UpdateTexture
// ============================================================
static int __cdecl Hook_UpdateTexture(SDL_Texture* tex, const Rect* r, const void* px, int pitch)
{
    // Capture framebuffer BEFORE calling original
    if (g_fb && g_Query && px && pitch > 0) {
        Uint32 fmt = 0;
        int acc = 0, w = 0, h = 0;
        g_Query(tex, &fmt, &acc, &w, &h);

        if (w == 1920 && h == 1080) {
            int sz = h * pitch;
            if (sz > MAX_FB_SIZE) sz = MAX_FB_SIZE;
            g_fb->width  = w;
            g_fb->height = h;
            g_fb->format = fmt;
            g_fb->pitch  = pitch;
            g_fb->frameSeq++;
            memcpy(g_fb->pixels, px, sz);
            g_fb->ready = 1;
        }
    }

    // Call original
    return g_RealUpdate(tex, r, px, pitch);
}

// ============================================================
// Patch IAT entry for SDL_UpdateTexture in the calling module
// ============================================================
static BOOL PatchIAT(HMODULE hCaller)
{
    if (!hCaller || !g_RealUpdate) return FALSE;

    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)hCaller;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE*)hCaller + dos->e_lfanew);

    IMAGE_DATA_DIRECTORY& impDir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!impDir.VirtualAddress) return FALSE;

    PIMAGE_IMPORT_DESCRIPTOR imp = (PIMAGE_IMPORT_DESCRIPTOR)((BYTE*)hCaller + impDir.VirtualAddress);

    for (; imp->Name; imp++) {
        const char* dllName = (const char*)((BYTE*)hCaller + imp->Name);
        if (_stricmp(dllName, "SDL2.dll") != 0) continue;

        PIMAGE_THUNK_DATA thunk = (PIMAGE_THUNK_DATA)((BYTE*)hCaller + imp->FirstThunk);
        PIMAGE_THUNK_DATA orig  = (PIMAGE_THUNK_DATA)((BYTE*)hCaller + imp->OriginalFirstThunk);

        for (int i = 0; thunk[i].u1.Function; i++) {
            if (!orig || !orig[i].u1.AddressOfData) continue;
            PIMAGE_IMPORT_BY_NAME name = (PIMAGE_IMPORT_BY_NAME)((BYTE*)hCaller + orig[i].u1.AddressOfData);
            if (strcmp((const char*)name->Name, "SDL_UpdateTexture") != 0) continue;

            // Found the IAT entry — patch it
            DWORD oldProt;
            VirtualProtect(&thunk[i].u1.Function, sizeof(void*), PAGE_READWRITE, &oldProt);
            thunk[i].u1.Function = (DWORD_PTR)Hook_UpdateTexture;
            VirtualProtect(&thunk[i].u1.Function, sizeof(void*), oldProt, &oldProt);
            return TRUE;
        }
    }
    return FALSE;
}

// ============================================================
// Init
// ============================================================
static void Init()
{
    g_hSdl2 = LoadLibraryA("SDL2.dll");
    if (!g_hSdl2) return;

    g_RealUpdate = (PFN_SDL_UpdateTexture)GetProcAddress(g_hSdl2, "SDL_UpdateTexture");
    g_Query      = (PFN_SDL_QueryTexture)GetProcAddress(g_hSdl2, "SDL_QueryTexture");
    if (!g_RealUpdate || !g_Query) return;

    // Create shared memory
    g_fbMap = CreateFileMappingW(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE,
                                  0, sizeof(FBData), FB_MEM_NAME);
    if (!g_fbMap) return;
    g_fb = (FBData*)MapViewOfFile(g_fbMap, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(FBData));
    if (!g_fb) return;
    memset(g_fb, 0, sizeof(FBData));
    g_fb->magic = 0x46425200;

    // Patch IAT in the main executable (dnplayer.exe)
    HMODULE hExe = GetModuleHandleA(NULL);
    PatchIAT(hExe);
}

// ============================================================
// DLL Entry
// ============================================================
BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        Init();
    }
    return TRUE;
}
