@echo off
rem Windows one-shot run (no WSL): randomize.bat [options], same options as randomize.sh.
rem Needs uv (https://github.com/astral-sh/uv); the virtual environment lives in %USERPROFILE%\.venvs\er_mod.
rem All messages are ASCII on purpose: cmd shows UTF-8 text as garbage in the default code page.
setlocal
cd /d "%~dp0"
set "VENV=%USERPROFILE%\.venvs\er_mod"
rem The dependencies only ship wheels for Python 3.10-3.14, so the venv is created with a version range
rem (see build_exe.bat); an existing venv whose base Python was uninstalled or whose version is out of
rem range is deleted and recreated.
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
  uv venv --python ">=%PYMIN%,<%PYMAX%" "%VENV%" || exit /b 1
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || exit /b 1
)
set PYTHONDONTWRITEBYTECODE=1
"%VENV%\Scripts\python.exe" -I tools\randomize.py %*
