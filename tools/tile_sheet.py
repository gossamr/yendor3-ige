"""Draw the map's whole tile set as one sheet.

`PICTURES.VGA` holds 269,079 tiles; the map uses a block of 145 of them at
268503..268647, isolated between runs of blank tiles. 63 are fully opaque --
the terrain a cell's first word picks, and 82 carry transparent pixels, which
is what an object sprite needs so the terrain shows through around it.

Transparency is drawn as a checkerboard so a sprite's shape reads. Each tile is
labeled with its number in the block; add BLOCK_LO for its number in the bank.

    PYTHONPATH=tools python tools/tile_sheet.py [--out tmp/map_tiles.png]
"""

from __future__ import annotations

from pathlib import Path

import pngutil
import sections as S
import tiles

ROOT = Path(__file__).resolve().parent.parent

BLOCK_LO, BLOCK_HI = 268503, 268647     # the run the map's artwork sits in

SCALE = 8                # an 8x8 tile drawn 64x64
LABEL = 7                # rows under each tile for its number
PAD = 5
GAP = 18               # between the terrain grid and the sprite grid
COLS = 16

INK = (210, 210, 210)
BACK = (24, 24, 26)
RULE = (60, 60, 66)
CHECK = ((58, 44, 58), (44, 34, 46))    # transparent pixels

# 3x5 digits, one string a row, so a tile can say which one it is.
DIGITS = {
    "0": ("111", "101", "101", "101", "111"), "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"), "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"), "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"), "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"), "9": ("111", "101", "111", "001", "111"),
}


class Canvas:
    def __init__(self, w: int, h: int, fill: tuple[int, int, int]):
        self.w, self.h = w, h
        self.buf = bytearray(bytes(fill) * (w * h))

    def px(self, x: int, y: int, rgb) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(rgb)

    def rect(self, x: int, y: int, w: int, h: int, rgb) -> None:
        for dy in range(h):
            for dx in range(w):
                self.px(x + dx, y + dy, rgb)

    def text(self, x: int, y: int, s: str, rgb) -> None:
        for ch in s:
            rows = DIGITS.get(ch)
            if rows:
                for dy, row in enumerate(rows):
                    for dx, on in enumerate(row):
                        if on == "1":
                            self.px(x + dx, y + dy, rgb)
            x += 4


def sheet(pics: bytes, pal: list[bytes], lo: int = BLOCK_LO, hi: int = BLOCK_HI):
    """Two grids: tiles that can be terrain, then tiles that can be sprites.
    Every tile is labeled with its number in the run, so a tile here and a tile
    in the bank can be matched up."""
    block = list(range(lo, hi + 1))
    terrain = [t for t in block if 0xFF not in tiles.tile(pics, t)]
    objects = [t for t in block if 0xFF in tiles.tile(pics, t)]

    cell_w = 8 * SCALE
    cell_h = 8 * SCALE + LABEL + 2
    rows = sum((len(g) + COLS - 1) // COLS for g in (terrain, objects))
    w = PAD + COLS * (cell_w + PAD)
    h = PAD + rows * (cell_h + PAD) + GAP
    c = Canvas(w, h, BACK)

    y = PAD
    for group in (terrain, objects):
        for k, t in enumerate(group):
            cx = PAD + (k % COLS) * (cell_w + PAD)
            cy = y + (k // COLS) * (cell_h + PAD)
            raw = tiles.tile(pics, t)
            for py8 in range(8):
                for px8 in range(8):
                    v = raw[py8 * 8 + px8]
                    for dy in range(SCALE):
                        for dx in range(SCALE):
                            px, py = cx + px8 * SCALE + dx, cy + py8 * SCALE + dy
                            c.px(px, py, pal[v] if v != 0xFF
                                 else CHECK[((px // 4) + (py // 4)) % 2])
            c.text(cx, cy + 8 * SCALE + 2, str(t - lo), INK)
        y += ((len(group) + COLS - 1) // COLS) * (cell_h + PAD)
        if group is terrain:
            c.rect(PAD, y + GAP // 2, w - 2 * PAD, 1, RULE)
            y += GAP
    return w, h, bytes(c.buf)


if __name__ == "__main__":
    import sys

    out = "tmp/map_tiles.png"
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    d = S.load("game")
    pics = (ROOT / "game" / "PICTURES.VGA").read_bytes()
    w, h, rgb = sheet(pics, tiles.palette(d))
    pngutil.write(str(ROOT / out), w, h, rgb)
    opaque = sum(1 for t in range(BLOCK_LO, BLOCK_HI + 1)
                 if 0xFF not in tiles.tile(pics, t))
    print(f"wrote {out}  {w}x{h}  "
          f"{BLOCK_HI - BLOCK_LO + 1} tiles in the run: {opaque} opaque, "
          f"{BLOCK_HI - BLOCK_LO + 1 - opaque} with transparency. "
          f"Not all are map art.")
