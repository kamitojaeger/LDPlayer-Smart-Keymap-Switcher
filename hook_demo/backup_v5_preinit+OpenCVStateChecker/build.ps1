# build.ps1 - PowerShell build script for keymap_hook.dll + keymap_injector.exe
# Replaces build.bat for environments where cmd.exe invocation is restricted.
param([string]$Configuration = "Release")

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $here

$vsInstall = "C:\Program Files\Microsoft Visual Studio\18\Community"
$vcTools   = "$vsInstall\VC\Tools\MSVC"
$msvcVer   = (Get-ChildItem $vcTools -Directory | Select-Object -First 1).Name
$vcBase    = "$vcTools\$msvcVer"
$binHost   = "$vcBase\bin\Hostx64\x64"
$binX86    = "$vcBase\bin\Hostx64\x86"

$sdkRoot   = "C:\Program Files (x86)\Windows Kits\10"
$sdkVer    = (Get-ChildItem "$sdkRoot\Include" -Directory | Select-Object -Last 1).Name

Write-Host "=== MSVC $msvcVer / SDK $sdkVer (x86 target) ===" -ForegroundColor Cyan

# Environment: INCLUDE
$env:INCLUDE = "$vcBase\include;" +
               "$sdkRoot\Include\$sdkVer\ucrt;" +
               "$sdkRoot\Include\$sdkVer\um;" +
               "$sdkRoot\Include\$sdkVer\shared;" +
               "$sdkRoot\Include\$sdkVer\winrt;" +
               "$sdkRoot\Include\$sdkVer\cppwinrt"

# Environment: LIB (x86)
$env:LIB = "$vcBase\lib\x86;" +
           "$sdkRoot\Lib\$sdkVer\ucrt\x86;" +
           "$sdkRoot\Lib\$sdkVer\um\x86"

# Environment: PATH (host tools + x86 target tools)
$env:PATH = "$binHost;$binX86;$env:PATH"

Write-Host "=== Assembling hook_stub.asm ===" -ForegroundColor Cyan
& "$binX86\ml.exe" /c /coff hook_stub.asm
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: Assembly failed" -ForegroundColor Red; exit 1 }

Write-Host "=== Compiling keymap_hook.dll (static CRT) ===" -ForegroundColor Cyan
& "$binX86\cl.exe" /LD /O2 /MT keymap_hook.cpp hook_stub.obj /Fekeymap_hook.dll /link /NOLOGO
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: DLL compilation failed" -ForegroundColor Red; exit 1 }

Write-Host "=== Compiling keymap_injector.exe (static CRT + version info) ===" -ForegroundColor Cyan
# Find rc.exe in Windows SDK
$rcExe = "$sdkRoot\bin\$sdkVer\x86\rc.exe"
if (-not (Test-Path $rcExe)) { $rcExe = "$sdkRoot\bin\$sdkVer\x64\rc.exe" }
if (Test-Path $rcExe) {
    & $rcExe /fo version.res version.rc 2>$null
    if (Test-Path version.res) {
        & "$binX86\cl.exe" /O2 /MT keymap_injector.cpp version.res /Fekeymap_injector.exe /link /NOLOGO
    } else {
        & "$binX86\cl.exe" /O2 /MT keymap_injector.cpp /Fekeymap_injector.exe /link /NOLOGO
    }
} else {
    Write-Host "  (rc.exe not found, building without version info)" -ForegroundColor Yellow
    & "$binX86\cl.exe" /O2 /MT keymap_injector.cpp /Fekeymap_injector.exe /link /NOLOGO
}
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: Injector compilation failed" -ForegroundColor Red; exit 1 }

Write-Host "=== Build OK ===" -ForegroundColor Green
Get-ChildItem keymap_hook.dll, keymap_injector.exe | Format-Table Name, Length, LastWriteTime
