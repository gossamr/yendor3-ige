"""The first-person view: which cells it shows, and where each one lands.

The view is 51 map cells drawn as seven rows in front of the party. Image
`0x107E9` copies those cells out of the map window into an eight-byte table at
`DS:0x708E`, in row order. Three passes then walk that table and draw each
entry: `0x10299` the floor, `0x10153` the ceiling, `0x104A8` the walls. All
three call the same blitter at `0x19DC9`, which switches on `DS:0x53C8`.

Every slot's shape on screen is stored, in `WORLD.DAT` section 27, and the
artwork is drawn at final size: a floor picture is a whole 224 x 74 floor in
perspective and a cell copies its own trapezoid out of it. `slots()` reads
those shapes; `FLOOR_BAND` and `width()` are the same geometry as four numbers
and a multiply.

The seven rows run far to near, so drawing them in table order is the painter's
algorithm. Their half widths are 8, 8, 2, 1, 1, 1, 1 cells, which is the 17,
17, 5, 3, 3, 3, 3 the three passes loop over.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import sections as SEC
import tiles

# Cells to a row, far row first, and how far ahead each row is.
RUNS = (17, 17, 5, 3, 3, 3, 3)
DEPTHS = (6, 5, 4, 3, 2, 1, 0)
CELLS = sum(RUNS)
# The middle cell of the last row, which is the one the party stands on, and
# the one the hand-to-hand tables carry.
PARTY_CELL = CELLS - 2

# Which way each facing word points, and which way right is from it. Image
# `0x107E9` holds these as the two strides it walks the map window with, eight
# bytes a cell and 0x270 a row. docs/saves.md has the same four values, and
# 0x4000 is south: the run that starts six cells away at y + 6 walks in to the
# party, so the party is looking down the +y axis.
NORTH, SOUTH, WEST, EAST = 0x8000, 0x4000, 0x2000, 0x1000
FACINGS = {
    NORTH: ((0, -1), (1, 0)),
    SOUTH: ((0, 1), (-1, 0)),
    WEST: ((-1, 0), (0, -1)),
    EAST: ((1, 0), (0, 1)),
}

# The viewport, and where the two halves of it start on the 320 x 200 screen.
# The floor picture is drawn at the second, so a floor slot's own y counts from
# there (image `0x19FC0` adds 0x46) and a ceiling slot's from the first
# (`0x19FDF` adds 8).
VIEW_X, VIEW_Y, VIEW_W, VIEW_H = 8, 8, 224, 136
CEILING_Y, FLOOR_Y = 8, 70

# Where the two planes meet, as a viewport row, and how wide one cell is a row
# away from it. Both halves are drawn in perspective about that line, and one
# cell is four pixels wider for every row: `4 * rows` across, from 4 at the row
# below the horizon to 214 at the near edge, where the viewport's own 224 cuts
# it off. The floor's edges run out from row 61.5 and the ceiling's from 62.5,
# which is the half pixel two integer tables cannot both hold.
HORIZON = 62.0
WIDTH_PER_ROW = 4

# How many rows from the horizon each cell boundary sits at, near to far: the
# face between the party's own cell and the one ahead is 53 rows out, the next
# 42, and the seventh row's far face is the horizon itself.
FLOOR_BAND = (53, 42, 32, 22, 13, 4, 0)
CEILING_BAND = (52, 41, 31, 21, 12, 3, 0)


def width(rows: float) -> int:
    """How wide one cell is that many rows from the horizon, clipped to the
    viewport. The stored slots hold to this on every row."""
    return min(VIEW_W, int(WIDTH_PER_ROW * rows))

# The section holding every slot's shape, and the offsets in it the three
# passes read. Image `0x13088` writes those offsets into `DS:0x546A` upward,
# one per blitter mode.
GEOMETRY = 27
MODE_OFFSET = {1: 0x0386, 2: 0x0BF2, 3: 0x13B6}
FLOOR, CEILING, WALL, STRIP = 1, 2, 3, 6

# Where a terrain record keeps its four view pictures. tools/tiles.py has the
# same record's map tile at +0x0A, which is all twelve bytes accounted for.
TERRAIN_FLOOR, TERRAIN_CEILING, TERRAIN_WALL = 0x00, 0x02, 0x04
TERRAIN_STRIP, TERRAIN_COLUMN = 0x06, 0x08

# The strip is drawn 7 pixels wide and 0x71 rows tall, at the place mode 3's
# own table gives, and the pair of cells either side of the view take the two
# halves of it: image `0x10723` uses the record's column and `0x10764` that
# column plus 7.
STRIP_W, STRIP_H, STRIP_HALF = 7, 0x71, 7

# The picture run each pass draws from, as tools/pictures.py numbers them. A
# pass names its run by putting the run's own offset in the table at
# `DS:0x7B5C` into `DS:0x0FC5`: 0x40, 0x50 and 0x10.
RUN = {FLOOR: 4, CEILING: 5, WALL: 1, STRIP: 6}

# The character panel, under the viewport: four places 58 pixels apart, each a
# 32 x 32 portrait from run 7 and three bars below it. Which picture a place
# draws is the character record's own offset 18, which tools/saves.py reads.
# The bars are health, magic and burden, top to bottom, 38 pixels across and 5
# down, drawn in one flat color over a recess of index 6. docs/view.md, "The
# character panel".
PANEL_PLACES = 4
PANEL_STRIDE = 58
PORTRAIT_RUN = 7
PORTRAIT_X, PORTRAIT_Y = 8, 148
PORTRAIT_W = PORTRAIT_H = 32
BAR_X, BAR_W, BAR_H = 9, 38, 5
BAR_Y = (181, 186, 191)
BAR_EMPTY = 6
BAR_FILL = (89, 202, 134)


def bar_width(now: int, most: int) -> int:
    """How much of one bar is filled, in pixels."""
    if most <= 0 or now <= 0:
        return 0
    return min(BAR_W, BAR_W * now // most)


@dataclass
class Slot:
    """One cell's shape in one pass: a corner and a row per scanline.

    A row is a length in pixels and a step added to the source and the
    destination alike once the row is copied, which walks the trapezoid's left
    edge down. Image `0x1A015` is the loop.
    """

    x: int
    y: int
    rows: tuple[tuple[int, int], ...]

    @property
    def height(self) -> int:
        return len(self.rows)

    def spans(self) -> list[tuple[int, int, int]]:
        """(y, x, length) per scanline, with the left edge walked out."""
        out, x = [], self.x
        for i, (length, step) in enumerate(self.rows):
            out.append((self.y + i, x, length))
            x += step
        return out


def slots(world: bytes, mode: int, directory: SEC.Directory) -> list[Slot | None]:
    """The 51 slots of one pass, None where the pass draws nothing.

    The wall pass keeps its slots in the same section and reads them a column
    at a time rather than a row (image `0x1AA1A`), so its entries are not
    `Slot`s and mode 3 is not accepted here.
    """
    section = directory.sections[GEOMETRY]
    blob = world[section.offset:section.end]
    base = MODE_OFFSET[mode]
    out: list[Slot | None] = []
    for cell in range(CELLS):
        x, y, at = struct.unpack_from("<HHH", blob, base + cell * 6)
        if at == 0:
            out.append(None)
            continue
        rows = []
        while True:
            length, step, _ = struct.unpack_from("<hhh", blob, at)
            if length == 0:
                break
            rows.append((length, step))
            at += 6
        out.append(Slot(x, y, tuple(rows)))
    return out


# The corner-and-list tables the wall, object and monster passes read, by the
# offsets image 0x0F07C writes at DS:0x546A upward and the dispatch at
# 0x19DC9 pairs with each mode: mode 0 and mode 8 share `front`, modes 3 and
# 4 `side`, mode 7 reads `object_wide`, and mode 13 `object_tall`. A monster
# takes mode 10 when its word 96 carries bit 0 and mode 13 otherwise (image
# 0x126A8), so `monster_wide` is the run 3 monster's own table and the tall
# one shares the small object's. Modes 9 and 11 flank mode 10, and 12 and 14
# flank 13: only cell 0x31, the party's own, carries an entry in those four,
# and they are the three places a monster in hand to hand stands. Image
# 0x12B5C seats the first arrival in the middle buffer and pushes the group
# outward as it grows, so a buffer's index is its place and its blitter mode
# is 9 or 12 plus that index.
FACE_TABLES = {"front": 0x0000, "side": 0x13B6, "object_wide": 0x3B76,
               "monster_wide": 0x3DF2, "object_tall": 0x4460,
               "melee_wide_left": 0x3CA8, "melee_wide_right": 0x41D2,
               "melee_tall_left": 0x4316, "melee_tall_right": 0x4858}


def runs(blob: bytes, at: int) -> tuple[list[tuple[int, int, int]], int]:
    """(repeat, draw, skip) records up to a zero word, and where that word is.

    The walkers at 0x1A98E and 0x1AA1A read six bytes at a time and stop at
    a record whose first word is zero, so the terminator is one word and the
    last record's skip sits right before it.
    """
    out = []
    while True:
        # The terminator is one word, and the last list in the section ends on
        # the section's own last two bytes, so the repeat is read before the
        # rest of a record is asked for.
        repeat = struct.unpack_from("<h", blob, at)[0]
        if repeat == 0:
            return out, at
        _, draw, skip = struct.unpack_from("<hhh", blob, at)
        out.append((repeat, draw, skip))
        at += 6


def two_level(blob: bytes, at: int) -> dict:
    """A front or object face's list: image 0x19F39.

    A pointer to the row list, then the column list. A row record draws
    `draw` destination rows from consecutive source rows and skips `skip`
    source rows, `repeat` times; a column record does the same along a row,
    and one column list serves every row.
    """
    rows_at = struct.unpack_from("<H", blob, at)[0]
    cols, _ = runs(blob, at + 2)
    rows, _ = runs(blob, rows_at)
    return {"rows": rows, "cols": cols}


def side_list(blob: bytes, at: int) -> list[dict]:
    """A side face's records: image 0x1A09F for the left, 0x1A121 for the right.

    Each is a column count, a source column step, and a row list shared by
    those columns. A column draws the list down from the picture's top, then
    the source moves on by one column plus the step. After a record the
    destination drops one row on the left and rises one on the right. A
    record whose list is empty only moves the source by its step.
    """
    out = []
    while True:
        count, step, first = struct.unpack_from("<hhh", blob, at)
        if count == 0:
            return out
        if first == 0:
            out.append({"count": 0, "step": step, "rows": []})
            at += 6
            continue
        rows, end = runs(blob, at + 4)
        out.append({"count": count, "step": step, "rows": rows})
        at = end + 2


def faces(world: bytes, table: str, directory: SEC.Directory) -> list[dict | None]:
    """The 51 entries of one face table: a screen corner and its lists, or
    None where the entry is empty. `FACE_TABLES` names the tables."""
    section = directory.sections[GEOMETRY]
    blob = world[section.offset:section.end]
    base = FACE_TABLES[table]
    out: list[dict | None] = []
    for cell in range(CELLS):
        x, y, at = struct.unpack_from("<HHH", blob, base + cell * 6)
        if x == 0 or at == 0:
            out.append(None)
            continue
        shape = {"records": side_list(blob, at)} if table == "side" else two_level(blob, at)
        out.append({"x": x, "y": y, **shape})
    return out


def frustum(x: int, y: int, facing: int) -> list[tuple[int, int]]:
    """The 51 map cells the view shows, in the order the passes draw them."""
    (fx, fy), (rx, ry) = FACINGS[facing]
    out = []
    for run, width in enumerate(RUNS):
        depth, half = DEPTHS[run], (width - 1) // 2
        for lateral in range(-half, half + 1):
            out.append((x + fx * depth + rx * lateral,
                        y + fy * depth + ry * lateral))
    return out


def record(exe: bytes, terrain_id: int) -> int:
    """The DS offset of a terrain id's 12-byte record, by the game's own rule.

    tools/tiles.py states the rule; this repeats the walk because it wants the
    record rather than one field of it.
    """
    family, index = divmod(terrain_id, tiles.FAMILY)
    base = tiles._word(exe, tiles.TERRAIN_TABLE + family * 4)
    last = tiles._word(exe, tiles.TERRAIN_TABLE + family * 4 + 2)
    if index > last:
        return tiles._word(exe, tiles.TERRAIN_TABLE)
    return base + index * tiles.TERRAIN_RECORD


def axis_bit(facing: int, party_ceiling: int) -> int:
    """Bit 0 of every ceiling picture number, and of the sky behind them.

    Image `0x1021D` takes it from the party's own cell where that cell names a
    ceiling, and from the facing otherwise: one drawing for north and south,
    another for east and west.
    """
    if party_ceiling:
        return party_ceiling & 1
    return 0 if facing in (NORTH, SOUTH) else 1


# The sky's 32 colors at palette index 224 are a window on a gradient, and the
# window slides with the clock. The gradient is the head of section 12's third
# 768-byte block; image `0x0EDA0` copies 32 colors from `DS:0x4D62 + [0xD00F]`
# and uploads them, and `docs/view.md` has the slide.
SKY_SECTION, SKY_AT, SKY_COLORS, SKY_WINDOW = 12, 1536, 143, 32
SKY_STEPS, SKY_CURSOR_MAX, SKY_TURNS_AT = 0x71, 0x14D, 1080

# The shade offsets, one per row, far row first. `docs/view.md` has the rule.
LIGHT_FIXED = 0x7A68            # used where DS:0xCEF9 bit 0x2000 is set
LIGHT_BY_CLOCK = 0x7556         # 32-byte records, the seven words at +0x12
LIGHT_RECORD, LIGHT_OFFSETS = 0x20, 0x12
LIGHT_RUNGS_AT, LIGHT_RUNGS, LIGHT_ROWS = 0x7A06, 6, 7
# Which bits of DS:0xCEF7 answer for each rung, brightest first (`0x17971`).
LIGHT_BITS = ((0x200, 0x8), (0x400, 0x10), (0x800, 0x20),
              (0x1000, 0x40), (0x2000, 0x80), (0x4000, 0x100))


def sky_gradient(world: bytes, directory: SEC.Directory) -> list[tuple[int, int, int]]:
    """The colors the sky's window slides along, as 8-bit RGB."""
    at = directory.sections[SKY_SECTION].offset + SKY_AT
    raw = world[at:at + SKY_COLORS * 3]
    return [tuple((v << 2) | (v >> 4) for v in raw[i * 3:i * 3 + 3])
            for i in range(SKY_COLORS)]


