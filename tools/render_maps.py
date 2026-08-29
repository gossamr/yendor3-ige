"""Render the clue-book maps from the decoded tile grids.

The grid comes out of WORLD.DAT (see solve_maps.py for the addressing). The
tile *artwork* is lifted from the captured pages rather than decoded out of
PICTURES.VGA: each id is drawn with the same 8x8 block wherever it appears, so
one sample per id is a complete atlas, and building it that way costs nothing
and needs no picture-format work.

The point of rendering rather than keeping the captures is that the result is
generated from the game's data: it can be drawn at any size, the grid can be
queried, and a page the capture walk happened to miss can still be produced.
"""

from __future__ import annotations

import collections
import json
import struct
from pathlib import Path

import pngutil
import registry
import solve_maps as S

# Content read off the game's screens, not decoded from its files. Never
# shipped.
OBSERVED = Path(__file__).resolve().parent.parent / "observed"

ROOT = Path(__file__).resolve().parent.parent
TILE = S.TILE


def build_atlas(locations, world, shot_dir="tmp/maps4"):
    """(page, id) -> the 8x8 block the game draws for it.

    Keyed per page, not per area: each map loads its own tileset (the 1,087-byte
    blocks the tracer sees it pull from PICTURES.VGA), so the same id is grass
    on one page and stone on the next. Elfin City and Elfin Sewer share an area
    and disagree completely.

    Sampling the artwork from the page the game drew, rather than decoding
    PICTURES.VGA, is deliberate: the *grid* is what comes out of WORLD.DAT, and
    that is what makes the map generated rather than photographed. How well one
    block per id reproduces the page is then a direct measure of whether the
    grid is right: a wrong grid cannot be compressed to ten tiles and put back.
    """
    seen = collections.defaultdict(collections.Counter)
    for loc in locations:
        if loc["base"] is None:
            continue
        w, h, rgb = pngutil.read(f"{shot_dir}/{loc['shot']}")
        grid = S.read_grid(world, loc["base"], loc["level"])
        for r in range(S.ROWS):
            for c in range(S.COLS):
                block = b"".join(
                    rgb[((S.Y0 + r * TILE + y) * w + S.X0 + c * TILE) * 3:
                        ((S.Y0 + r * TILE + y) * w + S.X0 + c * TILE) * 3 + TILE * 3]
                    for y in range(TILE))
                seen[(loc["shot"], grid[r][c])][block] += 1
    return {key: blocks.most_common(1)[0][0] for key, blocks in seen.items()}


def render(grid, atlas, page, missing=b"\x20\x20\x20" * (TILE * TILE)):
    w, h = S.COLS * TILE, S.ROWS * TILE
    out = bytearray(w * h * 3)
    for r in range(S.ROWS):
        for c in range(S.COLS):
            block = atlas.get((page, grid[r][c]), missing)
            for y in range(TILE):
                dst = ((r * TILE + y) * w + c * TILE) * 3
                out[dst:dst + TILE * 3] = block[y * TILE * 3:(y + 1) * TILE * 3]
    return w, h, bytes(out)


def accuracy(rendered, shot):
    """Fraction of pixels that match the page the game drew."""
    w, h, mine = rendered
    sw, sh, theirs = pngutil.read(shot)
    same = total = 0
    for r in range(h):
        for c in range(w):
            a = (r * w + c) * 3
            b = ((S.Y0 + r) * sw + S.X0 + c) * 3
            same += mine[a:a + 3] == theirs[b:b + 3]
            total += 1
    return same / total


def main(out_dir="web/maps", shot_dir="tmp/maps4"):
    world = Path("game/WORLD.DAT").read_bytes()
    locations = registry.captures(world)
    atlas = build_atlas(locations, world, shot_dir)
    print(f"atlas: {len(atlas)} distinct tiles")
    out = ROOT / out_dir
    out.mkdir(parents=True, exist_ok=True)
    pages = []
    for i, loc in enumerate(locations):
        grid = S.read_grid(world, loc["base"], loc["level"])
        image = render(grid, atlas, loc["shot"])
        acc = accuracy(image, f"{shot_dir}/{loc['shot']}")
        path = out / f"{i:02d}.png"
        pngutil.write(str(path), *image)
        pages.append({"title": loc["title"], "image": f"maps/{i:02d}.png",
                      "width": image[0], "height": image[1],
                      "base": loc["base"], "level": loc["level"],
                      "accuracy": round(acc, 4)})
        print(f"  {loc['title']:26} {acc:6.2%} of pixels match the game's own page")
    return pages, atlas


if __name__ == "__main__":
    pages, atlas = main()
    OBSERVED.mkdir(exist_ok=True)
    (OBSERVED / "observed_maps.json").write_text(
        json.dumps(pages, indent=1) + "\n")
    mean = sum(p["accuracy"] for p in pages) / len(pages)
    print(f"\n{len(pages)} maps rendered from data, mean accuracy {mean:.2%}")
