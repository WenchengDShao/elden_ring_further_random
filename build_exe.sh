#!/usr/bin/env bash
# Pack the GUI into one executable with PyInstaller: dist/ERFurtherRandom (for the platform this runs on;
# PyInstaller cannot cross-compile, use build_exe.bat on Windows).  paramdef/, names/, assets/ and
# liblinoodle.so go inside the executable, the game's oo2core_6_win64.dll does not (keep it next to the executable).
set -e
cd "$(dirname "$0")"
VENV="$HOME/.venvs/er_mod"
if [ ! -x "$VENV/bin/python" ]; then
  uv venv "$VENV"
  uv pip install --python "$VENV/bin/python" -r tools/requirements.txt
fi
"$VENV/bin/python" -I -c "import PIL" 2>/dev/null || uv pip install --python "$VENV/bin/python" -r tools/requirements.txt
# tkcheck.py fails loudly when Tk is unusable and prints TCL_LIBRARY / TK_LIBRARY exports for PyInstaller's hook
tkenv="$("$VENV/bin/python" -I tools/tkcheck.py)" || { echo "tkinter unusable (Ubuntu / WSL: sudo apt install python3-tk)"; exit 1; }
eval "$tkenv"
uv pip install --python "$VENV/bin/python" pyinstaller
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --onefile --windowed --name ERFurtherRandom \
  --add-data "$PWD/tools/paramdef:paramdef" --add-data "$PWD/tools/names:names" --add-data "$PWD/tools/assets:assets" \
  --add-data "$PWD/tools/linoodle/liblinoodle.so:linoodle" \
  --distpath dist --workpath build --specpath build tools/gui.py
echo
echo "built dist/ERFurtherRandom"
