.model flat, C
.code

EXTERN g_d:DWORD
EXTERN g_f:DWORD
EXTERN g_ret:DWORD
EXTERN g_hcnt:DWORD
EXTERN LogFire:PROC

PUBLIC HookStub

; ────────────────────────────────────────────────────────────
; HookStub - replaces the CALL setKeyboardConfig instruction.
; The original CALL pushes a return address; since we replaced
; it with JMP, we must push the return address before jumping
; to g_f so that setKeyboardConfig sees proper stack layout:
;   [ESP+0] = return address
;   [ESP+4] = arg
; ────────────────────────────────────────────────────────────
HookStub PROC
    pushad
    call    LogFire
    popad

    push    eax
    push    edx

    mov     eax, [g_d]
    test    eax, eax
    jz      RESTORE

    cmp     dword ptr [eax], 4B4D5053h
    jne     RESTORE

    inc     dword ptr [eax+0C14h]       ; hookCount++

    mov     [eax+0C08h], ecx            ; savedInstance = this
    mov     [eax+0C18h], ecx            ; lastThis
    mov     [eax+0C24h], esp            ; lastHookEsp
    mov     edx, [esp+8]
    mov     [eax+0C1Ch], edx            ; lastOriginalArg

    test    dword ptr [eax+404h], 2
    jz      SKIP_REPLACE

    lea     edx, [eax+4]                ; &targetPath
    mov     [eax+0C20h], edx            ; lastReplacementArg
    mov     [esp+8], edx                ; replace arg in place
    jmp     RESTORE

SKIP_REPLACE:
    mov     [eax+0C20h], edx            ; record original as replacement

RESTORE:
    pop     edx
    pop     eax

    push    [g_ret]
    jmp     [g_f]

HookStub ENDP

; ────────────────────────────────────────────────────────────
; Export: SwitchKeymap
; Called via CreateRemoteThread from injector.
; Calls setKeyboardConfig(instance, filename).
; ────────────────────────────────────────────────────────────
PUBLIC SwitchKeymap
SwitchKeymap PROC
    pushad

    mov     eax, [g_d]
    test    eax, eax
    jz      SKIP_SW

    cmp     dword ptr [eax], 4B4D5053h
    jne     SKIP_SW

    mov     ecx, [eax+0C08h]       ; savedInstance
    test    ecx, ecx
    jz      SKIP_SW

    lea     edx, [eax+4]            ; targetPath
    push    edx                     ; arg = filename
    call    dword ptr [eax+0C0Ch]   ; call setKeyboardConfig

SKIP_SW:
    popad
    ret

SwitchKeymap ENDP

; ────────────────────────────────────────────────────────────
; Export: SwitchKeymapCycle
; Calls setKeyboardConfig(instance, 0) — cycle mode (same as Ctrl+F arg)
; ────────────────────────────────────────────────────────────
PUBLIC SwitchKeymapCycle
SwitchKeymapCycle PROC
    pushad

    mov     eax, [g_d]
    test    eax, eax
    jz      SKIP_SWC

    cmp     dword ptr [eax], 4B4D5053h
    jne     SKIP_SWC

    mov     ecx, [eax+0C08h]       ; savedInstance
    test    ecx, ecx
    jz      SKIP_SWC

    push    0                       ; arg = 0 (cycle to next)
    call    dword ptr [eax+0C0Ch]   ; call setKeyboardConfig

SKIP_SWC:
    popad
    ret

SwitchKeymapCycle ENDP
END
