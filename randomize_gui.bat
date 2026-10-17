@echo off
rem Windows 图形界面（不打包、不需要 WSL）：randomize_gui.bat [regulation.bin]
rem 需要 uv（https://github.com/astral-sh/uv）；虚拟环境建在 %USERPROFILE%\.venvs\er_mod。
rem 这个黑色窗口会一直开着，用来显示错误信息；关掉它图形界面也会关掉。不想要黑窗就用 build_exe.bat 打包出的 exe。
setlocal
cd /d "%~dp0"
set "VENV=%USERPROFILE%\.venvs\er_mod"
if not exist "%VENV%\Scripts\python.exe" (
  uv venv "%VENV%" || exit /b 1
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || exit /b 1
)
rem 旧的虚拟环境可能还没有 Pillow（背景图需要它）
"%VENV%\Scripts\python.exe" -I -c "import PIL" >nul 2>&1 || uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || exit /b 1
set PYTHONDONTWRITEBYTECODE=1
"%VENV%\Scripts\python.exe" -I tools\gui.py %*
if errorlevel 1 (
  echo.
  echo 图形界面没有正常结束，错误信息见上方和 gui_error.log。
  pause
)
