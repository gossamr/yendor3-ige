"""Assign every clue-book page its slot in WORLD.DAT, by rendering it.

solve_maps locates a page by asking which (area, level) makes one 8x8 block
explain every occurrence of each tile id. That is enough for pages whose
tileset is distinctive and not enough for the rest: several pages share an area
and a tileset, and purity alone cannot tell them apart.

So refine by rendering. Once a few pages in an area are placed confidently,
their tiles give that area an atlas; a candidate slot for any other page can
then be drawn with it and compared to what the game drew, tile for tile. That
is the ground truth, and it is not circular as long as the atlas is built from
*other* pages.
"""

from __future__ import annotations

import collections
import json
import os
from pathlib import Path

import pngutil
import registry
import solve_maps as S

# Content read off the game's screens, not decoded from its files. Never
# shipped.
OBSERVED = Path(__file__).resolve().parent.parent / "observed"

TILE = S.TILE
CONFIDENT = 0.93


def page_blocks(shot: str):
    w, h, rgb = pngutil.read(shot)
    return [[b"".join(
        rgb[((S.Y0 + r * TILE + y) * w + S.X0 + c * TILE) * 3:
            ((S.Y0 + r * TILE + y) * w + S.X0 + c * TILE) * 3 + TILE * 3]
        for y in range(TILE)) for c in range(S.COLS)] for r in range(S.ROWS)]


def atlas_from(assign, grids, blocks, threshold=CONFIDENT):
    seen = collections.defaultdict(collections.Counter)
    for shot, a in assign.items():
        if a["base"] is None or a["score"] < threshold:
            continue
        area = a["base"] // S.AREA_STRIDE
        g = grids[(a["base"], a["level"])]
        for r in range(S.ROWS):
            for c in range(S.COLS):
                seen[(area, g[r][c])][blocks[shot][r][c]] += 1
    return {k: v.most_common(1)[0][0] for k, v in seen.items()}


def draw_score(grid, block_rows, atlas, area, skip=None):
    hit = seen = 0
    for r in range(S.ROWS):
        for c in range(S.COLS):
            if skip is not None and skip[r][c]:
                continue
            if atlas.get((area, grid[r][c])) == block_rows[r][c]:
                hit += 1
            seen += 1
    return hit / seen if seen else 0.0


def fit(shot_dir="tmp/maps4", game="game/WORLD.DAT", rounds=4):
    world = Path(game).read_bytes()
    here = Path(__file__).resolve().parent
    titles = [p["title"] for p in json.loads((OBSERVED / "observed_maps.json").read_text())]
    shots = sorted(os.path.basename(p) for p in Path(shot_dir).glob("m[0-9][0-9].png"))
    blocks = {s: page_blocks(f"{shot_dir}/{s}") for s in shots}
    grids = {(a * S.AREA_STRIDE, l): S.read_grid(world, a * S.AREA_STRIDE, l)
             for a in range(S.AREAS) for l in range(S.LEVELS)}
    ids = {s: [[hash(b) for b in row] for row in blocks[s]] for s in shots}
    # Markers are drawn over the terrain and never match their id's block, so
    # they are excluded: with them counted, a right slot and a wrong one score
    # alike and the search cannot tell them apart.
    skips = {s: S.marker_mask(f"{shot_dir}/{s}") for s in shots}

    assign = {}
    for s in shots:
        best = (0.0, None, None)
        for (base, level), g in grids.items():
            p = S.purity(g, ids[s], range(S.ROWS), skips[s])
            if p > best[0]:
                best = (p, base, level)
        assign[s] = {"score": best[0], "base": best[1], "level": best[2]}

    for _ in range(rounds):
        atlas = atlas_from(assign, grids, blocks)
        areas_known = {k[0] for k in atlas}
        scored = []
        for s in shots:
            for (base, level), g in grids.items():
                area = base // S.AREA_STRIDE
                if area not in areas_known:
                    continue
                scored.append((draw_score(g, blocks[s], atlas, area, skips[s]), s, base, level))
        scored.sort(reverse=True)
        taken, fresh = set(), {}
        for score, s, base, level in scored:
            if s in fresh or (base, level) in taken:
                continue
            fresh[s] = {"score": score, "base": base, "level": level}
            taken.add((base, level))
        for s in shots:
            if s in fresh and fresh[s]["score"] > assign[s]["score"]:
                assign[s] = fresh[s]

    rows = []
    for i, s in enumerate(shots):
        a = assign[s]
        rows.append({"shot": s, "title": titles[i] if i < len(titles) else "",
                     "base": a["base"], "level": a["level"],
                     "score": round(a["score"], 4)})
    return rows


if __name__ == "__main__":
    rows = fit()
    registry.INDEX.write_text(
        json.dumps(rows, indent=1) + "\n")
    for r in rows:
        area = r["base"] // S.AREA_STRIDE if r["base"] is not None else "-"
        print(f"  {r['title']:26} area {area} level {str(r['level']):>2}  {r['score']:6.1%}")
    print(f"\n{sum(1 for r in rows if r['score'] > 0.95)}/{len(rows)} placed above 95%")
