#!/usr/bin/env bash
# Rebuild liblinoodle.so (Linux loader for the game's oo2core_6_win64.dll, used by tools/oodle.py).
# Needs git, cmake, g++.  Clones McSimp/linoodle + pe-parse, applies two small fixes
# (patched linoodle.cpp from this folder, missing #includes for current g++) and copies the .so here.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone --depth 1 --recurse-submodules -q https://github.com/McSimp/linoodle.git "$work/linoodle"
cd "$work/linoodle"
sed -i 's/-Werror//g' pe-parse/cmake/compilation_flags.cmake
sed -i '0,/#include/s//#include <utility>\n#include <cstdint>\n#include/' windows_library.cpp
cp "$here/linoodle.cpp" linoodle.cpp     # our patched copy: DLL path from $LINOODLE_DLL, OodleLZ_CompressOptions_GetDefault export
sed -i 's/option(BUILD_SHARED_LIBS "" OFF)/option(BUILD_SHARED_LIBS "" OFF)\nset(BUILD_COMMAND_LINE_TOOLS OFF CACHE BOOL "" FORCE)/' CMakeLists.txt
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release > /dev/null
cmake --build build --target linoodle -j"$(nproc)" > /dev/null
cp build/liblinoodle.so "$here/liblinoodle.so"
echo "built $here/liblinoodle.so"
