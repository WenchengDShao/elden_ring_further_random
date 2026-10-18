#!/usr/bin/env python3
"""Check that Tk works with this Python and print the Tcl / Tk library paths for build_exe.bat / .sh.

stdout: one assignment per line in the caller's shell syntax (`set "TCL_LIBRARY=..."` on Windows,
`export TCL_LIBRARY='...'` elsewhere) so the build script can apply them before running PyInstaller:
its tkinter hook needs a working `tkinter.Tcl()` and honours TCL_LIBRARY / TK_LIBRARY, and the
uv-managed Windows Python cannot find init.tcl from inside a venv on its own (gui._tcl_env() fixes
that for the running process).  Diagnostics go to stderr; exit status 1 when Tk is unusable.

Tcl/Tk 9 on Windows (python.org 3.14) keeps the Tk script library inside tk90.dll and reports it as
`//zipfs:/lib/tk/tk_library`; PyInstaller recognises that prefix and skips the collection, so such a
path must be passed on verbatim (Path() would turn its slashes into backslashes, which
PyInstaller then treats as a missing directory and aborts the build; seen 2026-10-18).
"""
from __future__ import annotations

import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui  # noqa: E402  (runs _tcl_env() and imports tkinter)


def main() -> int:
    if gui.tk is None:
        print("tkinter cannot be imported:\n" + (gui.TK_ERROR or ""), file=sys.stderr)
        return 1
    try:
        root = gui.tk.Tk()
        root.withdraw()
        tcl_dir = root.tk.eval("info library")
        tk_dir = root.tk.eval("set tk_library")
        root.destroy()
    except Exception as e:
        print(f"Tk cannot be initialised: {e}", file=sys.stderr)
        return 1
    print(f"tkinter {gui.tk.TkVersion} from {sys.base_prefix}: tcl={tcl_dir} tk={tk_dir}", file=sys.stderr)
    for var, d in (("TCL_LIBRARY", tcl_dir), ("TK_LIBRARY", tk_dir)):
        if not d.startswith("//zipfs:/"):
            d = str(Path(d))
        print(f'set "{var}={d}"' if gui.WINDOWS else f"export {var}={shlex.quote(d)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
