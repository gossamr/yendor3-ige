"""Map tile artwork, read out of the game's own files.

Two things here are settled, and one is not.

**The palette is in `WORLD.DAT`.** Section 12 is 5,376 bytes: seven 768-byte
VGA palettes of 6-bit DAC values, and the first is the one the map screen draws
with. Earlier notes recorded the palette as absent from all three files, having
looked for it beside the tile bank in `PICTURES.VGA`; it is nowhere near it.
Decoding a located tile with this palette reproduces the game's own pixels
exactly, which is the proof.

**The tile bank is the tail of `PICTURES.VGA`**, a flat array of 64-byte
tiles, 8x8 palette indices each, aligned to 20 mod 64. The map's own artwork
sits in roughly its last 600 tiles.

**What a cell draws.** Its four bytes are `(uint16 terrain, uint16 object)`.
The terrain word picks a tile through `TERRAIN` below, but only where the
cell's bit in the table at `0x3C4F02` is set; where it is clear the cell draws
`EMPTY`, whatever its id. A non-zero object word picks a tile through `OBJECT`,
composited over the terrain: its `0xff` pixels leave the terrain showing, and
an object with no transparent pixel replaces the cell outright.

**Which tile an id draws is read out of `REGISTER.EXE`.** An id is split by a
hundred, as `family = id / 100` and `index = id % 100`, which is why the ids real
maps use fall in 0..33, 100..103, 200..208 and 300..340. Each family has a
`(base, last index)` descriptor, and the base points at an array of records
holding, among other things, the picture number:

    terrain   descriptors at DS:0x0002, records 12 bytes, picture at +0x0A
    object    descriptors at DS:0xC8E7, records 10 bytes, picture at +0x08

An index past the family's last falls back to the first record of the first
family, which is what every id no map uses draws. An object whose picture is
zero draws nothing.

The routines are at image `0x0BC98` (terrain) and `0x0BCDB` (object); the map
renderer calls them at `0x194F5`, one after the other, taking `[si]` as the
cell's terrain and `[si+2]` as its object.
"""

from __future__ import annotations

import struct

import sections as S

HEADER = 0x4000

PALETTES = 12           # section index: seven 768-byte VGA palettes
PALETTE_BYTES = 768
MAP_PALETTE = 0         # the one the map screen draws with

BANK_ALIGN = 20         # the bank starts here and runs in 64-byte tiles
TILE_BYTES = 64
TILE = 8

# The map's artwork, as offsets from the first tile of the run it sits in.
BLOCK = 268503

EMPTY = 19              # what a cell draws where its bit is clear

# The lookup, in DGROUP. See the note above for how the game reads it.
FAMILY = 100
DGROUP = 0x1DDB0        # image offset; tools/levels.py derives it
TERRAIN_TABLE, TERRAIN_RECORD, TERRAIN_PICTURE = 0x0002, 12, 0x0A
OBJECT_TABLE, OBJECT_RECORD, OBJECT_PICTURE = 0xC8E7, 10, 0x08

# Indices 220-223 hold a fire ramp the game rotates through those four slots,
# so a still of the map shows one phase of it. The palette as stored holds the
# ramp at rest, whose brightest color is not one of the four.
CYCLE = range(220, 224)
FIRE = ((207, 93, 0), (223, 146, 36), (239, 195, 73), (255, 243, 69))
# What the stored palette holds at the last of those four indices: the ramp at
# rest, which is not one of the colors the cycle runs through.
FIRE_AT_REST = (255, 243, 109)


# One bit a cell: set where the cell draws its terrain, clear where it draws
# EMPTY. 5 bytes x 20 levels x 24 bands to an area, bands before levels, and
# the eight bits of a byte high to low across the row.
DRAWN = 0x3C4F02
AREA_BITS = 2400


def _word(exe: bytes, ds_offset: int) -> int:
    return struct.unpack_from("<H", exe, HEADER + DGROUP + ds_offset)[0]


