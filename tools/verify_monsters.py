#!/usr/bin/env python3
"""Check the decoded monster art against the game's own clue-book screens.

`tools/capture_monsters.js` photographs the F2 MONSTER STATISTICS page for
every creature the game lists, in the order it lists them. Each page draws the
creature at a fixed place, so rendering the record's own picture and comparing
it pixel for pixel says whether the picture, the palette and the recolour list
are all right.

The comparison takes the best of the creature's ten pictures because the page
animates: a capture catches whichever step the loop had reached.

    bun tools/capture_monsters.js --out=tmp/monsters --count=72
    PYTHONPATH=tools python tools/verify_monsters.py [tmp/monsters]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import extract
import pictures as P
import pngutil
import sections as S
import tiles

ROOT = Path(__file__).resolve().parent.parent

# Where each run's pictures are drawn on the page, found by searching for the
# offset that matches best and identical for every creature in that run.
ANCHOR = {P.TALL: (8, 7), P.WIDE: (6, 33)}


def compare(shot: bytes, sw: int, sh: int, raw: bytes, width: int,
            index: dict, at: tuple[int, int]) -> tuple[int, int]:
    """(matching pixels, opaque pixels) for one picture at one place."""
    ox, oy = at
    hit = total = 0
    for y in range(len(raw) // width):
        sy = oy + y
        if not 0 <= sy < sh:
            continue
        row = raw[y * width:(y + 1) * width]
        for x, v in enumerate(row):
            if v == P.TRANSPARENT:
                continue
            sx = ox + x
            if not 0 <= sx < sw:
                continue
            total += 1
            hit += index[sy * sw + sx] == v
    return hit, total


def main(shot_dir: str = "tmp/monsters") -> int:
    d = S.load()
    pics = (ROOT / "game" / "PICTURES.VGA").read_bytes()
    runs = P.read_runs(d.exe, len(pics))
    palette = tiles.palette(d, extract.MONSTER_PALETTE)
    slot = {}
    for i, c in enumerate(palette):
        slot.setdefault(bytes(c), i)

    enemies = [e for e in extract.extract_enemies(d) if e["listed"]]
    exact = 0
    for n, e in enumerate(sorted(enemies, key=lambda e: e["name"])):
        path = Path(shot_dir) / f"m{n:02d}.png"
        if not path.exists():
            print(f"{e['name']:20s} no capture")
            continue
        sw, sh, rgb = pngutil.read(str(path))
        index = [slot.get(rgb[i * 3:i * 3 + 3], -1) for i in range(sw * sh)]
        swaps = {s["from"]: s["to"] for s in e["recolour"]}
        best = (0.0, None)
        for f in range(P.FRAMES):
            run, raw = P.creature(pics, runs, e["sprite"], e["masks"]["w96"],
                                  e["masks"]["w98"], swaps, f)
            hit, total = compare(rgb, sw, sh, raw, run.width, index,
                                 ANCHOR[run.index])
            if total and hit / total > best[0]:
                best = (hit / total, f)
        exact += best[0] == 1.0
        print(f"{e['name']:20s} run {run.index} picture {e['sprite']:3d} "
              f"frame {best[1]}  {best[0]:.3f}")
    print(f"\n{exact}/{len(enemies)} reproduce the game's own screen exactly")
    return 0 if exact else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
