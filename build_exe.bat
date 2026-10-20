@echo off
rem Pack the GUI into one executable: dist\ERFurtherRandom.exe (PyInstaller; the first run installs it into
rem %USERPROFILE%\.venvs\er_mod).  paramdef\, names\ and assets\ (backdrop image) go inside the exe;
rem oo2core_6_win64.dll does not: keep it next to the exe or pick it in the window.
rem The text archives tools\msg\<language>\menu_dlc02.msgbnd.dcx (joke shifu) are copied next to the exe as
rem dist\msg\<language>\...: upload the exe together with the msg folder. The DLL is never shipped - it is RAD Game
rem Tools' and comes with the game - the user copies it from the game folder.
rem Every failure stops with a pause so the error can be read (the window does not just flash and close).
rem All messages are ASCII on purpose: cmd shows UTF-8 text as garbage in the default code page.
rem No parentheses inside echo lines within ( ) blocks: an unescaped ) there ends the block and kills the script.
setlocal
cd /d "%~dp0"
where uv >nul 2>&1 || (
  echo uv not found. Install it first - see the README section "Install" - then open a new window and run this again.
  goto :fail
)
set "VENV=%USERPROFILE%\.venvs\er_mod"
rem The dependencies only ship wheels for Python 3.10-3.14 (zstandard has none for 3.15 yet); a newer Python
rem makes pip compile from source and fail, so the venv is created with a version range: an installed Python
rem inside the range is used, otherwise uv downloads a managed one.
set "PYMIN=3.10"
set "PYMAX=3.15"
rem An existing venv is test-run with tools\pycheck.py first: when its base Python was uninstalled the
rem launcher fails with "did not find executable", and a version outside the range is unusable too;
rem both cases delete and recreate the venv.
set "RECREATE="
if not exist "%VENV%\Scripts\python.exe" set "RECREATE=1"
if not defined RECREATE (
  "%VENV%\Scripts\python.exe" -I tools\pycheck.py %PYMIN% %PYMAX% || set "RECREATE=1"
)
if defined RECREATE (
  if exist "%VENV%" (
    echo The virtual environment %VENV% is unusable or its Python is out of range, recreating it.
    rmdir /s /q "%VENV%"
  )
  uv venv --python ">=%PYMIN%,<%PYMAX%" "%VENV%" || goto :fail
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || goto :fail
)
"%VENV%\Scripts\python.exe" -I -c "import PIL" >nul 2>&1 || uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || goto :fail
rem tools\tkcheck.py makes sure Tk works and prints "set" lines for TCL_LIBRARY / TK_LIBRARY: a uv-managed
rem Python cannot find init.tcl from inside a venv on its own, and PyInstaller's tkinter hook needs the two
rem variables to put the Tcl/Tk script libraries into the exe.
set "TKENV=%TEMP%\er_tkenv.bat"
"%VENV%\Scripts\python.exe" -I tools\tkcheck.py > "%TKENV%"
if errorlevel 1 (
  echo.
  echo This virtual environment's Python has no usable tkinter; the packed exe would have no window. Stopped.
  echo Install Python from python.org with "tcl/tk and IDLE" ticked, delete %VENV% and run this script again.
  goto :fail
)
call "%TKENV%"
del "%TKENV%"
echo TCL_LIBRARY=%TCL_LIBRARY%
echo TK_LIBRARY=%TK_LIBRARY%
uv pip install --python "%VENV%\Scripts\python.exe" pyinstaller || goto :fail
rem PyInstaller's full output goes to build\pyinstaller.log (send that file when something goes wrong);
rem on failure it is shown in full.
if not exist build mkdir build
set "LOG=%~dp0build\pyinstaller.log"
echo Packing, this takes a minute or two; the full output is written to %LOG% ...
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name ERFurtherRandom ^
  --add-data "%~dp0tools\paramdef;paramdef" --add-data "%~dp0tools\names;names" --add-data "%~dp0tools\assets;assets" ^
  --distpath dist --workpath build --specpath build tools\gui.py > "%LOG%" 2>&1 || (
  type "%LOG%"
  echo.
  echo PyInstaller failed; the output above is its complete log, also saved as %LOG%.
  goto :fail
)
findstr /i /c:"WARNING" /c:"ERROR" "%LOG%"
if not exist "dist\ERFurtherRandom.exe" (
  echo.
  echo PyInstaller reported no error, but dist\ERFurtherRandom.exe does not exist. Most likely Windows Defender
  echo quarantined the fresh exe - PyInstaller programs are often false positives. Open "Windows Security -
  echo Virus and threat protection - Protection history", restore and allow ERFurtherRandom.exe, or add this
  echo folder to the exclusions and run this script again. If the history shows nothing, send %LOG%.
  goto :fail
)
for /d %%L in (tools\msg\*) do (
  if exist "%%L\menu_dlc02.msgbnd.dcx" (
    if not exist "dist\msg\%%~nxL" mkdir "dist\msg\%%~nxL"
    copy /y "%%L\menu_dlc02.msgbnd.dcx" "dist\msg\%%~nxL\" >nul || goto :fail
  )
)
echo.
for %%F in (dist\ERFurtherRandom.exe) do echo built %%~fF  (%%~zF bytes)
dir /b /s dist\msg
echo Upload ERFurtherRandom.exe together with the msg folder: the joke shifu reads msg\engus and msg\zhocn next to the exe.
echo The game's oo2core_6_win64.dll is not shipped; users copy it from the game folder.
echo If double-clicking it shows no window, the error is shown in a message box and written to gui_error.log next to the exe.
pause
exit /b 0

:fail
echo.
echo Failed, see the messages above.
echo Common causes: uv finds no Python 3.10-3.14 and cannot download one (no network) - install Python 3.13 from
echo python.org (tick "tcl/tk and IDLE") and run again; or a package download failed - check the network and retry.
pause
exit /b 1
