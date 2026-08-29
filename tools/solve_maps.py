"""Locate each clue-book map page in WORLD.DAT and decode its tile grid.

Established by tracing the game's own reads and then changing the data and
watching the screen (see docs/map.md):

    tile(band, col) = uint16 at  base + band*3200 + level*160 + (3 + col)*4

A page is 34 columns by 24 bands of 8x8 tiles, drawn at (24, 8). The row is 40
cells wide, of which columns 3..36 are shown; a 3,200-byte chunk holds that row
for 20 levels, and an area's 76,800 bytes hold 24 of those chunks. So an area
is up to 20 levels of a 40x24 map, and the only per-page unknowns are which
area block it lives in and which level it is.

Those two are solved here rather than traced, because tracing needs a cold boot
per map: for each candidate (base, level) the decoded ids are scored against the
captured page, and the right pair explains the picture's brightness almost
completely while everything else is noise.
"""

from __future__ import annotations

import collections
import glob
import json
import os
import statistics
import struct
from pathlib import Path

import pngutil

# Content read off the game's screens, not decoded from its files. Never
# shipped.
OBSERVED = Path(__file__).resolve().parent.parent / "observed"

ROOT = Path(__file__).resolve().parent.parent
COLS, ROWS = 34, 24
COL0 = 3                  # first visible column of the 40-wide row
CELL = 4                  # bytes per cell
LEVEL_STRIDE = 160        # 40 cells
BAND_STRIDE = 3200        # one row for all 20 levels
AREA_STRIDE = 76800       # 24 bands
LEVELS = 20
TILE, X0, Y0 = 8, 24, 8


def page_brightness(shot: str) -> list[list[float]]:
    """Mean brightness of each 8x8 tile of a captured page."""
    w, h, rgb = pngutil.read(shot)
    out = []
    for r in range(ROWS):
        row = []
        for c in range(COLS):
            s = 0
            for y in range(TILE):
                base = (Y0 + r * TILE + y) * w + X0 + c * TILE
                for x in range(TILE):
                    i = (base + x) * 3
                    s += rgb[i] + rgb[i + 1] + rgb[i + 2]
            row.append(s / (TILE * TILE * 3))
        out.append(row)
    return out


def read_grid(world: bytes, base: int, level: int) -> list[list[int]]:
    """The terrain layer: the second uint16 of each four-byte cell."""
    off = base + level * LEVEL_STRIDE + COL0 * CELL
    return [[struct.unpack_from("<H", world, off + band * BAND_STRIDE + c * CELL)[0]
             for c in range(COLS)] for band in range(ROWS)]


def read_objects(world: bytes, base: int, level: int) -> list[list[int]]:
    """The object layer: the *second* uint16 of each cell, zero where bare.

    Trees, buildings and people sit over the terrain rather than replacing it,
    and they are what the terrain layer alone cannot account for: the count of
    non-zero cells tracks the shortfall exactly, from 29 on Acoknight's Cave
    (97.9% from terrain alone) to 298 on Dwarven Homeland Map 2 (36.8%).

    An object covering more than one cell repeats its id in each of them, so
    there is no size to record and no cell without a record of its own: every
    cell it occupies draws its tile independently.
    """
    off = base + level * LEVEL_STRIDE + COL0 * CELL + 2
    return [[struct.unpack_from("<H", world, off + band * BAND_STRIDE + c * CELL)[0]
             for c in range(COLS)] for band in range(ROWS)]


def block_ids(shot: str) -> list[list[int]]:
    """Each tile of a captured page, as a small integer per distinct 8x8 block."""
    w, h, rgb = pngutil.read(shot)
    seen, out = {}, []
    for r in range(ROWS):
        row = []
        for c in range(COLS):
            block = b"".join(
                rgb[((Y0 + r * TILE + y) * w + X0 + c * TILE) * 3:
                    ((Y0 + r * TILE + y) * w + X0 + c * TILE) * 3 + TILE * 3]
                for y in range(TILE))
            row.append(seen.setdefault(block, len(seen)))
        out.append(row)
    return out


# A tileset is small. Scoring purity alone rewards the opposite: a region of
# unrelated bytes gives nearly one id per cell, which is trivially "pure", so
# a candidate with more ids than any real tileset is rejected outright.
MAX_TILESET = 64

