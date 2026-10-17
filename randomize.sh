#!/usr/bin/env bash
# 一键运行：./randomize.sh [--seed N] [--include-flasks] [--include-remembrances] [--split-anim [same|any]] [--weapons] [--no-spells] [--dry-run] [--output path]
set -e
cd "$(dirname "$0")"
VENV="$HOME/.venvs/er_mod"   # 项目盘是 exFAT，放不了 venv 的符号链接，所以 venv 放在家目录
if [ ! -x "$VENV/bin/python" ]; then
  uv venv "$VENV"
  uv pip install --python "$VENV/bin/python" -r tools/requirements.txt
fi
PYTHONDONTWRITEBYTECODE=1 exec "$VENV/bin/python" -I tools/randomize.py "$@"
