@echo off
rem Windows GUI from source (no packing, no WSL): randomize_gui.bat [regulation.bin]
rem Needs uv (https://github.com/astral-sh/uv); the virtual environment lives in %USERPROFILE%\.venvs\er_mod.
rem This black window stays open to show error messages; closing it closes the GUI too. For a program without
rem the console window use the exe built by build_exe.bat.
rem Every failure stops with a pause so the error can be read.
rem All messages are ASCII on purpose: cmd shows UTF-8 text as garbage in the default code page.
setlocal
cd /d "%~dp0"
where uv >nul 2>&1 || (
  echo uv not found. Install it first (see the README, "Install"), then open a new window and run this again.
  goto :fail
)
set "VENV=%USERPROFILE%\.venvs\er_mod"
rem The dependencies only ship wheels for Python 3.10-3.14 (zstandard has none for 3.15 yet), so the venv is
rem created with a version range: an installed Python inside the range is used, otherwise uv downloads one.
rem See build_exe.bat for the details.
set "PYMIN=3.10"
set "PYMAX=3.15"
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
rem an older venv may lack Pillow (the backdrop image needs it)
"%VENV%\Scripts\python.exe" -I -c "import PIL" >nul 2>&1 || uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || goto :fail
set PYTHONDONTWRITEBYTECODE=1
"%VENV%\Scripts\python.exe" -I tools\gui.py %*
if errorlevel 1 (
  echo.
  echo The GUI did not exit normally; see the messages above and gui_error.log.
  pause
)
exit /b 0

:fail
echo.
echo Failed, see the messages above.
echo Common causes: uv finds no Python 3.10-3.14 and cannot download one (no network) - install Python 3.13 from
echo python.org (tick "tcl/tk and IDLE") and run again; or a package download failed - check the network and retry.
pause
exit /b 1