def light_schedule(exe: bytes) -> dict:
    """The shade offsets: the fixed set, the clock's records, and the rungs."""
    def words(off, n):
        return [struct.unpack_from("<h", exe, tiles.HEADER + tiles.DGROUP + off + i * 2)[0]
                for i in range(n)]

    records, at = [], LIGHT_BY_CLOCK
    while True:
        row = words(at, 16)
        if row[0] == -1:
            break
        records.append({"from": row[0], "to": row[1],
                        "offsets": words(at + LIGHT_OFFSETS, LIGHT_ROWS)})
        at += LIGHT_RECORD
    rungs = [words(LIGHT_RUNGS_AT + row * 12, LIGHT_RUNGS) for row in range(LIGHT_ROWS)]
    return {"fixed": words(LIGHT_FIXED, LIGHT_ROWS), "by_clock": records,
            "rungs": [[r[i] for r in rungs] for i in range(LIGHT_RUNGS)],
            "bits": [list(b) for b in LIGHT_BITS]}


def picture(exe: bytes, terrain_id: int, mode: int, axis: int) -> int | None:
    """Which picture of the pass's run a cell draws, or None for nothing.

    The floor number carries the axis bit in bit 0 (`0x10308`) and so does the
    ceiling's, which falls back to the axis bit alone where the record names
    no ceiling (`0x101C2`). The wall number is taken whole (`0x1053D`).
    """
    at = record(exe, terrain_id)
    if mode == FLOOR:
        return (tiles._word(exe, at + TERRAIN_FLOOR) & ~1) | axis
    if mode == CEILING:
        held = tiles._word(exe, at + TERRAIN_CEILING)
        return ((held & ~1) | axis) if held else axis
    if mode == STRIP:
        return tiles._word(exe, at + TERRAIN_STRIP) or None
    return tiles._word(exe, at + TERRAIN_WALL) or None


def column(exe: bytes, terrain_id: int, second: bool = False) -> int:
    """Which column of the strip picture a cell draws, 7 pixels wide."""
    at = record(exe, terrain_id)
    return tiles._word(exe, at + TERRAIN_COLUMN) + (STRIP_HALF if second else 0)
