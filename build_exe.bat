@echo off
rem 把图形界面打包成单个 exe：dist\ERFurtherRandom.exe（PyInstaller，首次运行会装进 %USERPROFILE%\.venvs\er_mod）。
rem paramdef\、names\ 和 assets\（背景图）会打进 exe；oo2core_6_win64.dll 不会，使用时放在 exe 旁边或在界面里选择。
rem 任何一步失败都会停住等你看完错误再关窗口（双击运行时窗口不会一闪而过）。
setlocal
cd /d "%~dp0"
where uv >nul 2>&1 || (
  echo 没找到 uv，请先安装（见 README 的“安装”一节），装完重开窗口再运行。
  goto :fail
)
set "VENV=%USERPROFILE%\.venvs\er_mod"
rem 依赖包只给 Python 3.10-3.14 发了 wheel（zstandard 还没有 3.15 的），太新的 Python 会去编译源码然后失败，
rem 所以建虚拟环境时限定版本范围：已装的 Python 在范围内就用它，否则 uv 下载一个托管的。
set "PYMIN=3.10"
set "PYMAX=3.15"
rem 已有的虚拟环境先试跑一次 tools\pycheck.py：母体 Python 被卸载时它的 python.exe 会报 "did not find executable"，
rem Python 版本不在范围内也不能用，这两种情况都删掉重建。
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
"%VENV%\Scripts\python.exe" -I -c "import PIL" >nul 2>&1 || uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || goto :fail
rem tools\tkcheck.py 确认 Tk 可用，并输出 TCL_LIBRARY / TK_LIBRARY 的 set 语句：uv 托管的 Python 在虚拟环境里
rem 自己找不到 init.tcl，PyInstaller 的 tkinter hook 需要这两个变量才能把 Tcl/Tk 的脚本库打进 exe。
set "TKENV=%TEMP%\er_tkenv.bat"
"%VENV%\Scripts\python.exe" -I tools\tkcheck.py > "%TKENV%"
if errorlevel 1 (
  echo.
  echo 这个虚拟环境的 Python 没有可用的 tkinter，打包出来的 exe 不会有窗口，已停止。
  echo 请安装 python.org 的 Python（安装时勾选 "tcl/tk and IDLE"），删除 %VENV% 后重新运行本脚本。
  goto :fail
)
call "%TKENV%"
del "%TKENV%"
echo TCL_LIBRARY=%TCL_LIBRARY%
echo TK_LIBRARY=%TK_LIBRARY%
uv pip install --python "%VENV%\Scripts\python.exe" pyinstaller || goto :fail
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name ERFurtherRandom ^
  --add-data "%~dp0tools\paramdef;paramdef" --add-data "%~dp0tools\names;names" --add-data "%~dp0tools\assets;assets" ^
  --distpath dist --workpath build --specpath build tools\gui.py || goto :fail
echo.
echo built dist\ERFurtherRandom.exe
echo 如果双击它没有窗口，错误信息会弹窗显示并写在 exe 旁边的 gui_error.log 里。
pause
exit /b 0

:fail
echo.
echo 失败，错误信息见上方。
echo 常见原因：uv 找不到 3.10-3.14 的 Python 又下载不了（没网或被墙）——安装 python.org 的 Python 3.13
echo （勾选 "tcl/tk and IDLE"）后重新运行；或者下载依赖包失败——检查网络后重试。
pause
exit /b 1
