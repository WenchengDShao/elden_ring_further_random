"""Reader/writer for Elden Ring regulation.bin (AES-CBC + DCX/ZSTD + BND4 + PARAM).

Supports in-place field edits and adding rows to a param; the BND4 is rebuilt on save.
Unmodified params are written back byte-for-byte.
"""
from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import zstandard
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import oodle

ER_REGULATION_KEY = bytes.fromhex(
    "99BFFC366A6BC8C6F5827D093602D676C42892A01C207FB024D3AF4E493FEF99"
)

# ----------------------------------------------------------------------------
# Encryption
# ----------------------------------------------------------------------------

def decrypt_regulation(data: bytes) -> bytes:
    iv, body = data[:16], data[16:]
    dec = Cipher(algorithms.AES(ER_REGULATION_KEY), modes.CBC(iv)).decryptor()
    return dec.update(body) + dec.finalize()


def encrypt_regulation(plain: bytes, iv: bytes = bytes(16)) -> bytes:
    """AES-256-CBC with PKCS#7 padding, exactly like the shipped file and SoulsFormats:
    the DCX is already 16-byte aligned, so a full block of 0x10 bytes is appended."""
    n = 16 - len(plain) % 16
    plain += bytes([n]) * n
    enc = Cipher(algorithms.AES(ER_REGULATION_KEY), modes.CBC(iv)).encryptor()
    return iv + enc.update(plain) + enc.finalize()


# ----------------------------------------------------------------------------
# DCX: ZSTD (fog gate / item randomizer output) and KRAK (the shipped regulation.bin, Oodle)
# ----------------------------------------------------------------------------

CODEC_ZSTD, CODEC_KRAKEN, CODEC_LEVIATHAN = "zstd", "kraken", "leviathan"
CODECS = (CODEC_ZSTD, CODEC_KRAKEN, CODEC_LEVIATHAN)


@dataclass
class Dcx:
    level: int
    data: bytes  # uncompressed payload
    codec: str = CODEC_ZSTD


def read_dcx(buf: bytes) -> Dcx:
    if buf[:4] != b"DCX\0":
        raise ValueError("not a DCX")
    fmt = buf[0x28:0x2C]
    uncomp, comp = struct.unpack(">II", buf[0x1C:0x24])
    level = buf[0x30]
    payload = buf[0x4C:0x4C + comp]
    if fmt == b"ZSTD":
        out = zstandard.ZstdDecompressor().decompressobj().decompress(payload)
        codec = CODEC_ZSTD
    elif fmt == b"KRAK":
        out = oodle.decompress(payload, uncomp)
        codec = CODEC_KRAKEN
    else:
        raise ValueError(f"unsupported DCX compression {fmt!r} (ZSTD and KRAK are implemented)")
    if len(out) != uncomp:
        raise ValueError(f"DCX size mismatch {len(out)} != {uncomp}")
    return Dcx(level=level, data=out, codec=codec)


# The game keeps a copy of regulation.bin inside the save file (USER_DATA_11, 0x240010 bytes).
# A regulation.bin larger than this is reported as "save data corrupted" at the main menu,
# even when no save file exists (found 2026-10-17 after bisecting ~55 builds; the content
# never mattered, only the encrypted file size).
REGULATION_MAX_SIZE = 0x240000


def write_dcx(dcx: Dcx, window_log: int = 16) -> bytes:
    """ZSTD: the only ZSTD framing known to load in-game (fog gate / item randomizer output):
    64 KB window, no content size, no checksum, single frame (a 4 MB window crashed the game,
    2026-10-17).  Only the window matters to the decoder; the compression level is free.
    KRAK: the shipped regulation.bin's own format (Oodle Kraken, header level byte 6, same
    layout as SoulsFormats' DCX_KRAK_6); no window limit, so it compresses much better.
    "leviathan" writes an Oodle Leviathan stream under the same KRAK tag (OodleLZ_Decompress
    detects the codec from the stream itself)."""
    if dcx.codec == CODEC_ZSTD:
        params = zstandard.ZstdCompressionParameters.from_level(
            dcx.level, window_log=window_log, write_content_size=0, write_checksum=0, threads=0)
        comp = zstandard.ZstdCompressor(compression_params=params).compress(dcx.data)
        tag, level = b"ZSTD", dcx.level
    else:
        comp = oodle.compress(dcx.data, oodle.CODECS[dcx.codec], oodle.LEVEL_OPTIMAL5)
        tag, level = b"KRAK", 6
    hdr = struct.pack(
        ">4sIIIII4sII4s4sIB3sIIII4sI",
        b"DCX\0", 0x11000, 0x18, 0x24, 0x44, 0x4C,
        b"DCS\0", len(dcx.data), len(comp),
        b"DCP\0", tag, 0x20, level, b"\0\0\0", 0, 0, 0, 0x00010100,
        b"DCA\0", 0x8,
    )
    assert len(hdr) == 0x4C
    out = hdr + comp
    if len(out) % 16:
        out += bytes(16 - len(out) % 16)
    return out


