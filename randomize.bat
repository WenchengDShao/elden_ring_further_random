@echo off
rem Windows 一键运行（不需要 WSL）：randomize.bat [选项]，选项与 randomize.sh 相同。
rem 需要 uv（https://github.com/astral-sh/uv）；虚拟环境建在 %USERPROFILE%\.venvs\er_mod。
setlocal
cd /d "%~dp0"
set "VENV=%USERPROFILE%\.venvs\er_mod"
rem 依赖包只给 Python 3.10-3.14 发了 wheel，所以限定版本范围（详见 build_exe.bat）；已有的虚拟环境
rem 母体 Python 被卸载或版本不在范围内时删掉重建。
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
  uv venv --python ">=%PYMIN%,<%PYMAX%" "%VENV%" || exit /b 1
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || exit /b 1
)
set PYTHONDONTWRITEBYTECODE=1
"%VENV%\Scripts\python.exe" -I tools\randomize.py %*
