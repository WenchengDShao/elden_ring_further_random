@echo off
rem 把图形界面打包成单个 exe：dist\ERFurtherRandom.exe（PyInstaller，首次运行会装进 %USERPROFILE%\.venvs\er_mod）。
rem paramdef\ 和 names\ 会打进 exe；oo2core_6_win64.dll 不会，使用时放在 exe 旁边或在界面里选择。
setlocal
cd /d "%~dp0"
set "VENV=%USERPROFILE%\.venvs\er_mod"
if not exist "%VENV%\Scripts\python.exe" (
  uv venv "%VENV%" || exit /b 1
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || exit /b 1
)
"%VENV%\Scripts\python.exe" -I -c "import sys, tkinter; r = tkinter.Tk(); r.withdraw(); r.destroy(); print('tkinter', tkinter.TkVersion, 'from', sys.base_prefix)"
if errorlevel 1 (
  echo.
  echo 这个虚拟环境的 Python 没有可用的 tkinter，打包出来的 exe 不会有窗口，已停止。
  echo 请安装 python.org 的 Python（安装时勾选 "tcl/tk and IDLE"），删除 %VENV% 后重新运行本脚本。
  pause
  exit /b 1
)
uv pip install --python "%VENV%\Scripts\python.exe" pyinstaller || exit /b 1
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name ERFurtherRandom ^
  --add-data "%~dp0tools\paramdef;paramdef" --add-data "%~dp0tools\names;names" ^
  --distpath dist --workpath build --specpath build tools\gui.py || exit /b 1
echo.
echo built dist\ERFurtherRandom.exe
echo 如果双击它没有窗口，错误信息会弹窗显示并写在 exe 旁边的 gui_error.log 里。
