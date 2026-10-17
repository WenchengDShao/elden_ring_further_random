#!/usr/bin/env bash
# Rebuild liblinoodle.so (Linux / WSL loader for the game's oo2core_6_win64.dll, used by tools/oodle.py).
# Needs git, cmake and a C++ compiler (Ubuntu / WSL: sudo apt install git cmake g++).
# Clones McSimp/linoodle + pe-parse, applies small fixes (patched linoodle.cpp from this folder, missing
# #includes for current g++ / clang, pe-parse built with -w instead of -Werror) and copies the .so here.
#
# Portable build (how the shipped .so was made): set ZIG=/path/to/zig (https://ziglang.org/download/,
# 0.15.x) and the library is compiled with Zig's clang against glibc 2.28 with libc++ linked in, so it
# loads on any x86_64 distro from Ubuntu 18.10 / Debian 10 on.  Without ZIG the system g++ is used and the
# result needs the glibc / libstdc++ of the machine it was built on (or newer).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
for t in git cmake; do
  command -v "$t" >/dev/null || { echo "need $t (Ubuntu / WSL: sudo apt install git cmake g++)"; exit 1; }
done
if [ -n "${ZIG:-}" ]; then
  [ -x "$ZIG" ] || { echo "ZIG=$ZIG is not an executable"; exit 1; }
else
  command -v g++ >/dev/null || { echo "need g++ (Ubuntu / WSL: sudo apt install git cmake g++)"; exit 1; }
fi
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone --depth 1 --recurse-submodules -q https://github.com/McSimp/linoodle.git "$work/linoodle"
cd "$work/linoodle"
sed -i 's/-Werror/-w/g' pe-parse/cmake/compilation_flags.cmake      # third-party code: no -Werror, no warnings
sed -i '0,/#include/s//#include <utility>\n#include <cstdint>\n#include/' windows_library.cpp
sed -i '0,/#include/s//#include <clocale>\n#include/' windows_api.cpp            # LC_ALL with clang / zig
cp "$here/linoodle.cpp" linoodle.cpp     # our patched copy: DLL path from $LINOODLE_DLL, OodleLZ_CompressOptions_GetDefault export
sed -i 's/option(BUILD_SHARED_LIBS "" OFF)/option(BUILD_SHARED_LIBS "" OFF)\nset(BUILD_COMMAND_LINE_TOOLS OFF CACHE BOOL "" FORCE)/' CMakeLists.txt
flags=(-DCMAKE_BUILD_TYPE=Release)
if [ -n "${ZIG:-}" ]; then
  printf '#!/bin/sh\nexec "%s" cc -target x86_64-linux-gnu.2.28 "$@"\n' "$ZIG" > "$work/zcc"
  printf '#!/bin/sh\nexec "%s" c++ -target x86_64-linux-gnu.2.28 "$@"\n' "$ZIG" > "$work/zcxx"
  chmod +x "$work/zcc" "$work/zcxx"
  flags+=(-DCMAKE_C_COMPILER="$work/zcc" -DCMAKE_CXX_COMPILER="$work/zcxx" -DCMAKE_ASM_COMPILER="$work/zcc")
fi
cmake -S . -B build "${flags[@]}" > /dev/null
cmake --build build --target linoodle -j"$(nproc)" > /dev/null
cp build/liblinoodle.so "$here/liblinoodle.so"
echo "built $here/liblinoodle.so"
