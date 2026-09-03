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
