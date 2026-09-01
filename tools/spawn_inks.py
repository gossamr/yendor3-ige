#!/usr/bin/env python3
"""What the map tab draws each map's spawn dots in, and how far they get.

    python tools/spawn_inks.py           # every map, the tightest first
    python tools/spawn_inks.py --worst   # only the maps with the least room

The rule and the grid are read out of web/panel.js. This reports the tab's own
picks rather than a second opinion on them.

A dot is seen against two things: the colors the map paints where the monsters
stand, and the other dots. Each one is put as far from all of that as sRGB
allows. The tab takes the furthest color for the first kind, then the furthest
from the map and from that one for the second, and so on.

The field is the pixels of each spawn cell and the eight cells around it. A dot
sits in the middle of its cell and is read against what surrounds it. Overlay
sprites are opaque, so a cell carrying one gives the sprite and not the tile
beneath. Every color above SPECK of the sample counts, because a stand of trees
is ten shades of the same green at a percent or two each, and a dot drawn in
one of them is a tree.

The number this prints is that distance in dE76, the smallest one each map's
dots have to live with. It is a floor, not a fit: nothing is being met, only
maximized.
"""
from __future__ import annotations

import base64
import itertools
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "web" / "panel.js"

STEP = 8          # the sRGB grid `--ceiling` walks


def rules() -> dict:
    """The grid and the speck threshold, read out of web/panel.js."""
    src = PANEL.read_text()
    levels = re.search(r"const INK_LEVELS = \[(.*?)\];", src, re.S)
    return {"levels": [int(n) for n in re.findall(r"\d+", levels.group(1))],
            "SPECK": float(
                re.search(r"const INK_SPECK = ([\d.]+);", src).group(1))}


R = rules()


def _linear(u: float) -> float:
    return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4


def lab(hex_color: str) -> tuple[float, float, float]:
    """sRGB hex to CIELAB, D65."""
    r, g, b = (_linear(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def dE(a, b) -> float:
    """CIELAB dE76, the distance the panel maximizes."""
    return math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])


def field(page: dict, points: list[dict]) -> list[dict]:
    """Every color a dot on this map lands on or beside, specks dropped."""
    size = page["tile"]
    tiles = base64.b64decode(page["tiles"])
    grid = base64.b64decode(page["grid"])
    sprites = base64.b64decode(page.get("sprites") or "")
    over = {row * page["cols"] + col: sprite
            for row, col, sprite in page.get("overlay") or []}
    seen: dict[str, int] = {}
    total = 0
    for p in points:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                row, col = p["row"] + dr, p["col"] + dc
                if not (0 <= row < page["rows"] and 0 <= col < page["cols"]):
                    continue
                at = row * page["cols"] + col
                art = tiles if at not in over else sprites
                base = (grid[at] if at not in over else over[at]) * size * size
                for pixel in range(size * size):
                    color = page["palette"][art[base + pixel]]
                    seen[color] = seen.get(color, 0) + 1
                    total += 1
    return [{"hex": c, "lab": lab(c), "share": n / total}
            for c, n in seen.items() if n / total >= R["SPECK"]]


def ink_grid() -> list[tuple[str, tuple[float, float, float]]]:
    """The colors the panel chooses from, its own nine-level cut of sRGB."""
    return [(name, lab(name))
            for r in R["levels"] for g in R["levels"] for b in R["levels"]
            if (name := f"#{r:02x}{g:02x}{b:02x}")]


GRID = ink_grid()


def pick(kinds: list[str],
         colors: list[dict]) -> list[tuple[str, str, float]]:
    """Each kind's ink and how far it sits: web/panel.js' own walk."""
    against = [c["lab"] for c in colors]
    out = []
    for kind in kinds:
        far, taken = max(
            (min(dE(point, a) for a in against), name) for name, point in GRID)
        against.append(lab(taken))
        out.append((kind, taken, far))
    return out


def maps() -> list[tuple[str, list[dict], list[str]]]:
    """Every map that places monsters, with its field and its kinds.

    The kinds come in census order, which is the order the tab colors them in.
    """
    pages = {p["title"]: p for p in
             json.loads((ROOT / "data" / "map_pages.json").read_text())}
    points = json.loads((ROOT / "data" / "spawn_points.json").read_text())
    census = json.loads((ROOT / "data" / "spawns.json").read_text())
    out = []
    for title, placed in points.items():
        kinds = list(census.get(title, {}).get("monsters", {}))
        if title in pages and kinds:
            out.append((title, field(pages[title], placed), kinds))
    return out


def main(argv: list[str]) -> None:
    rows = []
    for title, colors, kinds in maps():
        taken = pick(kinds, colors)
        rows.append((min(f for _, _, f in taken), title, colors, taken))
    rows.sort()
    print(f"{len(rows)} maps place monsters. The tightest dot on any of them "
          f"sits {rows[0][0]:.0f} dE from what it has to stand out against; "
          f"the roomiest {rows[-1][0]:.0f}.")
    print("  least  map                          dots")
    for least, title, colors, taken in (rows[:8] if "--worst" in argv
                                        else rows):
        dots = ", ".join(f"{kind.title()} {ink} ({far:.0f})"
                         for kind, ink, far in taken)
        print(f"  {least:5.0f}  {title:<28}  {dots}")


if __name__ == "__main__":
    main(sys.argv[1:])
