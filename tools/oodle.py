"""Oodle (Kraken / Leviathan) compression through the game's own oo2core_6_win64.dll.

On Windows the DLL is loaded directly with ctypes.  On Linux (incl. WSL) it is loaded by linoodle,
a tiny PE loader (McSimp/linoodle): the prebuilt tools/linoodle/liblinoodle.so (x86_64, glibc >= 2.28,
libc++ linked in) is used; tools/linoodle/build.sh rebuilds it from source.
The DLL itself is not shipped here: it is expected in the current directory (./oo2core_6_win64.dll;
randomize.sh runs from the project folder, so er_mod/oo2core_6_win64.dll) or at $OODLE_DLL / --oodle-dll.
Copy it from the game folder (Steam\\steamapps\\common\\ELDEN RING\\Game\\) or from any ModEngine2 mod
folder (the fog gate and item randomizers carry one each).
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE / "linoodle" / "liblinoodle.so"
WINDOWS = sys.platform == "win32"          # load the game's DLL directly, no linoodle needed
DLL_NAME = "oo2core_6_win64.dll"

# OodleLZ_Compressor ids and OodleLZ_CompressionLevel values of Oodle 2.6
KRAKEN, MERMAID, SELKIE, HYDRA, LEVIATHAN = 8, 9, 11, 12, 13
CODECS = {"kraken": KRAKEN, "leviathan": LEVIATHAN}
LEVEL_OPTIMAL5 = 9

_lib = None


def find_dll() -> Path | None:
    """$OODLE_DLL (also set by --oodle-dll) wins; otherwise only ./oo2core_6_win64.dll in the current
       directory is used (no search of the game / mod folders any more)."""
    env = os.environ.get("OODLE_DLL")
    if env and Path(env).is_file():
        return Path(env)
    p = Path.cwd() / DLL_NAME
    return p if p.is_file() else None


def available() -> str | None:
    """None when usable, else the reason it is not."""
    if not WINDOWS and not LIB.is_file():
        return f"{LIB} missing (run tools/linoodle/build.sh)"
    if find_dll() is None:
        return (f"{DLL_NAME} not found in the current directory ({Path.cwd()}); copy it there or set "
                f"OODLE_DLL=/path/to/{DLL_NAME}")
    return None


def missing_dll() -> bool:
    return (WINDOWS or LIB.is_file()) and find_dll() is None


def use_dll(path: str | os.PathLike) -> bool:
    """Point the module at a user-supplied DLL; False if the file does not exist."""
    p = Path(path).expanduser()
    if not p.is_file():
        return False
    os.environ["OODLE_DLL"] = str(p.resolve())
    return True


def _load():
    global _lib
    if _lib is None:
        why = available()
        if why:
            raise RuntimeError(why)
        if WINDOWS:
            lib = ctypes.WinDLL(str(find_dll()))     # same three exports as the linoodle wrapper
        else:
            os.environ["LINOODLE_DLL"] = str(find_dll())
            lib = ctypes.CDLL(str(LIB))
        lib.OodleLZ_Compress.restype = ctypes.c_size_t
        lib.OodleLZ_Compress.argtypes = [ctypes.c_int64, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                                         ctypes.c_int64, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                                         ctypes.c_void_p, ctypes.c_size_t]
        lib.OodleLZ_CompressOptions_GetDefault.restype = ctypes.c_void_p
        lib.OodleLZ_CompressOptions_GetDefault.argtypes = [ctypes.c_int64, ctypes.c_int64]
        lib.OodleLZ_Decompress.restype = ctypes.c_size_t
        lib.OodleLZ_Decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p,
                                           ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_size_t, ctypes.c_int64]
        _lib = lib
    return _lib


# OodleLZ_CompressOptions (Oodle 2.6 layout, first fields): u32 verbosity, s32 minMatchLen,
# s32 seekChunkReset, s32 seekChunkLen, ...  The game decodes DCX KRAK in independent 256 KB
# seek chunks; SoulsFormats sets seekChunkReset = true / seekChunkLen = 0x40000 ("required for the
# game to not crash") and a stream compressed with the plain defaults did crash it (2026-10-17).
OPTIONS_SIZE = 0x60
SEEK_CHUNK_LEN = 0x40000


def compress_options(codec: int, level: int, seek_chunk: int | None = SEEK_CHUNK_LEN) -> ctypes.Array:
    lib = _load()
    ptr = lib.OodleLZ_CompressOptions_GetDefault(codec, level)
    opts = ctypes.create_string_buffer(ctypes.string_at(ptr, OPTIONS_SIZE), OPTIONS_SIZE)
    if seek_chunk:
        struct.pack_into("<ii", opts, 8, 1, seek_chunk)      # seekChunkReset, seekChunkLen
    return opts


def compress(data: bytes, codec: int = KRAKEN, level: int = LEVEL_OPTIMAL5,
             seek_chunk: int | None = SEEK_CHUNK_LEN) -> bytes:
    lib = _load()
    opts = compress_options(codec, level, seek_chunk)
    src = ctypes.create_string_buffer(data, len(data))
    cap = len(data) + 274 * ((len(data) + 0x3FFFF) // 0x40000) + 0x1000
    dst = ctypes.create_string_buffer(cap)
    n = lib.OodleLZ_Compress(codec, src, len(data), dst, level, opts, 0, 0, None, 0)
    if n <= 0 or n > cap:
        raise RuntimeError(f"OodleLZ_Compress returned {n}")
    return dst.raw[:n]


def decompress(comp: bytes, raw_len: int) -> bytes:
    lib = _load()
    src = ctypes.create_string_buffer(comp, len(comp))
    dst = ctypes.create_string_buffer(raw_len + 0x1000)
    n = lib.OodleLZ_Decompress(src, len(comp), dst, raw_len, 1, 0, 0, None, 0, None, None, None, 0, 3)
    if n != raw_len:
        raise RuntimeError(f"OodleLZ_Decompress returned {n}, expected {raw_len}")
    return dst.raw[:raw_len]
