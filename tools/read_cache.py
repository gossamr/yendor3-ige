#!/usr/bin/env python3
"""Find the game's page tile cache in a memory dump.

While a map page is open the game holds the tiles it needs as six-byte records:

    uint16  index into the tile run at PICTURES.VGA 268503, or 0xFFFF if unused
    uint16  the segment of the buffer the tile was read into
    uint16  the offset in that buffer, stepping 0x40, one tile a slot

They are in the order the tiles were first needed, so laying known ids across a
page and reading this back says which tile each id drew, with no rendering and
no picture of the game's screen involved.

    python tools/read_cache.py tmp/memory.bin
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

RECORD = 6
STEP = 0x40          # one tile a slot
EMPTY = 0xFFFF
TILES = 145          # the run the map's artwork sits in


def find(mem: bytes, want: int = 8) -> list[tuple[int, list[int]]]:
    """Every run of records that looks like the cache, longest first."""
    out = []
    at = 0
    while at < len(mem) - RECORD * want:
        first, seg, off = struct.unpack_from("<HHH", mem, at)
        if (first < TILES or first == EMPTY) and seg and off:
            entries, k = [], 0
            while at + (k + 1) * RECORD <= len(mem):
                a, s, o = struct.unpack_from("<HHH", mem, at + k * RECORD)
                if s != seg or o != off + k * STEP:
                    break
                if a != EMPTY and a >= TILES:
                    break
                entries.append(a)
                k += 1
            if k >= want:
                out.append((at, entries))
                at += k * RECORD
                continue
        at += 2
    out.sort(key=lambda r: -len(r[1]))
    return out


def tiles_in_order(mem: bytes) -> list[int]:
    """The cache's tiles, first use first, with the empty slots dropped."""
    runs = find(mem)
    if not runs:
        return []
    _, entries = runs[0]
    return [e for e in entries if e != EMPTY]


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "tmp/memory.bin"
    mem = Path(path).read_bytes()
    runs = find(mem)
    print(f"{len(runs)} candidate caches")
    for at, entries in runs[:3]:
        used = [e for e in entries if e != EMPTY]
        print(f"  heap 0x{at:X}: {len(entries)} slots, {len(used)} used")
        print(f"     {used}")
