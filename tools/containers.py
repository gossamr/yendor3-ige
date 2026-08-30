#!/usr/bin/env python3
"""Container records, and the two bags that end up sharing one.

A BAG, BOX or BACKPACK holds nothing itself. It carries a *record number* into
section 2 of the save, and that record holds the eight things inside it. The
number lives beside the item id in whichever slot the container sits in, which
is the "state" word [saves.md](../docs/saves.md) describes.

Nothing marks a record as taken. The whole of the bookkeeping is two words in
**roster slot 0**, the party header:

    +430  the next record to hand out      DS:0xD08B
    +432  the head of the free list        DS:0xD08D, chained through record word 0

The allocator at image `0x1600e` pops the free list when it can and otherwise
takes `+430` and increments it. `0x044bf` calls it as a container is put into a
slot, and only when the slot's state word is zero, so a container that already
has a record keeps it as it moves around. Freeing (image `0x051c0`, reached
from DELETE CHARACTER at `0x13ab3` and from the drop at `0x05273`) zeroes the
record and pushes it onto the free list.

Both words are inside the 5,000 bytes of the roster, so they travel with a save
and are restored with it. **A restore that carries the characters but not slot 0
puts the counter behind the world**: the characters keep the record numbers they
were given, the counter goes back to what the source held, and the next
container equipped is handed a record another bag is already using. The two
bags then show the same contents, and freeing either one -- deleting one of the
characters, or dropping one of the bags -- zeroes the record both point at.

`WORLD.DAT`'s roster template ships `+430 = 3`, because SQUIRE and JOSEPHINE
hold records 1 and 2 and record 0 is the "no container" sentinel. Grafting
kept characters into that template without touching slot 0 is exactly the
restore described above, which is why [keep_characters.py](keep_characters.py)
now renumbers as it grafts.

    python tools/containers.py tmp/saves/SAVGAME2          # audit a save
    python tools/containers.py tmp/saves/SAVGAME2 --fix --out tmp/fixed/SAVGAME2
    python tools/containers.py --world game/WORLD.DAT      # audit the template
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import saves as S

# Roster geometry, the same ten 500-byte slots keep_characters.py grafts.
ROSTER_SLOT, ROSTER_SLOTS = S.ROSTER_SLOT, S.ROSTER_SLOTS
ROSTER_BYTES = ROSTER_SLOT * ROSTER_SLOTS

# The allocator's two words, at their offsets in slot 0. DS:0xCEDD is the
# roster, so DS:0xD08B and DS:0xD08D are slot 0 + 430 and + 432.
NEXT_RECORD, FREE_HEAD = 430, 432

# Record 0 is what an unallocated container holds, so it is never handed out.
FIRST_RECORD = 1

# The eleven (id, state) pairs DELETE CHARACTER frees at image 0x13aab: the
# eight panel slots, then the missile, container and hand slots. A container
# can only reach the panel slots and the container slot -- those are the calls
# to 0x044bf -- and the other two are walked here for the same reason the game
# walks them.
SLOT_COUNT = 11
SLOT_OFFSETS = tuple(S.PANEL_AT + 4 * i for i in range(SLOT_COUNT))

CONTAINERS = 2          # the section a record number indexes
ENTRIES = 8             # items to a container
CONTAINER_ITEMS = "BAG", "BOX", "BACKPACK"

# Slot 0 is the party header, not a character. Its 500 bytes hold the position,
# the clock, the purse, the party list and the sky ramp, and the ramp runs from
# +310, straight through the offsets a character keeps items at. A ramp byte of
# 28 beside a zero reads as a BAG, so the header is skipped rather than walked.
CHARACTERS = range(1, ROSTER_SLOTS)

# Slots 6-9 are the characters the game ships. When two containers want the
# same record these hold it and the other one moves, so a repair never
# renumbers SQUIRE's bag out from under him.
STOCK = (6, 7, 8, 9)


@dataclass(frozen=True)
class Reference:
    """One place a container record number is written down."""
    where: str          # "slot 5" for a roster slot, "record 3" for a nesting
    at: int             # byte offset of the state word in the blob it came from
    item: int           # the container item's id
    record: int         # the section 2 record it points at

    def __str__(self) -> str:
        return f"{self.where} -> record {self.record}"


def container_ids(game: str | Path = "game") -> tuple[int, ...]:
    """The item ids whose category word carries the container bit.

    Read rather than listed: `0x2000` of the category word is the bit image
    `0x044bf` tests before it allocates, and three records carry it.
    """
    from sections import load as load_directory
    import items as I

    d = load_directory(Path(game))
    table = I.Items(d)
    ids = tuple(n + 1 for n, rec in enumerate(table.records)
                if I._u16(rec, I.CATEGORY) & I.IS_CONTAINER)
    names = [table.names[n - 1] for n in ids]
    if names != list(CONTAINER_ITEMS):
        raise ValueError(f"the container items are {names}, not {CONTAINER_ITEMS}")
    return ids


def _u16(blob: bytes, at: int) -> int:
    return struct.unpack_from("<H", blob, at)[0]


def _put16(blob: bytearray, at: int, value: int) -> None:
    struct.pack_into("<H", blob, at, value)


def allocator(roster: bytes) -> tuple[int, int]:
    """The next record to hand out, and the head of the free list."""
    return _u16(roster, NEXT_RECORD), _u16(roster, FREE_HEAD)


def roster_references(roster: bytes, ids) -> list[Reference]:
    """Every container record number a character writes down."""
    out = []
    for slot in CHARACTERS:
        base = slot * ROSTER_SLOT
        if not S.name_of(roster[base:base + ROSTER_SLOT]):
            continue
        for off in SLOT_OFFSETS:
            item, record = _u16(roster, base + off), _u16(roster, base + off + 2)
            if item in ids and record:
                out.append(Reference(f"slot {slot}", base + off + 2, item, record))
    return sorted(out, key=lambda r: (r.where not in _stock_names(), r.at))


def _stock_names() -> set[str]:
    return {f"slot {i}" for i in STOCK}


def nested_references(blob: bytes, ids, section) -> list[Reference]:
    """Every container record number written inside another container.

    A bag can be put into a box, and then the box's record holds the bag's
    number in the entry beside its id.
    """
    out = []
    for n in range(section.size // section.record):
        at = section.base + n * section.record
        for e in range(ENTRIES):
            item, record = _u16(blob, at + 2 + 4 * e), _u16(blob, at + 4 + 4 * e)
            if item in ids and record:
                out.append(Reference(f"record {n}", at + 4 + 4 * e, item, record))
    return out


@dataclass
class Audit:
    next_record: int
    free_head: int
    refs: list[Reference]

    @property
    def shared(self) -> dict[int, list[Reference]]:
        """Record numbers more than one container points at."""
        by = {}
        for r in self.refs:
            by.setdefault(r.record, []).append(r)
        return {n: rs for n, rs in sorted(by.items()) if len(rs) > 1}

    @property
    def reissued(self) -> list[Reference]:
        """References the allocator is about to hand out again."""
        return [r for r in self.refs if r.record >= self.next_record]

    @property
    def ok(self) -> bool:
        return not self.shared and not self.reissued

    def report(self) -> list[str]:
        out = [f"next record {self.next_record}, free list "
               + (f"head {self.free_head}" if self.free_head else "empty"),
               f"{len(self.refs)} container(s) referenced"]
        for n, rs in self.shared.items():
            out.append(f"  record {n} is shared by "
                       + ", ".join(r.where for r in rs))
        for r in self.reissued:
            out.append(f"  {r} is at or past the counter, so it will be "
                       "handed out again")
        if self.ok:
            out.append("  no record is shared, and none will be reissued")
        return out


def audit(blob: bytes, ids, section=None) -> Audit:
    """Audit a save (`section` given) or a bare 5,000-byte roster."""
    refs = roster_references(blob[:ROSTER_BYTES], ids)
    if section is not None:
        refs += nested_references(blob, ids, section)
    n, free = allocator(blob)
    return Audit(n, free, refs)


def repair(blob: bytes, ids, section=None,
           passes: int = 8) -> tuple[bytes, list[str]]:
    """Give every container a record of its own, and move the counter past them.

    The first container on a shared record keeps it. Each of the others is
    given a fresh one:

    * a container a **character** holds gets a copy of the contents, because
      that is what the game has been showing the player -- two bags whose
      panels both list the same eight things. Emptying one instead would take
      away items the player can see, and would leave that character's carried
      weight counting contents that are no longer there.
    * a container **inside another container** gets an empty record. A copy
      there would carry the references inside it along too, and a box that had
      come to hold itself would never come apart.

    The free list is dropped. Its head is a record number too, and a list built
    while the counter was behind can name a record a bag is still holding.
    Records are 34 bytes and there are 1,296 of them, so leaking a few costs
    nothing.
    """
    out = bytearray(blob)
    was, free = allocator(blob)
    notes = []
    for _ in range(passes):
        a = audit(bytes(out), ids, section)
        fresh = max([a.next_record, FIRST_RECORD]
                    + [r.record + 1 for r in a.refs])
        moved = False
        for record, rs in a.shared.items():
            for r in rs[1:]:
                _put16(out, r.at, fresh)
                notes.append(f"{r.where}: record {record} -> {fresh}"
                             + _fill(out, section, record, fresh, r))
                fresh, moved = fresh + 1, True
        _put16(out, NEXT_RECORD, fresh)
        _put16(out, FREE_HEAD, 0)
        if not moved:
            break
    else:
        raise ValueError(f"still sharing a record after {passes} passes")

    now = allocator(bytes(out))[0]
    if now != was:
        notes.append(f"next record {was} -> {now}")
    if free:
        notes.append(f"free list head {free} -> empty")
    return bytes(out), notes


def _fill(out: bytearray, section, record: int, fresh: int,
          ref: Reference) -> str:
    """Fill the record `ref` has just been pointed at, and say what went in."""
    if section is None:
        return ""
    dst = section.base + fresh * section.record
    if ref.where.startswith("slot "):
        src = section.base + record * section.record
        out[dst:dst + section.record] = out[src:src + section.record]
        return " with a copy of its contents"
    out[dst:dst + section.record] = bytes(section.record)
    return " and emptied"


def repair_template(world: bytes, ids, roster_at: int) -> tuple[bytes, list[str]]:
    """The same repair on `WORLD.DAT`'s roster template.

    NEW GAME rebuilds section 2 from zeros, so every container in the template
    starts empty and there are no contents to copy: renumbering is the whole of
    it.
    """
    out = bytearray(world)
    roster = bytes(out[roster_at:roster_at + ROSTER_BYTES])
    fixed, notes = repair(roster, ids)
    out[roster_at:roster_at + ROSTER_BYTES] = fixed
    return bytes(out), notes


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("save", nargs="?", help="a CURGAME or SAVGAMEn file")
    ap.add_argument("--world", help="a WORLD.DAT, to audit its roster template")
    ap.add_argument("--game", default="game", help="where the item table is")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--out", help="where to write the repaired file")
    a = ap.parse_args()

    ids = container_ids(a.game)
    if a.world:
        import keep_characters as K
        blob = Path(a.world).read_bytes()
        roster = blob[K.ROSTER:K.ROSTER + ROSTER_BYTES]
        print(f"{a.world} roster template:")
        for line in audit(roster, ids).report():
            print(f"  {line}")
        if a.fix:
            fixed, notes = repair_template(blob, ids, K.ROSTER)
    elif a.save:
        blob = Path(a.save).read_bytes()
        section = S.sections()[CONTAINERS]
        print(f"{a.save}:")
        for line in audit(blob, ids, section).report():
            print(f"  {line}")
        if a.fix:
            fixed, notes = repair(blob, ids, section)
    else:
        ap.error("give a save file, or --world")

    if a.fix:
        if not a.out:
            ap.error("--fix needs --out")
        for n in notes:
            print(f"  {n}")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_bytes(fixed)
        print(f"wrote {a.out}" if notes else f"nothing to repair; wrote {a.out}")
    sys.exit(0)
