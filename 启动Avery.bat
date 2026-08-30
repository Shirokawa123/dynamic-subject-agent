@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if exist ".venv\bin\python.exe" set "PYTHON_EXE=.venv\bin\python.exe"
"%PYTHON_EXE%" app\desktop\shell.py
pause
