@echo off
rem Windows 一键运行（不需要 WSL）：randomize.bat [选项]，选项与 randomize.sh 相同。
rem 需要 uv（https://github.com/astral-sh/uv）；虚拟环境建在 %USERPROFILE%\.venvs\er_mod。
setlocal
cd /d "%~dp0"
set "VENV=%USERPROFILE%\.venvs\er_mod"
if not exist "%VENV%\Scripts\python.exe" (
  uv venv "%VENV%" || exit /b 1
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || exit /b 1
)
set PYTHONDONTWRITEBYTECODE=1
"%VENV%\Scripts\python.exe" -I tools\randomize.py %*
