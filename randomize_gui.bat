@echo off
rem Windows 图形界面（不打包、不需要 WSL）：randomize_gui.bat [regulation.bin]
rem 需要 uv（https://github.com/astral-sh/uv）；虚拟环境建在 %USERPROFILE%\.venvs\er_mod。
rem 这个黑色窗口会一直开着，用来显示错误信息；关掉它图形界面也会关掉。不想要黑窗就用 build_exe.bat 打包出的 exe。
rem 任何一步失败都会停住等你看完错误再关窗口。
setlocal
cd /d "%~dp0"
where uv >nul 2>&1 || (
  echo 没找到 uv，请先安装（见 README 的“安装”一节），装完重开窗口再运行。
  goto :fail
)
set "VENV=%USERPROFILE%\.venvs\er_mod"
rem 依赖包只给 Python 3.10-3.14 发了 wheel（zstandard 还没有 3.15 的），所以限定版本范围：
rem 已装的 Python 在范围内就用它，否则 uv 下载一个托管的。详见 build_exe.bat。
set "PYMIN=3.10"
set "PYMAX=3.15"
set "RECREATE="
if not exist "%VENV%\Scripts\python.exe" set "RECREATE=1"
if not defined RECREATE (
  "%VENV%\Scripts\python.exe" -I tools\pycheck.py %PYMIN% %PYMAX% || set "RECREATE=1"
)
if defined RECREATE (
  if exist "%VENV%" (
    echo 虚拟环境 %VENV% 不可用或 Python 版本不在支持范围内，删掉重建。
    rmdir /s /q "%VENV%"
  )
  uv venv --python ">=%PYMIN%,<%PYMAX%" "%VENV%" || goto :fail
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || goto :fail
)
rem 旧的虚拟环境可能还没有 Pillow（背景图需要它）
"%VENV%\Scripts\python.exe" -I -c "import PIL" >nul 2>&1 || uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || goto :fail
set PYTHONDONTWRITEBYTECODE=1
"%VENV%\Scripts\python.exe" -I tools\gui.py %*
if errorlevel 1 (
  echo.
  echo 图形界面没有正常结束，错误信息见上方和 gui_error.log。
  pause
)
exit /b 0

:fail
echo.
echo 失败，错误信息见上方。
echo 常见原因：uv 找不到 3.10-3.14 的 Python 又下载不了（没网或被墙）——安装 python.org 的 Python 3.13
echo （勾选 "tcl/tk and IDLE"）后重新运行；或者下载依赖包失败——检查网络后重试。
pause
exit /b 1
