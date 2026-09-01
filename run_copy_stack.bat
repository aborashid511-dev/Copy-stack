@echo off
REM تشغيل Copy Stack على ويندوز بنقرة واحدة
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python غير مثبت. حمّله من https://www.python.org/downloads/
    pause
    exit /b 1
)
python -m pip install --quiet pyperclip
start "" pythonw copy_stack.py
