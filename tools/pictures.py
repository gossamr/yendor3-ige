"""Artwork in `PICTURES.VGA`, and the monster pictures in particular.

**The file is ten runs of fixed-size pictures.** A table of ten sixteen-byte
entries in the executable's data segment, at `DS:0x7B5C`, says where each run
starts and what shape its pictures are:

    +0x04  bytes in one picture, always width x height
    +0x08  width in pixels
    +0x0A  height in pixels
    +0x0C  where the run starts in the file, as a 32-bit byte offset

A run ends where the next begins, and the last ends at the end of the file, so
the count of each run follows from the table:

      run  pixels     pictures  what it holds
        0  318 x 198        23
        1  210 x 105       156
        2  140 x 155       270  monsters drawn tall, and scenery
        3  190 x 110       238  monsters drawn wide, and spell effects
        4  224 x  74        28
        5  224 x  62        14
        6   56 x 136        70
        7   32 x  32       180
        8   16 x  16       340
        9    8 x   8       576  the map's tiles; see tools/tiles.py

The game reads a picture by seeking to `base + n * size` and reading `size`
bytes (image 0x3997 does the read, 0x39ED the seek), so a run is a flat array
with no per-picture header.

**A pixel is one palette index, and 0xFF is transparent.** The high nibble
picks a twelve-color ramp and the low nibble the shade within it, which is
what makes recoloring a monster possible: substituting one high nibble for
another moves every pixel of that ramp to a different one at the same shade.

**A monster's pictures.** The record's offset 26 is the first of ten
consecutive pictures, and bit 0 of the word at offset 96 says which run they
are in: set for run 3, clear for run 2 (image 0x10352). Within the ten, the
draw loop cycles 0..5 while the monster stands and walks, shows 6 when it
attacks (image 0x80B0) and 9 when it dies (image 0x10397).

Offsets 64..69 hold up to six recolor pairs, read when bit 2 of word 96 is
set (image 0x10337); each byte is `from << 4 | to`, and the list stops at the
first zero byte.

Bit 15 of the word at offset 98 sends the picture through a different blit
(image 0x10378), which draws every pixel in ramp 0, the gray one, whatever
ramp the picture stores. Three monsters carry it: GHOST, SPECTRE and PHASE
TITAN, the last of which shares the TITAN artwork and is told apart by nothing
else.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER = 0x4000         # the MZ load image starts here in the file
DGROUP = 0x1DDB0        # image offset; tools/levels.py derives it

TABLE = 0x7B5C          # DS offset of the run table
ENTRY = 16              # bytes an entry
COUNT = 10              # entries

SIZE, WIDTH, HEIGHT, BASE = 0x04, 0x08, 0x0A, 0x0C

TRANSPARENT = 0xFF

TALL, WIDE = 2, 3       # the two runs monsters are drawn from
WIDE_BIT = (96, 0)      # record word 96, bit 0: the monster is drawn wide
RECOLOR_BIT = (96, 2)  # record word 96, bit 2: the recolor list applies
GREY_BIT = (98, 15)     # record word 98, bit 15: drawn in ramp 0 throughout

RAMP = 0x10             # colors a ramp; the high nibble of a pixel picks one
GREY_RAMP = 0

SPRITE = 26             # record offset of the first of the ten pictures
FRAMES = 10
ATTACK_FRAME, DEATH_FRAME = 6, 9


@dataclass(frozen=True)
class Run:
    """One of the ten runs: `count` pictures of `width` x `height` bytes."""

    index: int
    width: int
    height: int
    size: int
    base: int
    count: int

    def at(self, n: int) -> int:
        """Where picture `n` starts in the file."""
        if not 0 <= n < self.count:
            raise IndexError(f"run {self.index} holds {self.count} pictures, not {n}")
        return self.base + n * self.size


def _word(exe: bytes, ds_offset: int) -> int:
    return struct.unpack_from("<H", exe, HEADER + DGROUP + ds_offset)[0]


def read_runs(exe: bytes, pics_size: int) -> list[Run]:
    """The ten runs, with each one's count taken from where the next starts."""
    raw = []
    for i in range(COUNT):
        at = TABLE + i * ENTRY
        size, w, h = (_word(exe, at + f) for f in (SIZE, WIDTH, HEIGHT))
        base = _word(exe, at + BASE) | (_word(exe, at + BASE + 2) << 16)
        assert w * h == size, f"run {i}: {w}x{h} is not {size} bytes"
        raw.append((w, h, size, base))
    ends = [r[3] for r in raw[1:]] + [pics_size]
    runs = []
    for i, ((w, h, size, base), end) in enumerate(zip(raw, ends)):
        span = end - base
        assert span > 0 and span % size == 0, \
            f"run {i}: {span} bytes is not a whole number of {size}-byte pictures"
        runs.append(Run(i, w, h, size, base, span // size))
    return runs


def picture(pics: bytes, run: Run, n: int) -> bytes:
    """Picture `n` of a run, as `width * height` palette indices."""
    at = run.at(n)
    return pics[at:at + run.size]


def recoloured(raw: bytes, swaps: dict[int, int]) -> bytes:
    """The picture with each named ramp moved to another, shade preserved."""
    if not swaps:
        return raw
    table = bytes((swaps.get(v >> 4, v >> 4) << 4) | (v & 0xF)
                  if v != TRANSPARENT else TRANSPARENT for v in range(256))
    return raw.translate(table)


def greyed(raw: bytes) -> bytes:
    """The picture with every pixel moved to the gray ramp, shade preserved."""
    return recoloured(raw, {r: GREY_RAMP for r in range(RAMP)})


def bounds(raw: bytes, width: int) -> tuple[int, int, int, int]:
    """The box that holds every opaque pixel, as (left, top, right, bottom).

    Right and bottom are exclusive. A picture with no opaque pixel at all has
    no box, and raises.
    """
    rows = [(y, r) for y, r in enumerate(
        raw[i:i + width] for i in range(0, len(raw), width))
        if r.count(TRANSPARENT) < width]
    if not rows:
        raise ValueError("the picture is entirely transparent")
    left = min(next(x for x, v in enumerate(r) if v != TRANSPARENT) for _, r in rows)
    right = max(width - next(x for x, v in enumerate(reversed(r)) if v != TRANSPARENT)
                for _, r in rows)
    return left, rows[0][0], right, rows[-1][0] + 1


def monster_run(runs: list[Run], word96: int) -> Run:
    """Which run a monster is drawn from."""
    return runs[WIDE if word96 >> WIDE_BIT[1] & 1 else TALL]


def monster(pics: bytes, runs: list[Run], sprite: int, word96: int,
             word98: int, swaps: dict[int, int],
             frame: int = 0) -> tuple[Run, bytes]:
    """One of a monster's ten pictures, drawn the way the game draws it."""
    run = monster_run(runs, word96)
    raw = recoloured(picture(pics, run, sprite + frame), swaps)
    return run, greyed(raw) if word98 >> GREY_BIT[1] & 1 else raw
