"""Draw the view's floor and ceiling from the files, and diff a capture.

    PYTHONPATH=tools python tools/view_check.py \
        --probe=tmp/view-north.json --shot=tmp/view-probe/00-after-entering.png

The reading in [view.py](view.py) is only as good as a picture it reproduces.
This one takes a frame the game drew, redraws the passes whose slot format is
decoded, and counts the pixels that agree. The wall pass keeps its slots in a
column format that is not read yet, so cells whose terrain names a wall are
left out of the count and the residual image shows what is left.

The strips are counted separately. The pair either side of the party is drawn
last and nothing covers it, so those two are held to the frame exactly; the
rest of the pair are counted where a nearer cell has not drawn over them.

`--probe` is what [view_probe.js](view_probe.js) wrote: it supplies the party's
position and, per cell, the bit that says the game skipped it. Which cells the
view covers is worked out here rather than taken from the probe, so a run also
checks `view.FACINGS` against the game's own table.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import pictures as P
import pngutil
import sections as SEC
import tiles
import view as V

# Section 12's first palette, which is the one the map screen draws with.
PALETTE = 0
# Indices 224 and up are one ramp from blue to white, and the sky is drawn in
# it. A capture reads one step down that ramp from what the picture holds, the
# same way a still of a map page catches one phase of the fire ramp
# (docs/map.md). Why is not settled, so the count reports it separately.
SKY = 224


def draw(exe: bytes, world: bytes, pics: bytes, d: SEC.Directory,
         party: dict, skipped: list[bool]) -> tuple[bytearray, dict]:
    """The screen the two passes produce, and which cell wrote each pixel."""
    runs = P.read_runs(exe, len(pics))
    cells = V.frustum(party["x"], party["y"], party["facing"])
    ids = [terrain(world, x, y) for x, y in cells]
    axis = V.axis_bit(party["facing"],
                      tiles._word(exe, V.record(exe, ids[49]) + V.TERRAIN_CEILING))

    screen = bytearray(320 * 200)
    owner: dict[tuple[int, int], int] = {}

    def whole(mode: int, number: int, top: int) -> None:
        run = runs[V.RUN[mode]]
        raw = P.picture(pics, run, number)
        for y in range(run.height):
            at = (top + y) * 320 + V.VIEW_X
            screen[at:at + run.width] = raw[y * run.width:(y + 1) * run.width]

    def pass_over(mode: int, top: int) -> None:
        run = runs[V.RUN[mode]]
        for cell, slot in enumerate(V.slots(world, mode, d)):
            if slot is None or skipped[cell]:
                continue
            raw = P.picture(pics, run, V.picture(exe, ids[cell], mode, axis))
            for y, x, length in slot.spans():
                for i in range(length):
                    screen[(top + y) * 320 + V.VIEW_X + x + i] = raw[y * run.width + x + i]
                    owner[(V.VIEW_X + x + i, top + y)] = cell

    # The two backgrounds first: whatever the frustum leaves uncovered is sky
    # above and the party's own floor below (image `0x10249`).  Strips are not
    # drawn here: they are held to the frame on their own, below.
    whole(V.CEILING, axis, V.CEILING_Y)
    whole(V.FLOOR,
          tiles._word(exe, V.record(exe, ids[49]) + V.TERRAIN_FLOOR) & 1, V.FLOOR_Y)
    pass_over(V.FLOOR, V.FLOOR_Y)
    pass_over(V.CEILING, V.CEILING_Y)
    return screen, owner


# The two cells either side of the party. The strip pass draws them last, so
# nothing covers them and they can be held to the frame exactly.
NEAREST_PAIR = (48, 50)


def strip_check(exe, world, pics, d, ids, skipped, shot):
    """(cell, picture, column, matching, opaque) for each of the nearest pair.

    Image `0x1A055` draws a strip 7 pixels wide and 0x71 rows tall, from the
    column the terrain record names, at the place mode 3's own table gives.
    The second of a pair takes the column 7 further on (`0x10764`).
    """
    section = d.sections[V.GEOMETRY]
    blob = world[section.offset:section.end]
    run = P.read_runs(exe, len(pics))[V.RUN[V.STRIP]]
    out = []
    for nth, cell in enumerate(NEAREST_PAIR):
        number = V.picture(exe, ids[cell], V.STRIP, 0)
        if number is None or skipped[cell]:
            continue
        x, y, _ = struct.unpack_from("<HHH", blob,
                                     V.MODE_OFFSET[V.WALL] + cell * 6)
        col = V.column(exe, ids[cell], bool(nth))
        raw = P.picture(pics, run, number)
        hit = opaque = 0
        for row in range(V.STRIP_H):
            for i in range(V.STRIP_W):
                held = raw[row * run.width + col + i]
                if held == P.TRANSPARENT:
                    continue
                opaque += 1
                hit += shot(x + i, y + row) == held
        out.append((cell, number, col, hit, opaque))
    return out


def terrain(world: bytes, x: int, y: int) -> int:
    """The terrain id of one world cell. docs/map.md has the arithmetic."""
    area, band = divmod(y, 24)
    level, cell = divmod(x, 40)
    at = area * 76800 + band * 3200 + level * 160 + cell * 4
    return struct.unpack_from("<H", world, at)[0]


def captured(path: str, palette: list[bytes]) -> callable:
    """A reader turning the shot's pixels back into palette indices.

    js-dos delivers the 320 x 200 screen doubled, so a pixel is read from the
    top left of its four. Fifteen colors appear twice in the palette and the
    lower index wins; none of the fifteen is in the sky ramp.
    """
    width, _, rgb = pngutil.read(path)
    scale = width // 320
    back: dict[tuple[int, ...], int] = {}
    for i, c in enumerate(palette):
        back.setdefault(tuple(c), i)

    def read(x: int, y: int) -> int:
        at = ((y * scale) * width + x * scale) * 3
        return back.get(tuple(rgb[at:at + 3]), -1)

    return read


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", default="tmp/view-north.json")
    ap.add_argument("--shot", default="tmp/view-probe/00-after-entering.png")
    ap.add_argument("--game", default="game")
    ap.add_argument("--out", default="tmp/view-check.png")
    a = ap.parse_args()

    game = Path(a.game)
    d = SEC.load(game)
    exe = (game / "REGISTER.EXE").read_bytes()
    world = (game / "WORLD.DAT").read_bytes()
    pics = (game / "PICTURES.VGA").read_bytes()
    probe = json.loads(Path(a.probe).read_text())
    party, rows = probe["party"], probe["rows"]

    cells = V.frustum(party["x"], party["y"], party["facing"])
    wrong = [(i, r["draws"], terrain(world, *cells[i]))
             for i, r in enumerate(rows) if r["draws"] != terrain(world, *cells[i])]
    print(f"frustum: {51 - len(wrong)}/51 cells agree with the table the game built")
    for i, held, want in wrong:
        print(f"  cell {i}: the game read {held}, the frustum says {want}")

    screen, owner = draw(exe, world, pics, d, party, [r["skipped"] for r in rows])
    palette = tiles.palette(d, PALETTE)
    shot = captured(a.shot, palette)
    ids = [terrain(world, x, y) for x, y in cells]

    # A wall stands floor to ceiling, so it covers every row of the columns its
    # own cell spans, and the same columns of anything standing behind it.
    # Those pixels are the third pass's, so they are not counted here. Each
    # column keeps the nearest wall standing in it, as a depth in cells.
    depth = [ahead for run, ahead in enumerate(V.DEPTHS)
             for _ in range(V.RUNS[run])]
    walled: dict[int, int] = {}
    for mode in (V.FLOOR, V.CEILING):
        for cell, slot in enumerate(V.slots(world, mode, d)):
            if slot is None or rows[cell]["skipped"]:
                continue
            if V.picture(exe, ids[cell], V.WALL, 0) is None:
                continue
            for _, x, length in slot.spans():
                for i in range(length):
                    at = V.VIEW_X + x + i
                    walled[at] = min(walled.get(at, 99), depth[cell])

    exact = phase = left = 0
    residual = set()
    for (x, y), cell in owner.items():
        if walled.get(x, 99) <= depth[cell]:
            continue
        drew, got = screen[y * 320 + x], shot(x, y)
        if got == drew:
            exact += 1
        elif drew >= SKY and got == drew - 1:
            phase += 1
        else:
            left += 1
            residual.add((x, y))
    total = exact + phase + left
    print(f"floor and ceiling: {exact}/{total} exact, {phase} one step down the sky "
          f"ramp, {left} left over")

    for cell, number, col, hit, opaque in strip_check(
            exe, world, pics, d, ids, [r["skipped"] for r in rows], shot):
        print(f"strip at cell {cell}: picture {number} column {col}, "
              f"{hit}/{opaque} exact")

    out = bytearray()
    for y in range(200):
        for x in range(320):
            if (x, y) in residual:
                out += b"\xff\x00\x00"
            elif (x, y) in owner:
                out += bytes(palette[screen[y * 320 + x]])
            else:
                out += b"\x14\x14\x14"
    if residual:
        by = {}
        for x, y in residual:
            by[owner[(x, y)]] = by.get(owner[(x, y)], 0) + 1
        print("  left over by cell: " + ", ".join(
            f"{c}({ids[c]}) x{n}" for c, n in sorted(by.items(), key=lambda kv: -kv[1])[:10]))
    pngutil.write(a.out, 320, 200, bytes(out))
    print(f"wrote {a.out}: what the two passes drew, the leftovers in red")


if __name__ == "__main__":
    main()
