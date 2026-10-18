#!/usr/bin/env bash
# One-shot run: ./randomize.sh [--seed N] [--include-flasks] [--include-remembrances] [--split-anim [same|any]] [--weapons] [--no-spells] [--dry-run] [--output path]
set -e
cd "$(dirname "$0")"
VENV="$HOME/.venvs/er_mod"   # the project drive is exFAT and cannot hold a venv's symlinks, so the venv lives in $HOME
# The dependencies only ship wheels for Python 3.10-3.14 (zstandard has none for 3.15 yet), so the venv is created
# with a version range: a system Python inside the range is used, otherwise uv downloads one.  An existing venv
# whose base Python is gone or whose version is out of range is deleted and recreated.
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
PYTHONDONTWRITEBYTECODE=1 exec "$VENV/bin/python" -I tools/randomize.py "$@"
