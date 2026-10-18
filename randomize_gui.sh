#!/usr/bin/env bash
# GUI: ./randomize_gui.sh [regulation.bin]  (Linux needs tkinter: on Ubuntu / WSL  sudo apt install python3-tk)
set -e
cd "$(dirname "$0")"
VENV="$HOME/.venvs/er_mod"
# Python 3.10-3.14 (the range the dependencies ship wheels for, see randomize.sh); a broken or out-of-range venv is recreated
PYMIN=3.10
PYMAX=3.15
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -I tools/pycheck.py "$PYMIN" "$PYMAX"; then
  if [ -e "$VENV" ]; then
    echo "The virtual environment $VENV is unusable or its Python is out of range, recreating it"
    rm -rf "$VENV"
  fi
  uv venv --python ">=$PYMIN,<$PYMAX" "$VENV"
  uv pip install --python "$VENV/bin/python" -r tools/requirements.txt
fi
# an older venv may lack Pillow (backdrop image)
"$VENV/bin/python" -I -c "import PIL" 2>/dev/null || uv pip install --python "$VENV/bin/python" -r tools/requirements.txt
PYTHONDONTWRITEBYTECODE=1 exec "$VENV/bin/python" -I tools/gui.py "$@"