def picture(exe: bytes, tile_id: int, table: int, record: int, field: int) -> int:
    """The picture an id draws, by the game's own rule.

    `family = id / 100` picks a `(base, last index)` descriptor; `index` past
    that last falls back to the first family's first record.
    """
    family, index = divmod(tile_id, FAMILY)
    base = _word(exe, table + family * 4)
    last = _word(exe, table + family * 4 + 2)
    at = _word(exe, table) if index > last else base + index * record
    return _word(exe, at + field)


def terrain(exe: bytes, tile_id: int) -> int:
    return picture(exe, tile_id, TERRAIN_TABLE, TERRAIN_RECORD, TERRAIN_PICTURE)


def obj(exe: bytes, object_id: int) -> int:
    """The object's picture, or 0 where it draws nothing."""
    return picture(exe, object_id, OBJECT_TABLE, OBJECT_RECORD, OBJECT_PICTURE)


def palette(d: S.Directory, which: int = MAP_PALETTE) -> list[bytes]:
    """One of the seven palettes, as 256 RGB triples.

    Stored as 6-bit DAC values; a VGA shows them as `(v << 2) | (v >> 4)`,
    which is what the game's own frames are drawn with.
    """
    world = d.world
    base = d.sections[PALETTES].offset + which * PALETTE_BYTES
    return [bytes(((world[base + 3 * i + c] << 2) | (world[base + 3 * i + c] >> 4))
                  for c in range(3))
            for i in range(256)]


def count(pics: bytes) -> int:
    """How many whole tiles the bank holds. Valid numbers are 0..count-1."""
    return (len(pics) - BANK_ALIGN) // TILE_BYTES


def tile(pics: bytes, n: int) -> bytes:
    """The 64 palette indices of bank tile `n`."""
    at = BANK_ALIGN + n * TILE_BYTES
    return pics[at:at + TILE_BYTES]


def render(pics: bytes, pal: list[bytes], n: int) -> bytes:
    """Bank tile `n` as 8x8 RGB, 192 bytes."""
    return b"".join(pal[v] for v in tile(pics, n))


def index(pics: bytes, pal: list[bytes], lo: int = 0, hi: int | None = None) -> dict:
    """Rendering -> the bank tiles that produce it.

    Several tiles can render identically, which does not matter for drawing --
    the pixels are what is wanted, not the tile's number.
    """
    out: dict[bytes, list[int]] = {}
    for n in range(lo, count(pics) if hi is None else hi):
        out.setdefault(render(pics, pal, n), []).append(n)
    return out


def locate(pics: bytes, pal: list[bytes], block: bytes) -> list[int]:
    """Which bank tiles draw this 8x8 RGB block."""
    return index(pics, pal).get(block, [])


def drawn(world: bytes, area: int, level: int, band: int, cell: int) -> int:
    """Does this cell draw its terrain, or the empty tile?"""
    at = DRAWN + area * AREA_BITS + band * 100 + level * 5 + cell // 8
    return (world[at] >> (7 - cell % 8)) & 1


def cycled(pal: list[bytes], phase: int) -> list[bytes]:
    """The palette with the fire ramp rotated to one of its four phases."""
    out = list(pal)
    for k, i in enumerate(CYCLE):
        out[i] = bytes(FIRE[(k + phase) % 4])
    return out


def cell(pics: bytes, pal: list[bytes], exe: bytes, terrain_id: int,
         object_id: int, is_drawn: int) -> bytes:
    """One cell as 8x8 RGB: its terrain, with any object composited over it."""
    n = EMPTY if not is_drawn else terrain(exe, terrain_id)
    out = bytearray(render(pics, pal, BLOCK + n))
    sprite = obj(exe, object_id) if object_id else 0
    if sprite:
        raw = tile(pics, BLOCK + sprite)
        for i in range(TILE_BYTES):
            if raw[i] != 0xFF:
                out[i * 3:i * 3 + 3] = pal[raw[i]]
    return bytes(out)