# ----------------------------------------------------------------------------
# BND4
# ----------------------------------------------------------------------------

@dataclass
class BndFile:
    index: int
    id: int
    name: str
    offset: int
    size: int


def _rev8(b: int) -> int:
    return int(f"{b:08b}"[::-1], 2)


@dataclass
class Bnd4:
    head: bytes             # everything before the first file's data (headers, names, hash table)
    files: list[BndFile]
    datas: list[bytes]
    file_header_size: int
    has_compression: bool
    long_offsets: bool


def read_bnd4(buf: bytes) -> Bnd4:
    if buf[:4] != b"BND4":
        raise ValueError("not a BND4")
    bit_big_endian = buf[0x0A] == 1
    file_count = struct.unpack_from("<i", buf, 0x0C)[0]
    file_header_size = struct.unpack_from("<q", buf, 0x20)[0]
    file_headers_end = struct.unpack_from("<q", buf, 0x28)[0]
    unicode = buf[0x30] != 0
    raw_fmt = buf[0x31]
    reverse = bit_big_endian or ((raw_fmt & 1) and not (raw_fmt & 0x80))
    fmt = _rev8(raw_fmt) if reverse else raw_fmt
    has_ids, has_names, long_off, compression = fmt & 0x02, fmt & 0x0C, fmt & 0x10, fmt & 0x20
    files, datas = [], []
    pos = 0x40
    for i in range(file_count):
        p = pos + 8  # flags + pad + (-1)
        csize = struct.unpack_from("<q", buf, p)[0]; p += 8
        if compression:
            p += 8
        if long_off:
            doff = struct.unpack_from("<q", buf, p)[0]; p += 8
        else:
            doff = struct.unpack_from("<I", buf, p)[0]; p += 4
        fid = i
        if has_ids:
            fid = struct.unpack_from("<i", buf, p)[0]; p += 4
        name = ""
        if has_names:
            noff = struct.unpack_from("<i", buf, p)[0]; p += 4
            if unicode:
                e = noff
                while buf[e:e + 2] != b"\0\0":
                    e += 2
                name = buf[noff:e].decode("utf-16-le")
            else:
                name = buf[noff:buf.index(b"\0", noff)].decode("shift_jis")
        files.append(BndFile(i, fid, name, doff, csize))
        datas.append(bytes(buf[doff:doff + csize]))
        pos += file_header_size
    return Bnd4(bytes(buf[:file_headers_end]), files, datas, file_header_size, bool(compression), bool(long_off))


def write_bnd4(b: Bnd4) -> bytes:
    out = bytearray(b.head)
    for f, data in zip(b.files, b.datas):
        if len(out) % 16:
            out += bytes(16 - len(out) % 16)
        doff = len(out)
        out += data
        p = 0x40 + f.index * b.file_header_size + 8
        struct.pack_into("<q", out, p, len(data)); p += 8
        if b.has_compression:
            struct.pack_into("<q", out, p, len(data)); p += 8
        if b.long_offsets:
            struct.pack_into("<q", out, p, doff)
        else:
            struct.pack_into("<I", out, p, doff)
    return bytes(out)


# ----------------------------------------------------------------------------
# PARAMDEF
# ----------------------------------------------------------------------------

_BASE_SIZE = {"s8": 1, "u8": 1, "dummy8": 1, "s16": 2, "u16": 2, "s32": 4, "u32": 4,
              "f32": 4, "b32": 4, "f64": 8, "fixstr": 1, "fixstrW": 2}
_STRUCT = {"s8": "b", "u8": "B", "dummy8": "B", "s16": "h", "u16": "H", "s32": "i",
           "u32": "I", "f32": "f", "b32": "I", "f64": "d"}
_DEF_RE = re.compile(r"^(\w+)\s+(\w+)(?:\[(\d+)\])?(?::(\d+))?(?:\s*=\s*(.+))?$")


@dataclass
class FieldDef:
    type: str
    name: str
    offset: int
    array: int | None = None
    bit_offset: int | None = None
    bit_size: int | None = None
    display_name: str = ""

    @property
    def size(self) -> int:
        return _BASE_SIZE[self.type] * (self.array or 1)


@dataclass
class ParamDef:
    param_type: str
    data_version: int
    fields: list[FieldDef] = field(default_factory=list)
    row_size: int = 0

    def __getitem__(self, name: str) -> FieldDef:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)

    def __contains__(self, name: str) -> bool:
        return any(f.name == name for f in self.fields)


