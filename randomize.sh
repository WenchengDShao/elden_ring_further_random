#!/usr/bin/env bash
# 一键运行：./randomize.sh [--seed N] [--include-flasks] [--include-remembrances] [--split-anim [same|any]] [--weapons] [--no-spells] [--dry-run] [--output path]
set -e
cd "$(dirname "$0")"
VENV="$HOME/.venvs/er_mod"   # 项目盘是 exFAT，放不了 venv 的符号链接，所以 venv 放在家目录
# 依赖包只给 Python 3.10-3.14 发了 wheel（zstandard 还没有 3.15 的），所以限定版本范围：系统 Python 在范围内
# 就用它，否则 uv 下载一个托管的。已有的虚拟环境坏了（母体 Python 没了）或版本越界时删掉重建。
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
PYTHONDONTWRITEBYTECODE=1 exec "$VENV/bin/python" -I tools/randomize.py "$@"
