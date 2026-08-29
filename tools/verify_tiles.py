#!/usr/bin/env python3
"""Check the id -> tile table against the game's own cache.

While a map page is open the game holds the tiles it needs, in the order it
first needed them (see `tools/read_cache.py`). Lay a known set of ids across a
page, take a memory dump, and that cache says which tiles the game decided the
page needed, with no rendering, no palette and no picture of the screen in it
anywhere.

That checks the rule `tools/tiles.py` reads out of `REGISTER.EXE` against what
the game itself loaded. The cache is keyed by tile, so ids sharing one
introduce nothing after the first and the mapping cannot be read back out of a
single dump; what it settles exactly is which tiles a page needs and in what
order.

    bun tools/dump_memory.js --ids=0..340           --out=tmp/memory.bin
    bun tools/dump_memory.js --ids=0..340 --reverse --out=tmp/memory-desc.bin
    python tools/verify_tiles.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import read_cache
import tiles

ROOT = Path(__file__).resolve().parent.parent
COLS, ROWS, COL0 = 40, 24, 3      # a row is 40 cells; the book prints 34
CELLS = (COLS - COL0 - 3) * ROWS  # what the sweep can carry


def page(ids: list[int]) -> list[int]:
    """Every cell of the page, in the order the game draws them.

    The three margin cells at either end of a row are not part of the sweep and
    carry id 0. They are drawn all the same once their bit is set, and they are
    drawn *first*, so the first tile the game caches is whatever id 0 draws,
    not whatever the sweep starts with. Leaving them out shifts every
    attribution by one.
    """
    out, n = [], 0
    for _ in range(ROWS):
        for col in range(COLS):
            inside = COL0 <= col < COLS - COL0
            out.append(ids[n] if inside and n < len(ids) else 0)
            if inside and n < len(ids):
                n += 1
    return out


def expected(ids: list[int], table: dict[int, int]) -> list[int]:
    """The tiles a page of these ids needs, first use first."""
    out, seen = [], set()
    for i in page(ids):
        t = table.get(i)
        if t is None or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


# The map screen caches artwork of its own after the page's terrain (tile 20
# turns up on every page, including ones where no id draws it) so the cache
# ends with entries no id accounts for.
SCREEN = {20}


def check(dump: str, ids: list[int], table: dict[int, int]) -> tuple[bool, list, list]:
    got = [t for t in read_cache.tiles_in_order(Path(dump).read_bytes())
           if t not in SCREEN]
    want = [t for t in expected(ids, table) if t not in SCREEN]
    return got == want, want, got


if __name__ == "__main__":
    exe = (ROOT / "game" / "REGISTER.EXE").read_bytes()
    table = {i: tiles.terrain(exe, i) for i in range(341)}
    ids = list(range(341))
    ok = True
    for dump, order, label in ((ROOT / "tmp" / "memory.bin", ids, "ascending"),
                              (ROOT / "tmp" / "memory-desc.bin", ids[::-1], "descending")):
        if not dump.exists():
            print(f"{label}: no {dump}")
            continue
        same, want, got = check(str(dump), order, table)
        ok &= same
        print(f"{label}: {len(got)} tiles cached, {len(want)} predicted: "
              f"{'identical, in order' if same else 'DIFFER'}")
        if not same:
            for k, (a, b) in enumerate(zip(want, got)):
                if a != b:
                    print(f"   first difference at {k}: predicted {a}, cached {b}")
                    break
    sys.exit(0 if ok else 1)
