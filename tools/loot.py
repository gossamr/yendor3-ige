"""What a cell holds: the world's containers, and its locked passages.

Section 28 gives a cell one six-byte record per thing standing on it
([map.md](../docs/map.md)). Two of its six kinds are read here.

* **`0x8000`** is a container: a chest, a barrel, an urn, whatever the cell's
  object id draws. Its argument is a **bundle**, 1-based, into `WORLD.DAT`
  section 10. A bundle is 26 bytes: a lock word, a pick-and-trap word, eight
  item ids, and three counts for the three items that stack. Image `0x0252E`
  loads one, and image `0x02881` walks the eight.

* **`0x4000`** is a lock standing on the cell with nothing behind it. Its
  argument is 1-based into a second table, 71 records of four bytes, which is
  the head of section 11. Image `0x025CB` loads one: `(arg - 1) * 4` past
  `26 * [DS:0x545E]`, and `DS:0x545E` is written once with 1,000 at image
  `0x0F070`, which is section 10's own record count. So the two tables are
  read out of one buffer and the second begins where the first ends.

A lock record is a bundle's first two words and nothing else, so both kinds
answer the same reader. What differs is what is behind the lock: a bundle has
eight places, a lock has the cell.

**Which bank records that it has been dealt with** follows the kind. A
container's bundle takes a bit in section 3's bank 0 and one bit per item in
section 4; a lock takes a bit in bank 1 and nothing else
([saves.md](../docs/saves.md)).

    python tools/loot.py                    # a summary of both tables
    python tools/loot.py --containers       # every container, by map
    python tools/loot.py --locks            # every lock, by map
"""

from __future__ import annotations

import argparse
import struct

import sections as S
from links import CELLS, events
from registry import map_registry

BUNDLES = 10                # the section a container's argument indexes
BUNDLE_RECORD = 26
BUNDLE_COUNT = 1000         # DS:0x545E, written at image 0x0F070
LOCKS = 11                  # the section the lock table begins
LOCK_RECORD = 4
LOCK_COUNT = 71             # every lock the cell events name

# Word 0. The low two bits are the kind, and one state bit stands above them.
# Image 0x02692 walks the state bits to pick what the panel says the lock is,
# from the lines at DS:0x3EE9 up. docs/map.md has the six combinations the
# 451 records take between them.
KIND = 0x0003
UNLOCKED = 0x0080           # NOT LOCKED
PICKABLE = 0x0040           # LOCKED, picked against word 1's difficulty
MAGIC = 0x0020              # MAGICALLY LOCKED
TRAP_ONLY = 0x0008          # not locked, and word 1's trap is armed
STATES = UNLOCKED | PICKABLE | MAGIC | TRAP_ONLY
# The seven named keys, high bit first, as image 0x0270E tests them. A chest
# takes the CHEST KEY of that metal, items 36 to 42, and a lock the DOOR KEY,
# items 43 to 49 (docs/items.md).
KEYS = {0x8000: "brass", 0x4000: "bronze", 0x2000: "copper", 0x1000: "iron",
        0x0800: "steel", 0x0400: "silver", 0x0200: "gold"}
KEYED = 0xFE00
METALS = ["brass", "bronze", "copper", "iron", "steel", "silver", "gold"]
CHEST_KEY, DOOR_KEY = 36, 43

# Word 1 carries two numbers in one, split by image 0x025BB: the quotient is
# the pick difficulty and the remainder is the trap.
LOCK_SPLIT = 100
# A trap at or over this hits the whole party rather than one character, and
# the number the effect table is indexed by is what is left after subtracting
# it (image 0x018EA3).
TRAP_PARTY = 50

# The party's own inventory, a slot at a time.
#
# The game gives the party six inventory slots at roster header 282 and puts no
# order on them: the item search walks all six (docs/saves.md). These are named
# slots over the same set, and each takes the items listed and nothing else.
# The game reaches three of them from the keyboard, `K` `M` `T` at image
# 0x00777; two are the unique items that travel (docs/items.md); and two are
# the things a party spends, which a played save keeps here for the reach
# rather than because the game puts them here.
#
# A slot is drawn with the first item's own 16 x 16 icon, which is that
# record's word 8.
PARTY_ITEMS = {
    "key": [33],            # ATHANEUM KEY
    "ankh": [84],           # ANKH OF PORTALS
    "map": [51],            # PARTY MAP
    "hourglass": [12],      # HOURGLASS
    "ring": [50],           # KEY RING
    "lockpick": [11],       # LOCKPICK
    "torch": [34, 35],      # TORCH, and the same torch lit
}

ITEMS_AT, ITEM_SLOTS = 2, 8
# The three items that carry a count rather than standing one to a place. The
# count is a word of its own, and image 0x028A9 picks which by the item's id.
STACKED = {1: 10, 2: 11, 3: 12}
STACKED_NAME = {1: "gold", 2: "food", 3: "nuore"}


