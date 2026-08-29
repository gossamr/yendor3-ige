"""Solve the 58-byte item record against the game's own F5 screens.

The solve has landed: `tools/items.py` decodes every row an F5 page prints, and
the screens are now the check rather than the source. This module stays because
it is the instrument: point it at a field that is still open and it reports
every encoding at every offset that fits the observations exactly.

Same method as the enemy and spell records: read every item's clue-book page,
then look for the field in the record whose values match exactly across all of
them. An exact match over a hundred-odd items is not something a wrong offset
can fake.

Record shape, established by inspection: 19 bytes of fields followed by three
13-byte name fields (12 characters and a NUL), 58 bytes in all, 631 records.
Names run across the three fields, so "BROKEN" + "BO STICK" is one item.
"""

from __future__ import annotations

import glob
import struct
from pathlib import Path

import items as I
import ocr
import read_items
import sections as S

ITEM_FIELD_BYTES = I.FIELD_BYTES


def records(game_dir: str = "game") -> list[tuple[str, bytes]]:
    d = S.load(game_dir)
    return [(I.name(rec), rec) for rec in d[S.ITEMS].records(d.world, I.RECORD)]


def bcd(rec: bytes, off: int, length: int) -> int | None:
    """Packed BCD, most significant byte first, as the reward fields use."""
    total = 0
    for b in rec[off:off + length]:
        hi, lo = b >> 4, b & 0xF
        if hi > 9 or lo > 9:
            return None
        total = total * 100 + hi * 10 + lo
    return total


def plain(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum())


def read_screens(shot_dir: str = "tmp/items", game_dir: str = "game") -> dict:
    """Every captured screen, keyed by the record name it belongs to."""
    recs = records(game_dir)
    names = [n for n, _ in recs if n]
    shots = [Path(p) for p in
             sorted(glob.glob(f"{shot_dir}/c[0-9]i[0-9][0-9][0-9].png"))]
    alpha = read_items.build_alphabet(shots, names)
    by_plain = {}
    for n in names:
        by_plain.setdefault(plain(n), n)
    out = {}
    for shot in shots:
        item = read_items.read_item(ocr.Frame(shot), alpha)
        name = by_plain.get(plain(item["name"] or ""))
        if name and name not in out:
            out[name] = item
    return out


def solve_number(rows, value_of, label=""):
    """Every encoding at every offset that matches the observation exactly."""
    hits = []
    for off in range(ITEM_FIELD_BYTES):
        if all(r[off] == value_of(o) for r, o in rows):
            hits.append(f"u8@{off}")
    for off in range(ITEM_FIELD_BYTES - 1):
        if all(struct.unpack_from("<H", r, off)[0] == value_of(o) for r, o in rows):
            hits.append(f"u16@{off}")
        if all(struct.unpack_from(">H", r, off)[0] == value_of(o) for r, o in rows):
            hits.append(f"be16@{off}")
        if all(bcd(r, off, 2) == value_of(o) for r, o in rows):
            hits.append(f"bcd2@{off}")
    for off in range(ITEM_FIELD_BYTES):
        if all(r[off] == value_of(o) * 10 for r, o in rows):
            hits.append(f"u8@{off} (tenths)")
    return hits
