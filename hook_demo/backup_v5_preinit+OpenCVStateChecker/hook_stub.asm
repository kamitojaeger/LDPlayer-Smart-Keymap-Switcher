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
;
; Critical: the original CALL pushes a return address onto the
; stack, but we replaced it with JMP (which pushes nothing).
; setKeyboardConfig uses __thiscall with one stack argument:
;   push arg            ; by caller before CALL
;   call setKeyboardConfig  ; pushes return addr, then enters fn
;   fn prologue: push ebp; mov ebp, esp
;   fn reads arg from [ebp+8]   ; = [ESP+4] at entry
;   fn returns with ret 4       ; pops ret addr, cleans arg
;
; So at fn entry the stack MUST look like:
;   [ESP+0] = return address
;   [ESP+4] = arg
;
; Since we entered via JMP, [ESP+0] is currently the arg (no
; return address). We must push the return address before
; jumping to g_f, otherwise [ebp+8] reads garbage and the
; argument replacement has no effect.
;
; Stack layout during stub execution:
;   entry:          [ESP+0] = arg
;   after pushad:   [ESP+32] = arg
;   after push eax, edx: [ESP+40] = arg
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

    ; Save CALL context for diagnostics and later direct calls.
    mov     [eax+0C08h], ecx            ; savedInstance = this
    mov     [eax+0C18h], ecx            ; lastThis
    mov     [eax+0C24h], esp            ; lastHookEsp
    ; arg lives at [esp+8] now (above saved eax and edx)
    mov     edx, [esp+8]
    mov     [eax+0C1Ch], edx            ; lastOriginalArg

    ; flags bit1 enables CALL argument replacement.
    test    dword ptr [eax+404h], 2
    jz      SKIP_REPLACE

    lea     edx, [eax+4]                ; &targetPath (ANSI filename)
    mov     [eax+0C20h], edx            ; lastReplacementArg
    mov     [esp+8], edx                ; replace arg in place
    jmp     RESTORE

SKIP_REPLACE:
    mov     [eax+0C20h], edx            ; record original as replacement

RESTORE:
    pop     edx
    pop     eax

    ; Re-establish proper CALL semantics: push return address
    ; so setKeyboardConfig sees [ESP]=ret, [ESP+4]=arg, and its
    ; `ret 4` returns to g_ret (the instruction after the CALL).
    push    [g_ret]
    jmp     [g_f]

HookStub ENDP

; ────────────────────────────────────────────────────────────
; Export: SwitchKeymap
; Called via CreateRemoteThread from injector.
; Calls   setKeyboardConfig(instance, filename)
; using savedInstance + targetPath from shared memory.
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
    ; ret 4 cleans the stack

SKIP_SW:
    popad
    ret

SwitchKeymap ENDP
END
