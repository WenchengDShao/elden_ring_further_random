#!/usr/bin/env python3
"""Exit 0 when this Python's version is inside [MIN, MAX): pycheck.py 3.10 3.15

The launcher / build scripts run it with the virtual environment's python to decide whether that
environment can be kept: a broken venv launcher (base interpreter uninstalled) or a Python the
dependencies have no wheels for (zstandard had none for 3.15 in October 2026) both mean "recreate".
"""
import sys


def ver(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split("."))


lo, hi = ver(sys.argv[1]), ver(sys.argv[2])
ok = lo <= sys.version_info[:2] < hi
print(f"Python {sys.version.split()[0]} at {sys.executable}: "
      + ("ok" if ok else f"not in [{sys.argv[1]}, {sys.argv[2]})"), file=sys.stderr)
sys.exit(0 if ok else 1)
