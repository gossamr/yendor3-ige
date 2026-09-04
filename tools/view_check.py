"""Draw the view from the files, and diff a capture.

    PYTHONPATH=tools python tools/view_check.py \
        --probe=tmp/view-north.json --shot=tmp/view-probe/00-after-entering.png
    PYTHONPATH=tools python tools/view_check.py \
        --ledger=tmp/view-objects.json --frames=tmp/view-objects-frames

The reading in [view.py](view.py) is only as good as a picture it reproduces.
The first form takes a frame the game drew, redraws the floor and ceiling
passes with the skip bits the probe read, and counts the pixels that agree
outside the walls. The second draws every pass, walls and objects from the
section 27 lists and the strips beside the party, for each stop in a probe's
ledger, and diffs the whole viewport index for index, split by which pass
drew each pixel. The residual image shows what is left in red.

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


# --- Every pass, for the ledger form --------------------------------------

# Where the wall pass's faces land in the viewport: the corner tables are in
# screen coordinates, and the two halves of the view start at these rows.
STRIP_LEFT, STRIP_RIGHT, STRIP_TOP = 8, 225, 14
STAGE = {"floor": 1, "ceiling": 2, "face": 3, "strip": 4}


def cell_words(world: bytes, x: int, y: int) -> tuple[int, int]:
    """Terrain and object of one world cell, zero off the grid."""
    if not (0 <= x < 800 and 0 <= y < 168):
        return 0, 0
    area, band = divmod(y, 24)
    level, cell = divmod(x, 40)
    at = area * 76800 + band * 3200 + level * 160 + cell * 4
    return struct.unpack_from("<HH", world, at)


def object_face(exe: bytes, object_id: int, facing: int) -> tuple[int, int] | None:
    """(run, picture) of an object seen from this facing, or None."""
    import view_art as VA
    at = VA.object_record(exe, object_id)
    order = (V.NORTH, V.SOUTH, V.EAST, V.WEST)
    face = tiles._word(exe, at + VA.OBJECT_FACES[order.index(facing)])
    if not face:
        return None
    run = VA.OBJECT_SMALL_RUN if object_id <= VA.OBJECT_SMALL_MAX else VA.OBJECT_LARGE_RUN
    return run, face


class Frame:
    """A 320 x 200 screen, with which cell and which pass wrote each pixel."""

    def __init__(self):
        self.screen = bytearray(320 * 200)
        self.owner = [-1] * (320 * 200)
        self.stage = bytearray(320 * 200)

    def put(self, x: int, y: int, v: int, cell: int, stage: int) -> None:
        if v == P.TRANSPARENT or not (V.VIEW_X <= x < V.VIEW_X + V.VIEW_W
                                      and V.VIEW_Y <= y < V.VIEW_Y + V.VIEW_H):
            return
        i = y * 320 + x
        self.screen[i] = v
        self.owner[i] = cell
        self.stage[i] = stage


def draw_two_level(frame: Frame, raw: bytes, width: int, face: dict, cell: int) -> None:
    """A front or object face: the row list down, the column list across."""
    dy, sy = face["y"], 0
    for repeat, draw, skip in face["rows"]:
        for _ in range(repeat):
            for _ in range(draw):
                dx, sx = face["x"], 0
                for r2, d2, k2 in face["cols"]:
                    for _ in range(r2):
                        for _ in range(d2):
                            frame.put(dx, dy, raw[sy * width + sx] if sx < width else P.TRANSPARENT,
                                      cell, STAGE["face"])
                            dx += 1
                            sx += 1
                        sx += k2
                dy += 1
                sy += 1
            sy += skip


def draw_side(frame: Frame, raw: bytes, width: int, face: dict, right: bool, cell: int) -> None:
    """A side face, one column at a time; the destination drops a row per
    record on the left of the view and rises one on the right."""
    dx, dy, sx = face["x"], face["y"], 0
    for rec in face["records"]:
        if not rec["rows"]:
            sx += rec["step"]
            continue
        for _ in range(rec["count"]):
            y, sy = dy, 0
            for repeat, draw, skip in rec["rows"]:
                for _ in range(repeat):
                    for _ in range(draw):
                        frame.put(dx, y, raw[sy * width + sx] if sx < width else P.TRANSPARENT,
                                  cell, STAGE["face"])
                        y += 1
                        sy += 1
                    sy += skip
            sx += 1 + rec["step"]
            dx += 1
        dy += -1 if right else 1


def render(exe: bytes, world: bytes, pics: bytes, d: SEC.Directory, party: dict,
           poked: bool = False) -> Frame:
    """The whole view: sky and floor whole, the two slot passes, then each
    row's faces far to near in the wall pass's order, then the strips.

    The axis bits are the party's own cell's (docs/view.md, "The passes, in
    order"); `poked` draws with the bits a position the probe poked gets,
    which are the last stepped-to cell's. The skip bits are not needed,
    since a row drawn after the one behind it covers it.
    """
    runs = P.read_runs(exe, len(pics))
    facing = party["facing"]
    cells = V.frustum(party["x"], party["y"], facing)
    words = [cell_words(world, x, y) for x, y in cells]
    ids = [t for t, _ in words]
    party_record = V.record(exe, ids[49])
    party_floor = tiles._word(exe, party_record + V.TERRAIN_FLOOR)
    party_ceiling = tiles._word(exe, party_record + V.TERRAIN_CEILING)
    by_facing = 0 if facing in (V.NORTH, V.SOUTH) else 1
    if poked:
        ceiling_axis, floor_axis = by_facing, 0
    else:
        ceiling_axis = party_ceiling & 1 if party_ceiling else by_facing
        floor_axis = party_floor & 1
    frame = Frame()

    def whole(mode: int, number: int, top: int) -> None:
        run = runs[V.RUN[mode]]
        raw = P.picture(pics, run, number)
        for y in range(run.height):
            for x in range(run.width):
                frame.put(V.VIEW_X + x, top + y, raw[y * run.width + x], -1,
                          STAGE["floor" if mode == V.FLOOR else "ceiling"])

    def slot_pass(mode: int, top: int, axis: int) -> None:
        run = runs[V.RUN[mode]]
        for cell, slot in enumerate(V.slots(world, mode, d)):
            if slot is None:
                continue
            raw = P.picture(pics, run, V.picture(exe, ids[cell], mode, axis))
            for y, x, length in slot.spans():
                for i in range(length):
                    frame.put(V.VIEW_X + x + i, top + y, raw[y * run.width + x + i], cell,
                              STAGE["floor" if mode == V.FLOOR else "ceiling"])

    whole(V.CEILING, ceiling_axis, V.CEILING_Y)
    whole(V.FLOOR, (party_floor & ~1) | floor_axis, V.FLOOR_Y)
    slot_pass(V.FLOOR, V.FLOOR_Y, floor_axis)
    slot_pass(V.CEILING, V.CEILING_Y, ceiling_axis)

    tables = {name: V.faces(world, name, d) for name in V.FACE_TABLES}
    wall_run = runs[V.RUN[V.WALL]]

    def cell_faces(cell: int, lateral: int) -> None:
        terrain_id, object_id = words[cell]
        wall = V.picture(exe, terrain_id, V.WALL, 0)
        if wall is not None:
            raw = P.picture(pics, wall_run, wall)
            if tables["front"][cell]:
                draw_two_level(frame, raw, wall_run.width, tables["front"][cell], cell)
            # Image 0x10520: a side face only where the cell toward the center
            # names neither a wall face nor a strip.
            if lateral and tables["side"][cell]:
                inner = ids[cell - (1 if lateral > 0 else -1)]
                if V.picture(exe, inner, V.WALL, 0) is None and V.picture(exe, inner, V.STRIP, 0) is None:
                    draw_side(frame, raw, wall_run.width, tables["side"][cell], lateral > 0, cell)
        if object_id:
            found = object_face(exe, object_id, facing)
            if found:
                run_index, number = found
                run = runs[run_index]
                table = ("front" if object_id >= 200 else
                         "object_wide" if run_index == 1 else "object_tall")
                if tables[table][cell]:
                    draw_two_level(frame, P.picture(pics, run, number), run.width,
                                   tables[table][cell], cell)

    # Image 0x104A8: each row's left half from the outside in, its right half
    # the same way, and the middle last.
    at = 0
    for run_len in V.RUNS:
        half = (run_len - 1) // 2
        order = ([(at + half + l, l) for l in range(-half, 0)]
                 + [(at + half + l, l) for l in range(half, 0, -1)]
                 + [(at + half, 0)])
        for cell, lateral in order:
            cell_faces(cell, lateral)
        at += run_len

    strip_run = runs[V.RUN[V.STRIP]]
    for cell, x0, second in ((48, STRIP_LEFT, False), (50, STRIP_RIGHT, True)):
        number = V.picture(exe, ids[cell], V.STRIP, 0)
        if number is None:
            continue
        raw = P.picture(pics, strip_run, number)
        col = V.column(exe, ids[cell], second)
        for y in range(V.STRIP_H):
            for i in range(V.STRIP_W):
                frame.put(x0 + i, STRIP_TOP + y, raw[y * strip_run.width + col + i], cell,
                          STAGE["strip"])
    return frame


def check_ledger(exe, world, pics, d, palette, ledger: str, frames_dir: str | None,
                 out_dir: str, poked: bool = False) -> None:
    """Every stop of a probe's ledger against its capture, every pass."""
    import os
    held = json.loads(Path(ledger).read_text())
    readings = held["readings"] if "readings" in held else [held]
    sky_back = {}
    for i, c in enumerate(V.sky_gradient(world, d)):
        sky_back.setdefault(tuple(c), i)
    total_all = exact_all = 0
    for reading in readings:
        shot_path = reading["shot"]
        if frames_dir:
            shot_path = os.path.join(frames_dir, os.path.basename(shot_path))
        if not Path(shot_path).exists():
            print(f"{shot_path}: missing")
            continue
        party = reading["party"]
        # A stop the probe poked draws with a stale pointer's bits; one it
        # walked to, marked so by tools/view_probe.js, draws with its own.
        frame = render(exe, world, pics, d, party, poked or not reading.get("walked"))
        shot = captured(shot_path, palette)
        width, _, rgb = pngutil.read(shot_path)
        scale = width // 320
        cursor = SKY_CURSOR_MAX
        tally = {k: [0, 0, 0] for k in ("floor", "ceiling", "face", "strip", "none")}
        residual = set()
        for y in range(V.VIEW_Y, V.VIEW_Y + V.VIEW_H):
            for x in range(V.VIEW_X, V.VIEW_X + V.VIEW_W):
                drew = frame.screen[y * 320 + x]
                got = shot(x, y)
                if got < 0:
                    at = ((y * scale) * width + x * scale) * 3
                    g = sky_back.get(tuple(rgb[at:at + 3]))
                    if g is not None:
                        got = SKY + (g - cursor)
                stage = ("none", "floor", "ceiling", "face", "strip")[frame.stage[y * 320 + x]]
                if got == drew:
                    tally[stage][0] += 1
                elif drew >= SKY and got == drew - 1:
                    tally[stage][1] += 1
                else:
                    tally[stage][2] += 1
                    residual.add((x, y))
        exact = sum(t[0] for t in tally.values())
        phase = sum(t[1] for t in tally.values())
        wrong = sum(t[2] for t in tally.values())
        total = exact + phase + wrong
        total_all += total
        exact_all += exact + phase
        print(f"{os.path.basename(shot_path)}  party {party['x']},{party['y']} "
              f"{party['facing']:x}: {exact}/{total} exact, {phase} one sky step, {wrong} wrong")
        for k, (e, p_, w) in tally.items():
            if e + p_ + w:
                print(f"  {k:<8} {e + p_}/{e + p_ + w}")
        out = bytearray()
        for y in range(V.VIEW_Y, V.VIEW_Y + V.VIEW_H):
            for x in range(V.VIEW_X, V.VIEW_X + V.VIEW_W):
                out += b"\xff\x00\x00" if (x, y) in residual else bytes(palette[frame.screen[y * 320 + x]])
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        pngutil.write(str(Path(out_dir) / os.path.basename(shot_path)), V.VIEW_W, V.VIEW_H, bytes(out))
    if total_all:
        print(f"all: {exact_all}/{total_all} ({100 * exact_all / total_all:.1f}%)")


# The daylight end of the sky gradient, where the game rests by day, as a
# color index: docs/view.md, "The sky".
SKY_CURSOR_MAX = 0x14D // 3


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
    ap.add_argument("--ledger", help="a probe ledger: draw every pass at each stop")
    ap.add_argument("--frames", help="where the ledger's captures are, if moved")
    ap.add_argument("--out-dir", default="tmp/view-check")
    ap.add_argument("--poked", action="store_true",
                    help="treat every stop as poked, even those the ledger marks walked")
    a = ap.parse_args()

    game = Path(a.game)
    d = SEC.load(game)
    exe = (game / "REGISTER.EXE").read_bytes()
    world = (game / "WORLD.DAT").read_bytes()
    pics = (game / "PICTURES.VGA").read_bytes()
    if a.ledger:
        check_ledger(exe, world, pics, d, tiles.palette(d, PALETTE), a.ledger, a.frames, a.out_dir,
                     a.poked)
        return

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
