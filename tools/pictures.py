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

Bit 15 of the word at offset 98 puts 6 in DS:0x0E28 (image 0x10378), and the
blitter's copy loops then rebuild every pixel as the *destination* pixel's own
ramp with the source pixel's shade (images 0x1A9C5 and 0x1AA55). Three
monsters carry it, GHOST, SPECTRE and PHASE TITAN, and they are drawn
see-through. Over a ramp 0 ground the result is ramp 0 throughout, which is
what the clue book's own page shows and what `grayed` reproduces.
"""

from __future__ import annotations

from collections.abc import Sequence

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
GRAY_BIT = (98, 15)     # record word 98, bit 15: the pixel takes the ground's ramp

RAMP = 0x10             # colors a ramp; the high nibble of a pixel picks one
GRAY_RAMP = 0

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


def recolored(raw: bytes, swaps: dict[int, int]) -> bytes:
    """The picture with each named ramp moved to another, shade preserved."""
    if not swaps:
        return raw
    table = bytes((swaps.get(v >> 4, v >> 4) << 4) | (v & 0xF)
                  if v != TRANSPARENT else TRANSPARENT for v in range(256))
    return raw.translate(table)


def grayed(raw: bytes) -> bytes:
    """The picture with every pixel moved to the gray ramp, shade preserved.

    What the blitter does with word 98 bit 15 is take the destination pixel's
    ramp rather than ramp 0, so this is that blit over a ramp 0 ground. That
    is the clue book's page, and it is what a still of the monster wants;
    docs/pictures.md, "Recoloring, and the blend", has the general case.
    """
    return recolored(raw, {r: GRAY_RAMP for r in range(RAMP)})


# How thick a border to read the ground's own ramp off. Two pixels is enough
# on every picture this is used for and narrow enough that a figure reaching
# the frame's edge would still not outvote the ground.
GROUND_BORDER = 2


def ground_ramp(raw: bytes, width: int, border: int = GROUND_BORDER) -> int:
    """The ramp that fills the frame's own border, which is what is behind."""
    height = len(raw) // width
    edge = [raw[y * width + x] >> 4
            for y in range(height) for x in range(width)
            if x < border or x >= width - border
            or y < border or y >= height - border]
    return max(set(edge), key=edge.count)


def without_ground(raw: bytes, width: int, alike: Sequence[bytes] = ()) -> bytes:
    """The picture with the ground behind it made transparent.

    Some artwork is a whole panel rather than a sprite: the eighteen bodies
    the paper doll is built on are 56 by 136 with no transparent pixel at all,
    the figure standing in the stone alcove the game's own character screen
    shows ([../docs/pictures.md](../docs/pictures.md)). A panel redrawn by
    something other than the game wants the figure without the alcove.

    **A ramp test alone is not enough.** The ground is one whole ramp per
    picture, but a figure may wear that ramp too: body 6's clothing is the
    ground's own ramp and a plain test takes 312 pixels of it away. So the
    ground is taken as the pixels of that ramp a flood from the frame's border
    can reach, which leaves a figure whole.

    **The flood alone is not enough either.** It is walled out of the pockets
    the figure encloses, between a forearm and a hip, and those show as stone
    behind an armor that does not fill them, though a robe covers them. They
    are 15 of the 7,616 on every male body and 36 on every female one.

    `alike` closes that: the other pictures drawn over the same ground. A
    pixel of the ground's ramp that the flood could not reach and that carries
    the same index in every one of them is the ground, since what the figures
    have in common behind them is what they stand on. It tells the two cases
    apart exactly. Of body 6's 312, fifteen are shared by the nine of its sex
    and go, and the 297 of its clothing stay.
    """
    height = len(raw) // width
    ramp = ground_ramp(raw, width)
    out = bytearray(raw)
    seen = bytearray(len(raw))
    stack: list[int] = []

    def reach(at: int) -> None:
        if not seen[at] and raw[at] >> 4 == ramp:
            seen[at] = 1
            stack.append(at)

    for x in range(width):
        reach(x)
        reach((height - 1) * width + x)
    for y in range(height):
        reach(y * width)
        reach(y * width + width - 1)
    while stack:
        at = stack.pop()
        out[at] = TRANSPARENT
        x, y = at % width, at // width
        if x:              reach(at - 1)
        if x < width - 1:  reach(at + 1)
        if y:              reach(at - width)
        if y < height - 1: reach(at + width)
    for at in range(len(out)):
        if out[at] == TRANSPARENT or out[at] >> 4 != ramp:
            continue
        if alike and all(other[at] == out[at] for other in alike):
            out[at] = TRANSPARENT
    return bytes(out)


