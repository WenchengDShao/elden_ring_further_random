#!/usr/bin/env bash
# 图形界面：./randomize_gui.sh [regulation.bin]（Linux 需要 tkinter：Ubuntu / WSL 下 sudo apt install python3-tk）
set -e
cd "$(dirname "$0")"
VENV="$HOME/.venvs/er_mod"
if [ ! -x "$VENV/bin/python" ]; then
  uv venv "$VENV"
  uv pip install --python "$VENV/bin/python" -r tools/requirements.txt
fi
PYTHONDONTWRITEBYTECODE=1 exec "$VENV/bin/python" -I tools/gui.py "$@"
