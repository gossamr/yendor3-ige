"""Pack each map page into grid + tileset, small enough to draw in the panel.

The page is a 34 x 24 grid of tile ids read from WORLD.DAT. The artwork for
those ids is lifted from the game's own render of the page: an id is drawn
with one 8x8 block wherever it appears, so a page needs only its handful of
distinct tiles, not a picture.

Packed that way a page is about 2 kB instead of a 6 kB PNG, and the panel can
draw it at any size instead of scaling a bitmap: the grid is the data, the
tileset is the palette it is drawn with.
"""

from __future__ import annotations

import base64
import collections
import json
import re
import struct
from pathlib import Path

import pngutil
import tiles as T
import markers
import render_maps
import registry
import sections as SEC
import solve_maps as S
from registry import map_names, map_registry

TILE = S.TILE
ROOT = Path(__file__).resolve().parent.parent

# The book prints cells 3..36 of a 40-cell row, and for a long time so did we --
# which cropped three columns off each side of every map. They are real squares:
# markers stand on them (DWARVEN HOMELAND MAP 1's ship is at cell 0), and levels
# are stored end to end along a band, so a 40-wide map abuts its neighbor
# exactly. The page is 40 wide; the book's window is what was arbitrary.
FULL_COLS = S.CELLS if hasattr(S, "CELLS") else 40


def full_grid(world, base, level, delta=0):
    """The whole 40-cell row, margins included."""
    return [[struct.unpack_from(
        "<H", world,
        base + level * S.LEVEL_STRIDE + c * S.CELL + band * S.BAND_STRIDE + delta)[0]
        for c in range(FULL_COLS)] for band in range(S.ROWS)]


# What the party may stand on. The step at image `0x032E9` happens only when
# two classifiers both return zero: `0x02EEA` on the cell's terrain word and
# `0x02F13` on its object word.
#
#   terrain   <=1 blocked, 2..99 blocked, 100..199 clear, 200..299 blocked,
#             300 and over clear
#   object    200..399 blocked, anything else clear
#
# Tinting the cells this calls clear draws the floor plan: the Athaneum's rooms
# and corridors, the paths through the Cave of Fire with the lava left out, the
# island at Delia's with the sea left out. Which is also what makes it worth
# using rather than a guess about which id is the ground: on a map that is
# mostly water, mostly-anything is water.
#
# Id 2 is a *wall*, not a floor: 434 of the Athaneum's 960 cells are brick.
WALKS = (range(100, 200), range(300, 65536))
BLOCKING_OBJECT = range(200, 400)


def walkable(world: bytes, area: int, level: int, band: int, cell: int) -> bool:
    """Can the party stand here?"""
    if not T.drawn(world, area, level, band, cell):
        return False
    at = (area * S.AREA_STRIDE + band * S.BAND_STRIDE
          + level * S.LEVEL_STRIDE + cell * S.CELL)
    terrain, obj = struct.unpack_from("<HH", world, at)
    return (any(terrain in r for r in WALKS) and obj not in BLOCKING_OBJECT)


def arrival(world: bytes, area: int, level: int) -> list[int] | None:
    """A cell of this map to put a party in, as `[band, cell]`.

    The party's place in the world is one x and one y across the whole grid --
    `x = level * 40 + cell`, `y = area * 24 + band`, so putting it on a map
    means naming a cell of that map, and it has to be one the party could have
    walked to. A bare cell is preferred over a walkable one with something on
    it: an object the party can stand on may be a door, and arriving on a door
    is arriving somewhere else.

    None where the map has no such cell.
    """
    base = area * S.AREA_STRIDE
    middle = (S.ROWS / 2, FULL_COLS / 2)
    best = None
    for band in range(S.ROWS):
        for cell in range(FULL_COLS):
            if not walkable(world, area, level, band, cell):
                continue
            at = (base + band * S.BAND_STRIDE
                  + level * S.LEVEL_STRIDE + cell * S.CELL)
            bare = struct.unpack_from("<H", world, at + 2)[0] == 0
            d = (band - middle[0]) ** 2 + (cell - middle[1]) ** 2
            key = (0 if bare else 1, d)
            if best is None or key < best[0]:
                best = (key, [band, cell])
    return best[1] if best else None


