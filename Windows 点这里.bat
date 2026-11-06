@echo off
rem Windows: open Coda. This file stays ASCII because cmd.exe often garbles Chinese.
cd /d "%~dp0"
set "PY="
where py >nul 2>&1 && py -3 -c "" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "" >nul 2>&1 && set "PY=python"
if not defined PY goto nopython
%PY% -X utf8 -B -c "import glob,runpy,sys;p=glob.glob('mac/*/coda_start.py')[0];sys.argv=[p];runpy.run_path(p,run_name='__main__')"
if errorlevel 1 pause
exit /b 0
:nopython
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms;[void][System.Windows.Forms.MessageBox]::Show([regex]::Unescape('\u8fd9\u53f0\u7535\u8111\u8fd8\u6ca1\u6709 Python\u3002\u70b9\u786e\u5b9a\u540e\u4f1a\u6253\u5f00\u4e0b\u8f7d\u9875\uff0c\u5b89\u88c5\u65f6\u8bf7\u52fe\u9009 Add python.exe to PATH\uff0c\u88c5\u597d\u540e\u518d\u53cc\u51fb\u4e00\u6b21\u3002'),'Coda')"
start "" https://www.python.org/downloads/windows/
exit /b 1
