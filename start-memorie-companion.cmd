@echo off
powershell.exe -NoLogo -NoProfile -File "%~dp0scripts\start_memorie_companion.ps1" -OpenGame
if errorlevel 1 pause
