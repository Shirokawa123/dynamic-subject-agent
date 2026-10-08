@echo off
pushd "%~dp0\..\.." || exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\start_living_final_text_chat.ps1"
if errorlevel 1 pause
popd
