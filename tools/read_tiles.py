#!/usr/bin/env python3
"""Read the id -> tile table out of a probe frame.

`tmp/probe_tiles.js` writes 0, 1, 2, ... into a map page's cells, sets every
cell's drawn bit, and photographs what the game makes of it. Each drawn cell
then shows the artwork the game itself chose for that id, so matching the cell
against the tile bank gives the lookup without any reference to the clue book.

    bun tmp/probe_tiles.js --first=0 --count=340 --out=tmp/tiles
    bun tmp/probe_tiles.js --first=0 --count=340 --object --out=tmp/tiles
    PYTHONPATH=tools python tools/read_tiles.py

Ids the picture file has nothing for draw the page's empty tile; they are
reported rather than recorded, since the game draws nothing of its own for
them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pngutil
import sections as S
import solve_maps as SM
import tiles

ROOT = Path(__file__).resolve().parent.parent
DRAWN_COLS = 34          # the sweep is laid across the columns the game draws
TERRAIN_UNDER = 29       # what the probe leaves under an object sweep: id 0


def read(frame: str, first: int, count: int, pics: bytes, pal: list[bytes],
         over: int | None = None) -> dict[int, int]:
    """id -> tile, read off a probe frame.

    `over` is the block index of the terrain the sweep sits on. Pass it when
    the ids went into the object word: a sprite is composited rather than
    drawn, so the cell shows the sprite's opaque pixels and that terrain
    everywhere else, and matching the cell against the bank directly would only
    ever find the fully opaque sprites.
    """
    w, _, rgb = pngutil.read(frame)
    # The frame catches the fire ramp at whatever phase it had reached, so a
    # tile drawn with indices 220-223 matches only under that phase.
    phases = [tiles.cycled(pal, n) for n in range(4)]
    index = {}
    for p in phases:
        for k, v in tiles.index(pics, p, tiles.BLOCK, tiles.BLOCK + 145).items():
            index.setdefault(k, v)
    bases = [tiles.render(pics, p, tiles.BLOCK + over) for p in phases] \
        if over is not None else None
    raws = [(n, tiles.tile(pics, tiles.BLOCK + n)) for n in range(145)]

    def composited(block):
        for p, base in zip(phases, bases):
            for n, raw in raws:
                for i in range(64):
                    v = raw[i]
                    want = block[i * 3:i * 3 + 3]
                    if ((want != base[i * 3:i * 3 + 3]) if v == 0xFF
                            else (p[v] != want)):
                        break
                else:
                    return n
        return None

    out, n = {}, 0
    for row in range(SM.ROWS):
        for col in range(DRAWN_COLS):
            if n >= count:
                return out
            block = b"".join(
                rgb[((SM.Y0 + row * 8 + y) * w + SM.X0 + col * 8) * 3:
                    ((SM.Y0 + row * 8 + y) * w + SM.X0 + col * 8) * 3 + 24]
                for y in range(8))
            if bases is None:
                hit = index.get(block)
                if hit:
                    out[first + n] = hit[0] - tiles.BLOCK
            elif block not in bases:
                got = composited(block)
                if got is not None:
                    out[first + n] = got
            n += 1
    return out


if __name__ == "__main__":
    d = S.load("game")
    pics = (ROOT / "game" / "PICTURES.VGA").read_bytes()
    pal = tiles.palette(d)
    got = {}
    for kind, suffix in (("terrain", ""), ("object", "-object")):
        frame = ROOT / "tmp" / "tiles" / f"ids-0-340{suffix}.png"
        if not frame.exists():
            print(f"no {frame}; run tmp/probe_tiles.js{' --object' if suffix else ''}")
            continue
        table = read(str(frame), 0, 341, pics, pal,
                     over=TERRAIN_UNDER if kind == "object" else None)
        got[kind] = table
        print(f"{kind}: {len(table)} ids read from the game")
    if got:
        print(json.dumps({k: {str(i): t for i, t in sorted(v.items())}
                          for k, v in got.items()})[:200] + " ...")
