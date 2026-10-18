#!/usr/bin/env bash
# 图形界面：./randomize_gui.sh [regulation.bin]（Linux 需要 tkinter：Ubuntu / WSL 下 sudo apt install python3-tk）
set -e
cd "$(dirname "$0")"
VENV="$HOME/.venvs/er_mod"
# Python 3.10-3.14（依赖包的 wheel 范围，见 randomize.sh）；坏掉或版本越界的虚拟环境删掉重建
PYMIN=3.10
PYMAX=3.15
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -I tools/pycheck.py "$PYMIN" "$PYMAX"; then
  if [ -e "$VENV" ]; then
    echo "虚拟环境 $VENV 不可用或 Python 版本不在支持范围内，删掉重建"
    rm -rf "$VENV"
  fi
  uv venv --python ">=$PYMIN,<$PYMAX" "$VENV"
  uv pip install --python "$VENV/bin/python" -r tools/requirements.txt
fi
# an older venv may lack Pillow (backdrop image)
"$VENV/bin/python" -I -c "import PIL" 2>/dev/null || uv pip install --python "$VENV/bin/python" -r tools/requirements.txt
PYTHONDONTWRITEBYTECODE=1 exec "$VENV/bin/python" -I tools/gui.py "$@"