def pack_page(world, pics, exe, pal, area, level, title) -> dict:
    """One page, drawn from the game's files: grid, tiles and object sprites.

    Nothing here reads a picture of the game. A cell's terrain word picks a
    tile through the lookup in `REGISTER.EXE`, unless its bit at `0x3C4F02` is
    clear, in which case it draws the empty tile; a non-zero object word picks
    a sprite composited over that. See `tools/tiles.py`.

    The base layer and the objects stay separate in the output, as they are on
    screen: `grid` indexes `tiles`, and `overlay` names the cells that carry
    one of `sprites` on top.
    """
    base = area * S.AREA_STRIDE
    terrain = full_grid(world, base, level)
    objects = full_grid(world, base, level, delta=2)

    palette, index = [], {}
    def intern(block):
        for p in range(0, len(block), 3):
            rgb = block[p:p + 3]
            if rgb not in index:
                index[rgb] = len(palette)
                palette.append(rgb)

    blocks, slot = [], {}
    cells = bytearray(S.ROWS * FULL_COLS)
    sprites, overlay = {}, []
    for r in range(S.ROWS):
        for c in range(FULL_COLS):
            drawn = T.drawn(world, area, level, r, c)
            n = T.EMPTY if not drawn else T.terrain(exe, terrain[r][c])
            if n not in slot:
                slot[n] = len(blocks)
                block = T.render(pics, pal, T.BLOCK + n)
                blocks.append(block)
                intern(block)
            cells[r * FULL_COLS + c] = slot[n]

            sprite = T.obj(exe, objects[r][c]) if objects[r][c] else 0
            if not sprite:
                continue
            over = bytearray(blocks[slot[n]])
            raw = T.tile(pics, T.BLOCK + sprite)
            for i in range(T.TILE_BYTES):
                if raw[i] != 0xFF:
                    over[i * 3:i * 3 + 3] = pal[raw[i]]
            over = bytes(over)
            if over not in sprites:
                sprites[over] = len(sprites)
                intern(over)
            overlay.append([r, c, sprites[over]])

    pixels = bytes(index[b[p:p + 3]] for b in blocks for p in range(0, len(b), 3))
    sprite_pixels = bytes(index[b[p:p + 3]]
                          for b in sprites for p in range(0, len(b), 3))
    return {
        "title": title,
        "objects": sum(1 for r in range(S.ROWS) for c in range(FULL_COLS)
                       if objects[r][c]),
        "area": area,
        "level": level,
        "arrive": arrival(world, area, level),
        "cols": FULL_COLS, "rows": S.ROWS, "tile": TILE,
        "palette": [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in palette],
        "tiles": base64.b64encode(pixels).decode(),
        "grid": base64.b64encode(bytes(cells)).decode(),
        "sprites": base64.b64encode(sprite_pixels).decode(),
        "overlay": overlay,
    }


# --- The maps the clue book does not print ---------------------------------
#
# The book indexes 37 places, and both name tables in WORLD.DAT hold only those
# 37. The file itself holds 140 slots, and 63 of them carry a grid as varied as
# the least-varied page the book does print, so 27 drawn maps have no page.
# Eighteen of those carry legend markers, which is what gives them away: the
# book prints "THAINE MAP 3" as a destination on a map it never shows.
#
# They can still be drawn. A tile id means the same thing everywhere, so the
# artwork lifted from the captured pages covers them; only their *names* are
# missing, and nothing in the data supplies one.

# How much of an area's cells for a tile id must agree before that area's
# reading overrides the pooled one. Below this the page is telling us about
# what is drawn *over* the terrain, not about the terrain.
AGREEMENT = 0.6

# A margin tile no page has ever drawn. Black, so a hole is visible as a hole
# rather than passing for terrain.
BLANK = bytes(TILE * TILE * 3)





# Transitions confirmed by walking them in the game, for doors whose label
# does not say which map it means. SAXON'S SHIP TO THAINE says only "Thaine",
# and Thaine is ten maps; the ship lands on map 10. These are observations, not
# decodes: the table that holds them in the file has not been found yet, so
# anything not walked is left unlinked rather than guessed.
# A label can name a *region* where the registry only knows *maps*: "PORTAL TO
# BARIAG" picks none of Kingdom, Sewers or the two Castle levels. Both portals
# so far land on the kingdom, which is suggestive but is one observation each.
WALKED_LINKS = {
    ("YENDOR", "SAXON'S SHIP TO THAINE"): "THAINE MAP 10",
    ("ATHANEUM", "EXIT TO YENDOR"): "YENDOR",
    ("THAINE MAP 10", "PORTAL TO BARIAG"): "KINGDOM OF BARIAG",
}


def render(page) -> tuple[int, int, bytes]:
    """Draw a packed page back out, exactly as the panel does."""
    t = page["tile"]
    w, h = page["cols"] * t, page["rows"] * t
    pal = [bytes((int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)))
           for c in page["palette"]]
    tiles = base64.b64decode(page["tiles"])
    grid = base64.b64decode(page["grid"])
    sprites = base64.b64decode(page["sprites"] or "")
    buf = bytearray(w * h * 3)
    for r in range(page["rows"]):
        for c in range(page["cols"]):
            at = grid[r * page["cols"] + c] * t * t
            for y in range(t):
                for x in range(t):
                    i = ((r * t + y) * w + c * t + x) * 3
                    buf[i:i + 3] = pal[tiles[at + y * t + x]]
    for r, c, sprite in page["overlay"]:
        at = sprite * t * t
        for y in range(t):
            for x in range(t):
                i = ((r * t + y) * w + c * t + x) * 3
                buf[i:i + 3] = pal[sprites[at + y * t + x]]
    return w, h, bytes(buf)