def split(word: int) -> tuple[int, int]:
    """A lock word's pick difficulty and trap number."""
    return divmod(word, LOCK_SPLIT)


def _record(d: S.Directory, section: int, size: int, n: int, words: int) -> tuple[int, ...]:
    at = d.sections[section].offset + n * size
    return struct.unpack_from(f"<{words}H", d.world, at)


def key_of(lock: int) -> str | None:
    """Which metal's key opens this, or None where no key is named."""
    return next((name for bit, name in KEYS.items() if lock & bit), None)


def state_of(lock: int) -> str:
    """Which of the five states the word is in, as the panel reads it."""
    if lock & UNLOCKED:
        return "open"
    if lock & MAGIC:
        return "magic"
    if lock & PICKABLE:
        return "pick"
    if lock & TRAP_ONLY:
        return "trap"
    return "key" if lock & KEYED else "open"


def _lock_fields(lock: int, word: int) -> dict:
    pick, trap = split(word)
    return {
        "lock": lock,
        "kind": lock & KIND,
        "state": state_of(lock),
        "key": key_of(lock),
        "pick": pick,
        "trap": trap,
        "party_trap": trap >= TRAP_PARTY,
    }


def bundle(d: S.Directory, n: int) -> dict:
    """Bundle `n`, 0-based: its lock, its eight places, and its three counts."""
    r = _record(d, BUNDLES, BUNDLE_RECORD, n, 13)
    ids = list(r[ITEMS_AT:ITEMS_AT + ITEM_SLOTS])
    out = {"bundle": n} | _lock_fields(r[0], r[1])
    out["items"] = ids
    out["counts"] = {STACKED_NAME[i]: r[w] for i, w in STACKED.items()}
    return out


def lock(d: S.Directory, n: int) -> dict:
    """Lock `n`, 0-based. Four bytes: a bundle's first two words."""
    r = _record(d, LOCKS, LOCK_RECORD, n, 2)
    return {"number": n} | _lock_fields(r[0], r[1])


def containers(d: S.Directory) -> list[dict]:
    """Every cell a container stands on, with the bundle it holds."""
    return [{"x": e["x"], "y": e["y"]} | bundle(d, e["arg"] - 1)
            for e in events(d) if e["kind"] == "treasure"]


def passages(d: S.Directory) -> list[dict]:
    """Every cell a lock stands on, with the lock."""
    return [{"x": e["x"], "y": e["y"]} | lock(d, e["arg"] - 1)
            for e in events(d) if e["kind"] == "container"]


def chance(level: int, pick: int, thievery: int) -> int:
    """What a d100 is measured against to pick a lock or beat a trap.

    Image `0x17882`: five points per level over the difficulty, plus the
    thievery skill, and never under five. Image `0x18E6E` calls it with the
    pick difficulty in `DS:0x53EE` and the acting character's thievery, at
    record offset 108, in `DS:0x53F0`.
    """
    return max(5, 5 * (level - pick) + thievery)


def _say(rows: list[dict], names: dict, what: str) -> None:
    for r in rows:
        area, level = r["y"] // 24, r["x"] // CELLS
        state = f"{r['key']} key" if r["state"] == "key" else \
                f"pick {r['pick']}" if r["state"] == "pick" else r["state"]
        trap = f" trap {r['trap']}" if r["trap"] else ""
        held = ""
        if what == "container":
            kept = sum(1 for i in r["items"] if i)
            coins = {k: v for k, v in r["counts"].items() if v}
            held = f"  {kept} item{'' if kept == 1 else 's'}" + (f" {coins}" if coins else "")
        print(f'{r["x"]:4d},{r["y"]:4d}  {names.get((area, level), "?"):28s}'
              f'  {state:12s}{trap:9s}{held}')


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game", default="game")
    p.add_argument("--containers", action="store_true")
    p.add_argument("--locks", action="store_true")
    args = p.parse_args()

    d = S.load(args.game)
    chests, shut = containers(d), passages(d)
    names = map_registry(d.world)
    if args.containers:
        _say(chests, names, "container")
    if args.locks:
        _say(shut, names, "lock")
    if args.containers or args.locks:
        return

    def tally(rows: list[dict], what: str) -> None:
        counts = "  ".join(f"{s} {sum(1 for r in rows if r['state'] == s):3d}"
                           for s in ("open", "key", "pick", "magic", "trap"))
        print(f"  {what:11s} {counts}"
              f"  trapped {sum(1 for r in rows if r['trap']):3d}")

    print(f"{len(chests)} containers, {len(shut)} locks")
    tally(chests, "containers")
    tally(shut, "locks")
    places = sum(sum(1 for i in c["items"] if i) for c in chests)
    coins = sum(sum(c["counts"].values()) for c in chests)
    print(f"  {places} filled places, {coins} in the three counts")


if __name__ == "__main__":
    main()