def without_plate(raw: bytes, width: int, plates: Sequence[bytes],
                  ramp: int | None = None) -> bytes:
    """A sprite with the panel it was drawn over made transparent.

    The paper doll's head pieces are sprites with a hole in them: a helmet has
    to cover the hair the body underneath is drawn with, so the artist drew it
    straight onto the plate, and what is not helmet is the plate showing
    through. That is exact rather than approximate. Of the 447 opaque pixels
    of LEATHER HELMET's male picture, 363 are the same index as the body's own
    at the same place, and they are the whole of what should not be drawn: 341
    of the alcove's stone and 22 of the neck and shoulders the figure is
    outlined with.

    `plates` is the body's own pixels under the piece, taken at the corner the
    slot owns, one per body of the piece's own sex. **Which of the nine it was
    drawn over is not recorded, so the subtraction they agree on is it.** The
    nine differ under a helmet, each having its own face and hair, and a body
    whose hair happens to share a color with the helmet takes pixels out of
    the helmet that the rest keep: over the leather helmet five of the nine
    male plates leave the same 84 pixels and the other four leave 74 to 83,
    and four of the female ones leave the same 99 while the rest leave 70 to
    93. Taking each plate in turn and keeping the answer most of them give
    lands on the piece both times.

    A per-pixel vote does not: it blends nine plates into one that no body
    ever stood on, and takes 80 and 83.

    **The plate is not the whole of it on a woman.** A female piece carries
    stone the plate does not account for, two blobs where the hair of a wider
    head would fall, which the artist painted in by hand to erase it: 27 such
    pixels on the leather helmet and 51 on the dragon skin one, and no female
    body has stone there for the subtraction to match.

    `ramp` is the stone's own, and what is left of it goes by a flood from
    outside rather than by the ramp alone. **A helmet may be drawn in the
    stone's ramp**: the dragon skin helm's horns are filled with it, and a
    plain test empties them. The hand-painted blobs stand against the outside
    and the horn fill is walled in by the helmet's own outline, so a flood
    from the transparent pixels takes the one and leaves the other.

    A body piece takes no `ramp`, and the subtraction alone is the whole of
    it. **A garment may be drawn in the stone's ramp against the outside**:
    CLOTHES' male tunic is, and the flood empties it, 700 pixels of a 1127
    pixel picture. What a body piece carries is the plate over the shoulders
    a hood is cut out of, 371 pixels on ROBES' female picture, and the
    subtraction reaches all of it.
    """
    answers = [_minus_plate(raw, width, plate, ramp) for plate in plates]
    return max(set(answers), key=answers.count)


def _minus_plate(raw: bytes, width: int, plate: bytes, ramp: int | None) -> bytes:
    out = bytearray(TRANSPARENT if v == plate[at] else v
                    for at, v in enumerate(raw))
    if ramp is None:
        return bytes(out)
    height = len(out) // width
    stack = [at for at in range(len(out)) if out[at] == TRANSPARENT]
    seen = bytearray(len(out))
    for at in stack:
        seen[at] = 1
    while stack:
        at = stack.pop()
        x, y = at % width, at // width
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            to = ny * width + nx
            if seen[to] or out[to] >> 4 != ramp:
                continue
            seen[to] = 1
            out[to] = TRANSPARENT
            stack.append(to)
    return bytes(out)


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
    raw = recolored(picture(pics, run, sprite + frame), swaps)
    return run, grayed(raw) if word98 >> GRAY_BIT[1] & 1 else raw
