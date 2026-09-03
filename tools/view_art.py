"""The artwork the first-person view draws, one PNG per picture.

    PYTHONPATH=tools python tools/view_art.py        # writes data/view_art.json

Four kinds of picture reach the viewport, and [view.py](view.py) says which
run each pass takes its own from:

  * **floors**, run 4, 224 x 74. A whole floor drawn in perspective; a cell
    copies its own trapezoid out of one.
  * **ceilings**, run 5, 224 x 62, the same the other way up. Numbers 0 and 1
    are the sky, which is also what shows past the last row the view covers.
  * **wall faces**, run 1, 210 x 105, named by a terrain record's `+4`. The
    game maps one into a cell's slot a column at a time; drawn flat they are
    just wall.
  * **object faces**, run 1 for ids 100 and up and run 2 for the rest. An
    object record holds four of them, one per facing, so a door is a door from
    one side and a doorway from the other.
  * **strips**, run 6, 56 x 136. A wall seen almost edge on, at the far left
    and right of the view. A terrain record names the picture and the first of
    the 14 columns it uses, and the two cells either side of the view take
    7 of those columns each.

Monsters and their shots are the fifth thing the viewport draws and are
already exported, by `monster_art` and `projectile_art` in
[extract.py](extract.py).

Floors and ceilings fill their frame, so they are written whole, and so does a
strip, whose columns are indexed into the full width. A wall or an object face
is mostly transparent, so it is cropped and the corner it was cut from is kept:
the game draws it at its place in the full frame.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pictures as P
import pngutil
import sections as SEC
import tiles
import view as V

# Section 12's first palette, the one the map screen and the monster pages
# draw with.
PALETTE = 0
# Where an object record keeps its four view pictures, in the order image
# `0x10668` tests the facings: north, south, east, west. Its fifth word is the
# map tile tools/tiles.py reads.
OBJECT_FACES = (0x00, 0x02, 0x04, 0x06)
# Which run an object's face is in: image `0x1069C` sends ids up to 99 to
# bank 0x20 and the rest to bank 0x10.
OBJECT_SMALL_RUN, OBJECT_LARGE_RUN = 2, 1
OBJECT_SMALL_MAX = 0x63
# What the id-to-record walk covers. Terrain ids run 0..340 (docs/map.md) and
# objects are a word in the same cell, so both are walked over their whole
# range and the distinct records kept.
TERRAIN_IDS, OBJECT_IDS = range(341), range(400)


def object_record(exe: bytes, object_id: int) -> int:
    """The DS offset of an object id's 10-byte record."""
    family, index = divmod(object_id, tiles.FAMILY)
    base = tiles._word(exe, tiles.OBJECT_TABLE + family * 4)
    last = tiles._word(exe, tiles.OBJECT_TABLE + family * 4 + 2)
    if index > last:
        return tiles._word(exe, tiles.OBJECT_TABLE)
    return base + index * tiles.OBJECT_RECORD


def wanted(exe: bytes) -> dict[str, dict]:
    """Which pictures of which run the view can ask for, and what asks."""
    floors: dict[int, list[int]] = {}
    ceilings: dict[int, list[int]] = {}
    walls: dict[int, list[int]] = {}
    strips: dict[int, list[int]] = {}
    seen = set()
    for terrain_id in TERRAIN_IDS:
        at = V.record(exe, terrain_id)
        if at in seen:
            continue
        seen.add(at)
        for axis in (0, 1):
            floors.setdefault(V.picture(exe, terrain_id, V.FLOOR, axis), []) \
                  .append(terrain_id)
            ceilings.setdefault(V.picture(exe, terrain_id, V.CEILING, axis), []) \
                    .append(terrain_id)
        face = V.picture(exe, terrain_id, V.WALL, 0)
        if face is not None:
            walls.setdefault(face, []).append(terrain_id)
        strip = V.picture(exe, terrain_id, V.STRIP, 0)
        if strip is not None:
            strips.setdefault(strip, []).append(terrain_id)

    objects: dict[tuple[int, int], list[int]] = {}
    seen = set()
    for object_id in OBJECT_IDS:
        at = object_record(exe, object_id)
        if at in seen:
            continue
        seen.add(at)
        run = OBJECT_SMALL_RUN if object_id <= OBJECT_SMALL_MAX else OBJECT_LARGE_RUN
        for off in OBJECT_FACES:
            face = tiles._word(exe, at + off)
            if face:
                objects.setdefault((run, face), []).append(object_id)
    return {"floor": floors, "ceiling": ceilings, "wall": walls,
            "strip": strips, "object": objects}


