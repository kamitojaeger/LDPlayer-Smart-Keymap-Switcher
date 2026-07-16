@echo off
cd /d %~dp0

echo === Setting up VS 2022 32-bit environment ===
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"

echo === Assembling hook_stub.asm ===
ml /c /coff hook_stub.asm
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Assembly failed!
    exit /b 1
)

echo === Compiling keymap_hook.dll (static CRT) ===
cl /LD /O2 /MT keymap_hook.cpp hook_stub.obj /Fekeymap_hook.dll /link /NOLOGO
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: DLL compilation failed!
    exit /b 1
)

echo === Compiling keymap_injector.exe (static CRT) ===
cl /O2 /MT keymap_injector.cpp /Fekeymap_injector.exe /link /NOLOGO
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Injector compilation failed!
    exit /b 1
)

echo === Done ===
echo.
echo Usage:
echo   1. Start LDPlayer and open a game
echo   2. keymap_injector.exe "path\to\target.kmp"
echo      (default: CALL hook replaces arg + CFW redirect, one Ctrl+F)
echo   3. keymap_injector.exe --loop "path\to\target.kmp"
echo      (fallback: cycle Ctrl+F relying on native next-keymap rotation)
echo   4. keymap_injector.exe --direct "path\to\target.kmp"
echo      (diagnostic: CreateRemoteThread direct call, no Ctrl+F)
echo   5. keymap_injector.exe --status
echo      (print hook diagnostics only)
echo.
