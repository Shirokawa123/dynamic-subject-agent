@echo off
pushd "%~dp0\..\.." || exit /b 1
".venv\bin\python.exe" -X utf8 "app\desktop\character_dialogue_lab.py" --grounded-chat
popd
