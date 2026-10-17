@echo off
rem Windows 图形界面（不打包、不需要 WSL）：randomize_gui.bat [regulation.bin]
rem 需要 uv（https://github.com/astral-sh/uv）；虚拟环境建在 %USERPROFILE%\.venvs\er_mod。
setlocal
cd /d "%~dp0"
set "VENV=%USERPROFILE%\.venvs\er_mod"
if not exist "%VENV%\Scripts\python.exe" (
  uv venv "%VENV%" || exit /b 1
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || exit /b 1
)
set PYTHONDONTWRITEBYTECODE=1
start "" "%VENV%\Scripts\pythonw.exe" -I tools\gui.py %*
