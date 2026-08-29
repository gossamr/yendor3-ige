#!/usr/bin/env python3
"""Draw the whole world as one image.

The game's maps are not 140 separate pictures: they are one grid. A cell's
place is a single x and y across the lot, `x = level * 40 + cell` and
`y = area * 24 + band`, which is how the party's position is stored and how
the seen-grid is indexed. So the 140 slots can be drawn where they actually
sit: 20 levels across by 7 areas down, 800 by 168 cells, each cell the 8x8 the
game draws it with.

Most slots are empty, and they come out black. What is left is the shape of the
world: which maps abut which, and how much of the grid the game never uses.

    PYTHONPATH=tools python tools/world_map.py [--out data/world.png]
"""

from __future__ import annotations

import struct
from pathlib import Path

import pngutil
import sections as S
import solve_maps as SM
import tiles

ROOT = Path(__file__).resolve().parent.parent

AREAS, LEVELS = 7, 20
BANDS, CELLS = SM.ROWS, 40
TILE = tiles.TILE


def draw(d: S.Directory, pics: bytes) -> tuple[int, int, bytes]:
    """The world, as one RGB image."""
    pal = tiles.palette(d)
    world, exe = d.world, d.exe
    w = LEVELS * CELLS * TILE
    h = AREAS * BANDS * TILE
    out = bytearray(w * h * 3)
    # The same three words draw the same cell everywhere, and a world of 134,400
    # cells holds only a few hundred distinct ones.
    seen: dict[tuple[int, int, int], bytes] = {}
    for area in range(AREAS):
        base = area * SM.AREA_STRIDE
        for band in range(BANDS):
            row = area * BANDS + band
            for level in range(LEVELS):
                for cell in range(CELLS):
                    at = (base + band * SM.BAND_STRIDE
                          + level * SM.LEVEL_STRIDE + cell * SM.CELL)
                    terrain, obj = struct.unpack_from("<HH", world, at)
                    drawn = tiles.drawn(world, area, level, band, cell)
                    if not drawn and not obj:
                        continue          # never used: leave it black
                    key = (terrain, obj, drawn)
                    block = seen.get(key)
                    if block is None:
                        block = tiles.cell(pics, pal, exe, terrain, obj, drawn)
                        seen[key] = block
                    x0 = (level * CELLS + cell) * TILE
                    y0 = row * TILE
                    for y in range(TILE):
                        i = ((y0 + y) * w + x0) * 3
                        out[i:i + TILE * 3] = block[y * TILE * 3:(y + 1) * TILE * 3]
    return w, h, bytes(out)


def main(out: str = "data/world.png") -> None:
    d = S.load()
    pics = (ROOT / "game" / "PICTURES.VGA").read_bytes()
    w, h, rgb = draw(d, pics)
    path = ROOT / out
    path.parent.mkdir(parents=True, exist_ok=True)
    pngutil.write(str(path), w, h, rgb)
    print(f"wrote {path} ({w}x{h}, {path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    main(args[args.index("--out") + 1] if "--out" in args else "data/world.png")
