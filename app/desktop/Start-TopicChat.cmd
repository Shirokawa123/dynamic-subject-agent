@echo off
pushd "%~dp0\..\.." || exit /b 1
set "PYTHONPATH=src"
".venv\bin\python.exe" -X utf8 "scripts\serve_s120_topic_chat.py" --open-browser
if errorlevel 1 pause
popd
