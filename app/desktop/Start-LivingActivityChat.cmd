@echo off
pushd "%~dp0\..\.." || exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\start_living_activity_chat.ps1"
if errorlevel 1 pause
popd
