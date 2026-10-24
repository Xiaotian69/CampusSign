@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "CxSign" ".venv\Scripts\pythonw.exe" "desktop_ui.py"
) else (
    python "desktop_ui.py"
)
