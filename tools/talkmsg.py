#!/usr/bin/env python3
"""Build names/TalkMsg.txt (the dialogue lines --random-dialogue relies on and reports) from the game's own
text archive:

    python tools/talkmsg.py "<game>/Game/msg/engus/menu_dlc02.msgbnd.dcx" --output tools/names/TalkMsg.txt

The dialogue text sits in the menu archive: msg/<language>/menu_dlc02.msgbnd.dcx holds TalkMsg.fmg (base
game), TalkMsg_dlc01.fmg (Shadow of the Erdtree) and TalkMsg_dlc02.fmg (a dummy); menu.msgbnd.dcx holds the
base game only.  In the game folder these live inside the Data0.bdt / DLC.bdt archives (UXM Selective
Unpacker extracts a single file); the Item and Enemy Randomizer and the Fog Gate Randomizer also write a
copy into their mod folders (mod/randomizer/msg/engus/menu_dlc02.msgbnd.dcx), which serves just as well.
The archive is DCX (KRAK in the game: the game's oo2core_6_win64.dll is needed, see --oodle-dll; DFLT in
the randomizers' output) around a BND4 of FMG files; every FMG whose name starts with TalkMsg is read and
the entries with a text are written as "<text id> <line>" (one per line, line breaks folded to spaces,
%null% / dummy / blank entries dropped).  Any language folder works (zhocn, jpnjp ...), the report is then
in that language; dialogue.py only needs the ids.  Several archives may be given, later ones override.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import erreg  # noqa: E402
import oodle  # noqa: E402

HERE = Path(__file__).resolve().parent
PLACEHOLDERS = {"%null%", "(dummyText)", "DLC dummy"}


def read_fmg(buf: bytes) -> dict[int, str]:
    """FMG version 2 (DS3 / Elden Ring, UTF-16): groups of consecutive ids pointing into an offset table."""
    if buf[0] != 0 or buf[1] != 0 or buf[2] != 2:
        raise ValueError("not a little-endian FMG version 2")
    groups, strings = struct.unpack_from("<ii", buf, 0x0C)
    offsets_at = struct.unpack_from("<q", buf, 0x18)[0]
    text: dict[int, str] = {}
    pos = 0x28
    for _ in range(groups):
        first_index, first_id, last_id = struct.unpack_from("<iii", buf, pos)
        pos += 0x10
        for i in range(last_id - first_id + 1):
            off = struct.unpack_from("<q", buf, offsets_at + 8 * (first_index + i))[0]
            if off == 0:
                continue
            end = buf.index(b"\0\0", off - off % 2) if off % 2 == 0 else off
            while end % 2:                               # the terminator must sit on a UTF-16 boundary
                end = buf.index(b"\0\0", end + 1)
            text[first_id + i] = buf[off:end].decode("utf-16-le")
    return text


def write_fmg(entries: dict[int, str]) -> bytes:
    """FMG version 2 as SoulsFormats writes it: runs of consecutive ids become groups, every entry has a
       string (callers drop ids they do not want instead of writing null offsets)."""
    ids = sorted(entries)
    groups: list[list[int]] = []
    for i in ids:
        if groups and groups[-1][1] + 1 == i:
            groups[-1][1] = i
        else:
            groups.append([i, i])
    offsets_at = 0x28 + 0x10 * len(groups)
    data_at = offsets_at + 8 * len(ids)
    strings = bytearray()
    offsets = []
    for i in ids:
        offsets.append(data_at + len(strings))
        strings += entries[i].encode("utf-16-le") + b"\0\0"
    head = bytearray(struct.pack("<BBBBiBBBBiiiqq", 0, 0, 2, 0, 0, 1, 0, 0, 0, len(groups), len(ids), 0xFF, offsets_at, 0))
    index = 0
    for first, last in groups:
        head += struct.pack("<iiii", index, first, last, 0)
        index += last - first + 1
    out = bytes(head) + b"".join(struct.pack("<q", o) for o in offsets) + bytes(strings)
    return struct.pack("<i", len(out)).join((out[:4], out[8:]))


def fmg_name(f) -> str:
    return f.name.replace("\\", "/").rsplit("/", 1)[-1]


def patch_archive(src: Path, texts: dict[int, str]) -> tuple[bytes, dict[str, int]]:
    """The archive `src` (DCX around a BND4 of FMGs) with `texts` written into its TalkMsg FMGs: an id that
       already exists somewhere (e.g. as %null%) is replaced in place, a new id goes to TalkMsg.fmg
       (9 digits and below) or TalkMsg_dlc01.fmg (10 digits, the Shadow of the Erdtree range).  Returns
       the DCX DFLT bytes and {fmg name: entries written}.  Every other file is copied byte for byte."""
    raw = src.read_bytes()
    bnd = erreg.read_bnd4(erreg.read_dcx(raw).data if raw[:4] == b"DCX\0" else raw)
    fmgs = {f.index: read_fmg(bnd.datas[f.index]) for f in bnd.files
            if fmg_name(f).lower().startswith("talkmsg") and fmg_name(f).lower().endswith(".fmg")}
    if not fmgs:
        raise SystemExit(f"{src}: no TalkMsg*.fmg inside")
    by_name = {fmg_name(bnd.files[i]).lower(): i for i in fmgs}
    base = by_name.get("talkmsg.fmg", next(iter(fmgs)))
    dlc = by_name.get("talkmsg_dlc01.fmg", base)
    written: dict[str, int] = {}
    changed: set[int] = set()
    for tid, text in texts.items():
        where = next((i for i, e in fmgs.items() if tid in e), dlc if tid >= 1_000_000_000 else base)
        fmgs[where][tid] = text
        changed.add(where)
        written[fmg_name(bnd.files[where])] = written.get(fmg_name(bnd.files[where]), 0) + 1
    datas = list(bnd.datas)
    for i in changed:
        datas[i] = write_fmg(fmgs[i])
    data = erreg.write_bnd4(erreg.Bnd4(bnd.head, bnd.files, datas, bnd.file_header_size,
                                       bnd.has_compression, bnd.long_offsets))
    return erreg.write_dcx(erreg.Dcx(9, data, erreg.CODEC_DEFLATE)), written


def read_archive(path: Path) -> dict[int, str]:
    raw = path.read_bytes()
    bnd = erreg.read_bnd4(erreg.read_dcx(raw).data if raw[:4] == b"DCX\0" else raw)
    text: dict[int, str] = {}
    for f in bnd.files:
        name = fmg_name(f)
        if name.lower().startswith("talkmsg") and name.lower().endswith(".fmg"):
            got = read_fmg(bnd.datas[f.index])
            print(f"# {path.name}: {name} {len(got)} entries", file=sys.stderr)
            text.update(got)
    if not text:
        raise SystemExit(f"{path}: no TalkMsg*.fmg inside")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive", nargs="+", help="menu_dlc02.msgbnd.dcx / menu.msgbnd.dcx (or an unpacked .msgbnd)")
    ap.add_argument("--output", default=str(HERE / "names" / "TalkMsg.txt"))
    ap.add_argument("--oodle-dll", default=None, metavar="PATH", help=f"{oodle.DLL_NAME} for KRAK archives")
    args = ap.parse_args(argv)
    if args.oodle_dll is not None and not oodle.use_dll(args.oodle_dll):
        raise SystemExit(f"--oodle-dll: {args.oodle_dll} does not exist")
    text: dict[int, str] = {}
    for a in args.archive:
        text.update(read_archive(Path(a)))
    kept = {i: " ".join(t.split()) for i, t in text.items()}
    kept = {i: t for i, t in kept.items() if t and t not in PLACEHOLDERS}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(f"{i} {t}\n" for i, t in sorted(kept.items())), encoding="utf-8")
    print(f"# wrote {out}: {len(kept)} lines with text ({len(text) - len(kept)} empty / placeholder entries dropped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