# The map slots fill the unindexed head of WORLD.DAT exactly: the first
# section-directory entry is at 0x83400, and 0x83400 / 76800 = 7, so there are
# seven area blocks of twenty levels each, 140 slots, of which the clue book
# prints 37.
AREAS = 7


def marker_mask(shot: str, cut: float = 1.45) -> list[list[bool]]:
    """Which tiles carry a marker rather than terrain.

    The game draws its legend markers on top of the tiles, so those cells never
    match their id's block however right the grid is, and counting them makes
    a correct page score like an incorrect one, which is what stalled the
    search. Markers are much brighter than terrain (a feature tile measured
    131.9 against 51-72 for wall and floor), so a brightness cut finds them.
    """
    b = page_brightness(shot)
    flat = sorted(v for row in b for v in row)
    median = flat[len(flat) // 2]
    return [[v > median * cut for v in row] for row in b]


def purity(grid, drawn, rows, skip=None) -> float:
    """How well one block per id explains the page.

    The right grid draws every occurrence of an id with the same 8x8 block, so
    the modal block accounts for nearly all of them. A wrong grid scatters.
    """
    seen = collections.defaultdict(collections.Counter)
    n = 0
    for r in rows:
        for c in range(COLS):
            if skip is not None and skip[r][c]:
                continue
            seen[grid[r][c]][drawn[r][c]] += 1
            n += 1
    if not n or not (2 <= len(seen) <= MAX_TILESET):
        return 0.0
    return sum(cnt.most_common(1)[0][1] for cnt in seen.values()) / n


def solve(shot: str, world: bytes) -> dict:
    drawn = block_ids(shot)
    skip = marker_mask(shot)
    coarse = range(0, ROWS, 3)
    ranked = []
    for k in range(AREAS):
        base = k * AREA_STRIDE
        for level in range(LEVELS):
            g = read_grid(world, base, level)
            ranked.append((purity(g, drawn, coarse, skip), base, level))
    ranked.sort(reverse=True)
    scored = []
    for _, base, level in ranked[:60]:
        g = read_grid(world, base, level)
        scored.append((purity(g, drawn, range(ROWS), skip), base, level))
    scored.sort(reverse=True)
    return scored


def main(shot_dir="tmp/maps4", game="game/WORLD.DAT") -> list[dict]:
    """Assign each page a slot, allowing no two pages to claim the same one."""
    world = Path(game).read_bytes()
    titles = [p["title"] for p in
              json.loads((OBSERVED / "observed_maps.json").read_text())]
    candidates = []
    for shot in sorted(glob.glob(f"{shot_dir}/m[0-9][0-9].png")):
        idx = int(os.path.basename(shot)[1:3])
        candidates.append({
            "shot": os.path.basename(shot),
            "title": titles[idx] if idx < len(titles) else "",
            "options": solve(shot, world),
        })
    # Best-first assignment. Two pages cannot be the same slot, and letting the
    # confident ones claim first stops a weak match from stealing a slot.
    taken, out = set(), {}
    flat = sorted(((o[0], c["shot"], o[1], o[2])
                   for c in candidates for o in c["options"]), reverse=True)
    for score, shot, base, level in flat:
        if shot in out or (base, level) in taken:
            continue
        out[shot] = {"shot": shot, "base": base, "level": level, "score": score}
        taken.add((base, level))
    rows = []
    for c in candidates:
        got = out.get(c["shot"], {"base": None, "level": None, "score": 0.0})
        got = {**got, "title": c["title"], "shot": c["shot"]}
        rows.append(got)
        print(f"  {c['title']:26} area {got['base'] // AREA_STRIDE if got['base'] is not None else '-'}"
              f" level {str(got['level']):>2}  {got['score']:6.1%}")
    return rows


if __name__ == "__main__":
    import registry     # registry imports this module; only main writes the index

    rows = main()
    registry.INDEX.write_text(
        json.dumps(rows, indent=1) + "\n")
    good = sum(1 for r in rows if r["score"] > 0.7)
    print(f"\n{good}/{len(rows)} pages located with the grid explaining >70%")
