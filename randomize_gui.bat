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
rem 虚拟环境只是指向母体 Python 的壳：母体被卸载或移走后它的 python.exe 会报 "did not find executable"，
rem 这时把它删掉重建，而不是让后面每一步都失败。
if exist "%VENV%\Scripts\python.exe" (
  "%VENV%\Scripts\python.exe" -I -c "pass" >nul 2>&1 || (
    echo 虚拟环境 %VENV% 依赖的 Python 已不存在，删掉重建。
    rmdir /s /q "%VENV%"
  )
)
if not exist "%VENV%\Scripts\python.exe" (
  uv venv "%VENV%" || goto :fail
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
echo 常见原因：uv 找不到可用的 Python，又下载不了托管的 Python（没网或被墙）——安装 python.org 的 Python
echo （勾选 "tcl/tk and IDLE"）后重新运行；或者下载依赖包失败——检查网络后重试。
pause
exit /b 1
