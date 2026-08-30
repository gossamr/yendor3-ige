"""Where a door goes, and what else stands on a cell.

The 140 map slots are one 800x168 grid (`docs/map.md`), and the party's place
in it is the pair `DS:0xCF75`, `DS:0xCF77`. A door writes both, so following
what writes them reaches the whole network:

* **Section 28** is the cell-event table: 26,472 bytes, read whole into the
  buffer whose segment is `DS:0xFF7`, and looked up at image `0x10D57`. It is
  a **column index** of uint16 offsets, one per world column from x = 40, each
  the offset of that column's list of six-byte records, sorted by y and
  terminated by `0xFFFF`:

      +0  uint16  y
      +2  uint16  kind, one bit
      +4  uint16  argument, whose meaning follows the kind

  The offsets are from the section's own start, so the table reads straight
  out of the file with no fixing up.

* **`DS:0xBA95`** is the destination table the door kind indexes, 1-based:
  139 eighteen-byte records, ending exactly where the gate table at
  `DS:0xC45B` begins.

      +0x00 uint16  destination x        +0x0A uint16  -> DS:0xCF31
      +0x02 uint16  destination y        +0x0C uint16  -> DS:0xCF33
      +0x04 uint16  facing               +0x0E uint16  gate mask
      +0x06 uint16  sound                +0x10 uint16  flags, bit 0 -> DS:0xCF3F
      +0x08 uint16  -> DS:0xCF2F

  Image `0x05512` reads it: it copies x, y and facing into the party's own
  words, rebuilds the map window and redraws. A record whose `+0x0E` carries
  either of the top two bits is gated: image `0x055A3` walks the 22-byte
  records at `DS:0xC45B` for the door's own number and tests the flag word one
  of them points at, so the door only opens once the game says so.

Why searching never found it: a door does not record its source, and its
destination is a pair of *world* coordinates rather than a slot number or an
(area, level) pair. The table is also addressed by column, so a door's two
words are nowhere near either endpoint's map data.
"""

from __future__ import annotations

import struct

import sections as S
from registry import map_registry

CELL_EVENTS = 28
FIRST_COLUMN = 40           # the index starts at world x = 40; areas 0 and 6
COLUMNS = 720               # hold no map, and neither does level 0 or 19
RECORD = 6
END = 0xFFFF

# The kinds, one bit each, as image 0x10BC8 and image 0x0044A6 test them.
# `door` is the one this module is for; the rest are named because knowing
# which records are not doors is what makes the count trustworthy.
KINDS = {
    0x8000: "treasure",     # image 0x0252E: a 26-byte record, gated on a
                            # CURGAME bit, which is what "already looted" means
    0x4000: "container",    # image 0x025CB
    0x2000: "door",         # argument indexes DESTINATIONS
    0x1000: "person",       # argument is the record's own index in the NPC
                            # table at DS:0x0EC8, not 1-based unlike the
                            # door's; records 0 and 140 stand nowhere
    0x0800: "monster",     # a monster; the argument is its spawn id,
                            # which `tools/spawns.py` resolves to a
                            # monster through WORLD.DAT section 30
    0x0400: "script",       # a hand-written handler, six in all
}

DGROUP = 0x21DB0
DESTINATIONS = 0xBA95
DESTINATION_RECORD = 18
DESTINATION_COUNT = 139
GATE_TABLE = 0xC45B         # where the destination table ends
GATED = 0xC000              # +0x0E: the door is gated on a flag

CELLS, BANDS = 40, 24
FACING = {0x8000: "north", 0x4000: "south", 0x2000: "west", 0x1000: "east"}


def _u16(blob: bytes, at: int) -> int:
    return struct.unpack_from("<H", blob, at)[0]


def events(d: S.Directory) -> list[dict]:
    """Every cell the game has something to say about, in column order."""
    base = d.sections[CELL_EVENTS].offset
    out = []
    for column in range(COLUMNS):
        offset = _u16(d.world, base + column * 2)
        if not offset:
            continue
        at = base + offset
        while (y := _u16(d.world, at)) != END:
            kind, arg = _u16(d.world, at + 2), _u16(d.world, at + 4)
            out.append({"x": FIRST_COLUMN + column, "y": y,
                        "kind": KINDS.get(kind, f"0x{kind:04x}"), "arg": arg})
            at += RECORD
    return out


def destinations(exe: bytes) -> list[dict]:
    """The 139 places a door can put the party."""
    at = DGROUP + DESTINATIONS
    assert DESTINATIONS + DESTINATION_COUNT * DESTINATION_RECORD == GATE_TABLE, \
        "the destination table must end where the gate table begins"
    out = []
    for n in range(DESTINATION_COUNT):
        r = struct.unpack_from("<9H", exe, at + n * DESTINATION_RECORD)
        out.append({"x": r[0], "y": r[1], "facing": FACING.get(r[2]),
                    "sound": r[3] or None, "gated": bool(r[7] & GATED)})
    return out


def page_of(x: int, y: int) -> tuple[int, int]:
    """The (area, level) slot a world cell falls in."""
    return y // BANDS, x // CELLS


def doors(d: S.Directory) -> list[dict]:
    """Every door, as the cell it is on and the cell it puts you on."""
    table = destinations(d.exe)
    out = []
    for e in events(d):
        if e["kind"] != "door":
            continue
        to = table[e["arg"] - 1]
        out.append({"x": e["x"], "y": e["y"],
                    "to_x": to["x"], "to_y": to["y"],
                    "facing": to["facing"], "gated": to["gated"]})
    return out


def named(d: S.Directory, pages: list[dict]) -> list[dict]:
    """The doors, with both ends named, for the panel and for eyeballing."""
    titles = {(p["area"], p["level"]): p["title"] for p in pages}
    fallback = map_registry(d.world)

    def name(x: int, y: int) -> str | None:
        slot = page_of(x, y)
        return titles.get(slot) or fallback.get(slot)

    out = []
    for door in doors(d):
        out.append({
            **door,
            "from": name(door["x"], door["y"]),
            "to": name(door["to_x"], door["to_y"]),
        })
    return out


# A door's own cell may be the marker's cell or the cell in front of it: the
# gold square is drawn on the doorway, and some doors trigger from the square
# the party steps onto to reach it.
NEIGHBORS = ((0, 0), (0, -1), (0, 1), (-1, 0), (1, 0))


def by_label(d: S.Directory, pages: list[dict], marks: dict) -> dict:
    """`"<map>|<legend line>" -> the map that line leads to`.

    This is what the panel looks a legend line up in. Only doors that carry a
    legend line can be keyed, and a line that two doors on the same page share
    is dropped unless they agree: KEEP's two SHOP ENTRANCE doors do agree,
    and a pair that did not would be a key with no single answer.
    """
    at = {}
    for title, rows in marks.items():
        page = next((p for p in pages if p["title"] == title), None)
        if page is None:
            continue
        for m in rows:
            at[(page["level"] * CELLS + m["cell"],
                page["area"] * BANDS + m["row"])] = (title, m["label"])

    out: dict[str, str] = {}
    clashes: set[str] = set()
    for door in named(d, pages):
        if not door["to"]:
            continue
        for dx, dy in NEIGHBORS:
            hit = at.get((door["x"] + dx, door["y"] + dy))
            if hit:
                break
        else:
            continue
        key = f"{hit[0]}|{hit[1]}"
        if key in out and out[key] != door["to"]:
            clashes.add(key)
        out[key] = door["to"]
    for key in clashes:
        del out[key]
    return out