def fidelity(page, loc, world=None, shot_dir="tmp/maps4") -> float | None:
    """What fraction of the game's own page the packed one reproduces.

    Measured over the window the clue book prints, which is the only part there
    is a picture of, and cell by cell rather than pixel by pixel so the two
    things a still cannot be compared against directly can be excluded:

    * The legend markers the game paints over the page. Those cells show a gold
      square rather than the terrain underneath, and the marker records say
      which they are.
    * The fire ramp at palette indices 220-223, which the game rotates. A still
      catches one phase of it, so a cell is counted as matching if it matches
      under any.
    """
    shot = ROOT / shot_dir / (loc.get("shot") or "")
    if not loc.get("shot") or not shot.exists():
        return None
    marked = set()
    if world is not None:
        marked = {(m["row"], m["col"]) for m in markers.read_markers(world)
                  if (m["area"], m["level"]) == (page["area"], page["level"])}
    phases = [_phase(page, n) for n in range(4)]
    sw, _, src = pngutil.read(str(shot))
    same = total = 0
    for r in range(S.ROWS):
        for c in range(S.COLS):
            if (r, c) in marked:
                continue
            total += 1
            theirs = b"".join(
                src[((S.Y0 + r * TILE + y) * sw + S.X0 + c * TILE) * 3:
                    ((S.Y0 + r * TILE + y) * sw + S.X0 + c * TILE) * 3 + TILE * 3]
                for y in range(TILE))
            same += any(cell(r, S.COL0 + c) == theirs for cell in phases)
    return same / total if total else None


def _phase(page, n):
    """A reader for one cell of the page, with the fire ramp rotated to phase n.

    The page's own palette is a list of colors, not indices, so the rotation
    is applied by swapping the four colors wherever they appear.
    """
    # The palette stores the ramp at rest, whose brightest color is not one of
    # the four the game cycles through, so it is aliased onto the fourth.
    hexed = lambda c: "#%02x%02x%02x" % tuple(c)
    ramp = [hexed(c) for c in T.FIRE]
    order = {ramp[k]: ramp[(k + n) % 4] for k in range(4)}
    order[hexed(T.FIRE_AT_REST)] = ramp[(3 + n) % 4]
    pal = [bytes.fromhex(order.get(c, c)[1:]) for c in page["palette"]]
    tiles = base64.b64decode(page["tiles"])
    grid = base64.b64decode(page["grid"])
    sprites = base64.b64decode(page["sprites"] or "")
    over = {(r, c): sp for r, c, sp in page["overlay"]}

    def read(r, c):
        sp = over.get((r, c))
        if sp is not None:
            at = sp * TILE * TILE
            return b"".join(pal[v] for v in sprites[at:at + TILE * TILE])
        at = grid[r * page["cols"] + c] * TILE * TILE
        return b"".join(pal[v] for v in tiles[at:at + TILE * TILE])
    return read


def main(out="data/map_pages.json") -> list[dict]:
    world = Path("game/WORLD.DAT").read_bytes()
    pics = (ROOT / "game" / "PICTURES.VGA").read_bytes()
    exe = (ROOT / "game" / "REGISTER.EXE").read_bytes()
    pal = T.palette(SEC.load("game"))
    names = map_registry(world)
    booked = {(c["area"], c["level"]): c for c in registry.captures(world)}

    # Every slot the registry names, drawn the same way: there is nothing a
    # page the clue book prints can be given that the others cannot.
    labels = markers.read_labels(world)
    marks = collections.defaultdict(list)
    for r in markers.read_markers(world):
        text = labels[r["field3"]] if r["field3"] < len(labels) else None
        if text:
            marks[(r["area"], r["level"])].append({"label": text})

    pages = []
    for (area, level), title in sorted(names.items()):
        page = pack_page(world, pics, exe, pal, area, level, title)
        page["in_book"] = (area, level) in booked
        page["fidelity"] = fidelity(page, booked[(area, level)], world) \
            if (area, level) in booked else None
        page["markers"] = marks[(area, level)]
        pages.append(page)

    # One order for the whole list. The book's pages used to come first and the
    # rest after, which was a fact about our capture run rather than about the
    # maps, and with the registry naming every slot there is no such
    # distinction left. Sort by name, splitting digits out so THAINE MAP 2 comes
    # before THAINE MAP 10 and a place's levels stay together.
    def natural(page):
        parts = re.split(r"(\d+)", page["title"])
        return [int(x) if x.isdigit() else x for x in parts]

    pages.sort(key=natural)
    path = ROOT / out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pages, separators=(",", ":")))
    return pages


if __name__ == "__main__":
    pages = main()
    size = (ROOT / "data" / "map_pages.json").stat().st_size
    tiles = sum(len(p["palette"]) for p in pages)
    marks = sum(len(p["overlay"]) for p in pages)
    print(f"{len(pages)} pages packed into {size / 1024:.0f} kB "
          f"({tiles} palette entries, {marks} marker cells)")
    print(f"  the PNGs they replace: "
          f"{sum(f.stat().st_size for f in (ROOT / 'web' / 'maps').glob('*.png')) / 1024:.0f} kB")
