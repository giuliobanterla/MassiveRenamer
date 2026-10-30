"""Lettura minima della data di scatto (EXIF) senza dipendenze esterne.

Supporta i JPEG (segmento APP1 "Exif") e i file basati su TIFF, come TIFF, DNG e la maggior parte
dei RAW (CR2, NEF, ARW…). Per gli altri formati restituisce None.
"""

from __future__ import annotations

import struct
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

TAG_DATETIME = 0x0132
TAG_EXIF_IFD = 0x8769
TAG_DATETIME_ORIGINAL = 0x9003
MAX_ENTRIES = 1000


def _parse_date(raw: bytes) -> datetime | None:
    text = raw.split(b"\0", 1)[0].decode("ascii", "replace").strip()
    try:
        return datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _read_tiff(f: BinaryIO, base: int) -> datetime | None:
    """Legge un blocco TIFF che inizia all'offset `base` del file."""
    f.seek(base)
    header = f.read(8)
    if len(header) < 8:
        return None
    if header[:2] == b"II":
        order = "<"
    elif header[:2] == b"MM":
        order = ">"
    else:
        return None
    if struct.unpack(order + "H", header[2:4])[0] != 42:
        return None

    def read_ifd(offset: int) -> dict[int, tuple[int, int, bytes]]:
        f.seek(base + offset)
        count_raw = f.read(2)
        if len(count_raw) < 2:
            return {}
        count = min(struct.unpack(order + "H", count_raw)[0], MAX_ENTRIES)
        entries = {}
        for _ in range(count):
            entry = f.read(12)
            if len(entry) < 12:
                break
            tag, typ, n = struct.unpack(order + "HHI", entry[:8])
            entries[tag] = (typ, n, entry[8:12])
        return entries

    def ascii_value(entry: tuple[int, int, bytes]) -> bytes:
        typ, n, value = entry
        if typ != 2:
            return b""
        if n <= 4:
            return value[:n]
        f.seek(base + struct.unpack(order + "I", value)[0])
        return f.read(min(n, 64))

    ifd0 = read_ifd(struct.unpack(order + "I", header[4:8])[0])
    if TAG_EXIF_IFD in ifd0:
        exif = read_ifd(struct.unpack(order + "I", ifd0[TAG_EXIF_IFD][2])[0])
        if TAG_DATETIME_ORIGINAL in exif:
            found = _parse_date(ascii_value(exif[TAG_DATETIME_ORIGINAL]))
            if found:
                return found
    if TAG_DATETIME in ifd0:
        return _parse_date(ascii_value(ifd0[TAG_DATETIME]))
    return None


def _read_jpeg(f: BinaryIO) -> datetime | None:
    f.seek(2)
    while True:
        marker = f.read(4)
        if len(marker) < 4 or marker[0] != 0xFF:
            return None
        kind, length = marker[1], struct.unpack(">H", marker[2:4])[0]
        if kind in (0xDA, 0xD9):  # inizio dei dati dell'immagine: niente più metadati
            return None
        start = f.tell()
        if kind == 0xE1 and f.read(6) == b"Exif\0\0":
            return _read_tiff(f, start + 6)
        f.seek(start + length - 2)


def date_taken(path: Path) -> datetime | None:
    """Data di scatto della foto, o None se il file non la contiene o non è leggibile."""
    try:
        with path.open("rb") as f:
            magic = f.read(4)
            if magic[:2] == b"\xff\xd8":
                return _read_jpeg(f)
            if magic in (b"II*\0", b"MM\0*"):
                return _read_tiff(f, 0)
    except (OSError, struct.error):
        pass
    return None
