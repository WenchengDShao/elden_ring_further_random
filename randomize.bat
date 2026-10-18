@echo off
rem Windows 一键运行（不需要 WSL）：randomize.bat [选项]，选项与 randomize.sh 相同。
rem 需要 uv（https://github.com/astral-sh/uv）；虚拟环境建在 %USERPROFILE%\.venvs\er_mod。
setlocal
cd /d "%~dp0"
set "VENV=%USERPROFILE%\.venvs\er_mod"
rem 母体 Python 被卸载或移走后虚拟环境的 python.exe 会报 "did not find executable"，这时删掉重建
if exist "%VENV%\Scripts\python.exe" (
  "%VENV%\Scripts\python.exe" -I -c "pass" >nul 2>&1 || (
    echo 虚拟环境 %VENV% 依赖的 Python 已不存在，删掉重建。
    rmdir /s /q "%VENV%"
  )
)
if not exist "%VENV%\Scripts\python.exe" (
  uv venv "%VENV%" || exit /b 1
  uv pip install --python "%VENV%\Scripts\python.exe" -r tools\requirements.txt || exit /b 1
)
set PYTHONDONTWRITEBYTECODE=1
"%VENV%\Scripts\python.exe" -I tools\randomize.py %*