def load_paramdef(path: str | Path) -> ParamDef:
    root = ET.parse(path).getroot()
    pd = ParamDef(root.findtext("ParamType"), int(root.findtext("DataVersion")))
    offset = 0
    bit_type, bit_pos, bit_unit_off = None, 0, 0
    for fe in root.iter("Field"):
        m = _DEF_RE.match(fe.get("Def").strip())
        if not m:
            raise ValueError(fe.get("Def"))
        typ, name, arr, bits, _default = m.groups()
        disp = fe.findtext("DisplayName") or ""
        if bits:
            bits = int(bits)
            unit = _BASE_SIZE[typ] * 8
            if bit_type is None or _BASE_SIZE[bit_type] != _BASE_SIZE[typ] or bit_pos + bits > unit:
                if bit_type is not None:
                    offset = bit_unit_off + _BASE_SIZE[bit_type]
                bit_type, bit_pos, bit_unit_off = typ, 0, offset
            pd.fields.append(FieldDef(typ, name, bit_unit_off, None, bit_pos, bits, disp))
            bit_pos += bits
            continue
        if bit_type is not None:
            offset = bit_unit_off + _BASE_SIZE[bit_type]
            bit_type = None
        f = FieldDef(typ, name, offset, int(arr) if arr else None, display_name=disp)
        pd.fields.append(f)
        offset += f.size
    if bit_type is not None:
        offset = bit_unit_off + _BASE_SIZE[bit_type]
    pd.row_size = offset
    return pd


# ----------------------------------------------------------------------------
# PARAM
# ----------------------------------------------------------------------------

@dataclass
class ParamRow:
    id: int
    data: bytearray


class Param:
    """A param file: header + rows. Rows are owned bytearrays; `to_bytes` re-serializes.

    Only the ER layout is implemented: format2D 0x85 (64-bit data offsets, param type
    stored as a string after the data), 0x18-byte row descriptors, empty row names.
    """

    def __init__(self, buf: bytes, paramdef: ParamDef):
        self.pd = paramdef
        self.header = bytes(buf[:0x40])
        f2d = buf[0x2D]
        if (f2d & 0x85) != 0x85:
            raise ValueError(f"unsupported PARAM format2D {f2d:#x}")
        row_count = struct.unpack_from("<H", buf, 0x0A)[0]
        pt_off = struct.unpack_from("<q", buf, 0x10)[0]
        self.param_type = bytes(buf[pt_off:pt_off + 64]).split(b"\0")[0].decode()
        if self.param_type != paramdef.param_type:
            raise ValueError(f"param type {self.param_type} != paramdef {paramdef.param_type}")
        descs = [struct.unpack_from("<iiqq", buf, 0x40 + i * 0x18) for i in range(row_count)]
        offs = sorted({d[2] for d in descs})
        actual = offs[1] - offs[0] if len(offs) > 1 else paramdef.row_size
        if actual != paramdef.row_size:
            raise ValueError(f"row size {actual} != paramdef row size {paramdef.row_size}; wrong paramdef version?")
        rs = paramdef.row_size
        self.rows: list[ParamRow] = [ParamRow(d[0], bytearray(buf[d[2]:d[2] + rs])) for d in descs]
        self.by_id: dict[int, ParamRow] = {r.id: r for r in self.rows}
        self.dirty = False      # set by set()/add_row(); untouched params are written back verbatim

    @property
    def row_count(self) -> int:
        return len(self.rows)

    # --- field access -------------------------------------------------------
    def get(self, row: ParamRow, name: str):
        f = self.pd[name]
        off = f.offset
        if f.bit_size is not None:
            unit = struct.unpack_from("<" + _STRUCT[f.type].upper(), row.data, off)[0]
            return (unit >> f.bit_offset) & ((1 << f.bit_size) - 1)
        if f.type in ("fixstr", "fixstrW", "dummy8"):
            return bytes(row.data[off:off + f.size])
        return struct.unpack_from("<" + _STRUCT[f.type], row.data, off)[0]

    def set(self, row: ParamRow, name: str, value) -> None:
        f = self.pd[name]
        off = f.offset
        self.dirty = True
        if f.bit_size is not None:
            code = "<" + _STRUCT[f.type].upper()
            unit = struct.unpack_from(code, row.data, off)[0]
            mask = ((1 << f.bit_size) - 1) << f.bit_offset
            unit = (unit & ~mask) | ((int(value) << f.bit_offset) & mask)
            struct.pack_into(code, row.data, off, unit)
            return
        if f.type in ("fixstr", "fixstrW", "dummy8"):
            row.data[off:off + f.size] = value
            return
        struct.pack_into("<" + _STRUCT[f.type], row.data, off, value)

    def row_dict(self, row: ParamRow) -> dict:
        return {f.name: self.get(row, f.name) for f in self.pd.fields if f.type != "dummy8"}

    # --- rows ---------------------------------------------------------------
    def add_row(self, new_id: int, src: ParamRow) -> ParamRow:
        """Insert a copy of `src` with id `new_id`, keeping rows sorted by id."""
        if new_id in self.by_id:
            raise ValueError(f"row {new_id} already exists in {self.param_type}")
        row = ParamRow(new_id, bytearray(src.data))
        self.dirty = True
        lo, hi = 0, len(self.rows)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.rows[mid].id < new_id:
                lo = mid + 1
            else:
                hi = mid
        self.rows.insert(lo, row)
        self.by_id[new_id] = row
        return row

    def to_bytes(self) -> bytes:
        n = len(self.rows)
        if n > 0xFFFF:
            raise ValueError("too many rows for a 16-bit row count")
        rs = self.pd.row_size
        data_start = 0x40 + 0x18 * n
        strings_off = data_start + rs * n
        type_bytes = self.param_type.encode() + b"\0"
        name_off = strings_off + len(type_bytes)
        hdr = bytearray(self.header)
        struct.pack_into("<I", hdr, 0x00, strings_off)
        struct.pack_into("<H", hdr, 0x0A, n)
        struct.pack_into("<q", hdr, 0x10, strings_off)
        struct.pack_into("<q", hdr, 0x30, data_start)
        out = bytearray(hdr)
        for i, r in enumerate(self.rows):
            out += struct.pack("<iiqq", r.id, 0, data_start + rs * i, name_off)
        for r in self.rows:
            out += r.data
        out += type_bytes
        out += bytes(4)  # one empty UTF-16 row name shared by every row
        return bytes(out)


