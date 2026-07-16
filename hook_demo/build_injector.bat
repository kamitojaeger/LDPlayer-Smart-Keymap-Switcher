@echo off
cd /d %~dp0

call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"
cl /O2 /MT keymap_injector.cpp /Fekeymap_injector.exe /link /NOLOGO
