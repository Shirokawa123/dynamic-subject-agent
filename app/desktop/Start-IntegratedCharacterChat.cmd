@echo off
pushd "%~dp0\..\.." || exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\start_integrated_character_chat.ps1" -TechnicalVariant change-evidence
if errorlevel 1 pause
popd