# ----------------------------------------------------------------------------
# Regulation container
# ----------------------------------------------------------------------------

class Regulation:
    def __init__(self, path: str | Path):
        raw = Path(path).read_bytes()
        self.iv = raw[:16]
        dcx = read_dcx(decrypt_regulation(raw))
        self.level = dcx.level
        self.bnd = read_bnd4(dcx.data)
        self._params: dict[str, Param] = {}

    @property
    def files(self) -> list[BndFile]:
        return self.bnd.files

    def find(self, param_name: str) -> BndFile:
        for f in self.bnd.files:
            if f.name.endswith("\\" + param_name + ".param"):
                return f
        raise KeyError(param_name)

    def raw(self, param_name: str) -> bytes:
        return self.bnd.datas[self.find(param_name).index]

    def param(self, param_name: str, paramdef: ParamDef) -> Param:
        if param_name not in self._params:
            self._params[param_name] = Param(self.raw(param_name), paramdef)
        return self._params[param_name]

    def bnd_bytes(self) -> bytes:
        datas = list(self.bnd.datas)
        for name, p in self._params.items():
            if p.dirty:
                datas[self.find(name).index] = p.to_bytes()
        return write_bnd4(Bnd4(self.bnd.head, self.bnd.files, datas, self.bnd.file_header_size,
                               self.bnd.has_compression, self.bnd.long_offsets))

    def save(self, path: str | Path, max_size: int = REGULATION_MAX_SIZE, window_log: int = 16,
             codec: str = CODEC_ZSTD) -> int:
        """Write the regulation, compressing harder until it fits the game's size limit.
        codec: "zstd" (64 KB window, 15 -> 19 -> 22 level escalation), "kraken" / "leviathan"
        (Oodle through the game's own DLL, always Optimal5).  window_log: zstd window (16 is the
        only value the game accepts; 22 crashed it).  Returns the file size; raises ValueError if
        the result is still too large."""
        bnd = self.bnd_bytes()
        out = None
        levels = sorted({self.level, 19, 22}) if codec == CODEC_ZSTD else [9]
        for level in levels:
            if codec == CODEC_ZSTD and level < self.level:
                continue
            out = encrypt_regulation(write_dcx(Dcx(level, bnd, codec), window_log), self.iv)
            if len(out) <= max_size:
                break
        if len(out) > max_size:
            raise ValueError(f"regulation.bin would be {len(out)} bytes, over the game's limit of "
                             f"{max_size} (0x{max_size:X}); the game would report corrupted save data. "
                             "Randomize less (e.g. fewer --stat-groups, no --somber-infusable)"
                             + (" or use --compression kraken." if codec == CODEC_ZSTD else "."))
        Path(path).write_bytes(out)
        return len(out)


def load_names(path: str | Path) -> dict[int, str]:
    names = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rid, _, nm = line.partition(" ")
        names[int(rid)] = nm.strip()
    return names