def _entry(raw: bytes, run: P.Run, palette: list[bytes], crop: bool) -> dict:
    """One picture as a PNG, with the corner it was cut from where cropped."""
    x0, y0, x1, y1 = P.bounds(raw, run.width) if crop else (0, 0, run.width, run.height)
    if x1 <= x0 or y1 <= y0:
        x0, y0, x1, y1 = 0, 0, 1, 1
    pixels = b"".join(raw[y * run.width + x0:y * run.width + x1]
                      for y in range(y0, y1))
    used = sorted(set(pixels) - {P.TRANSPARENT})
    slot = {v: i + 1 for i, v in enumerate(used)}
    png = pngutil.encode_indexed(
        x1 - x0, y1 - y0, bytes(slot.get(v, 0) for v in pixels),
        [b"\x00\x00\x00"] + [palette[v] for v in used], transparent=0)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0,
            "src": "data:image/png;base64," + base64.b64encode(png).decode()}


def build(game_dir: str | Path = "game", out_dir: str | Path = "data") -> dict:
    game = Path(game_dir)
    d = SEC.load(game)
    pics = (game / "PICTURES.VGA").read_bytes()
    runs = P.read_runs(d.exe, len(pics))
    palette = tiles.palette(d, PALETTE)
    asked = wanted(d.exe)

    out: dict[str, dict] = {
        "frame": {"x": V.VIEW_X, "y": V.VIEW_Y,
                  "width": V.VIEW_W, "height": V.VIEW_H,
                  "ceiling_y": V.CEILING_Y, "floor_y": V.FLOOR_Y,
                  "horizon": V.HORIZON, "width_per_row": V.WIDTH_PER_ROW,
                  "floor_band": list(V.FLOOR_BAND),
                  "ceiling_band": list(V.CEILING_BAND),
                  "strip": [V.STRIP_W, V.STRIP_H, V.STRIP_HALF]},
    }
    for kind, run_index, crop in (("floor", V.RUN[V.FLOOR], False),
                                  ("ceiling", V.RUN[V.CEILING], False),
                                  ("strip", V.RUN[V.STRIP], False),
                                  ("wall", V.RUN[V.WALL], True)):
        run = runs[run_index]
        out[kind] = {str(n): _entry(P.picture(pics, run, n), run, palette, crop)
                     for n in sorted(asked[kind])}
    out["object"] = {}
    for (run_index, n), _ in sorted(asked["object"].items()):
        run = runs[run_index]
        out["object"][f"{run_index}/{n}"] = _entry(
            P.picture(pics, run, n), run, palette, True)

    out["cells"] = {
        "terrain": {str(t): {"floor": V.picture(d.exe, t, V.FLOOR, 0),
                             "ceiling": V.picture(d.exe, t, V.CEILING, 0),
                             "wall": V.picture(d.exe, t, V.WALL, 0),
                             "strip": V.picture(d.exe, t, V.STRIP, 0),
                             "column": V.column(d.exe, t)}
                    for t in TERRAIN_IDS},
        "object": {str(o): [tiles._word(d.exe, object_record(d.exe, o) + off)
                            for off in OBJECT_FACES]
                   for o in range(300)},
    }
    out["slots"] = {
        str(mode): [None if s is None else {"x": s.x, "y": s.y,
                                            "rows": [list(r) for r in s.rows]}
                    for s in V.slots(d.world, mode, d)]
        for mode in (V.FLOOR, V.CEILING)
    }

    path = Path(out_dir) / "view_art.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, separators=(",", ":")))
    return out


if __name__ == "__main__":
    import sys

    built = build(sys.argv[1] if len(sys.argv) > 1 else "game")
    for kind in ("floor", "ceiling", "strip", "wall", "object"):
        print(f"{kind:<8} {len(built[kind]):>4}")
    print(f"\nwrote data/view_art.json "
          f"{Path('data/view_art.json').stat().st_size / 1024:.0f} kB")
