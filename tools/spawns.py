"""Where every monster in the game stands, and which monster it is.

A **cell event** places each monster, the `0x0800` kind of the section 28
table `tools/links.py` reads. Its argument is a **spawn id**, and section 30
holds a `uint16` per spawn id naming the enemy record that id stands for. There
are 1,862 of them, numbered 1 to 1,862, and each one is one monster standing on
one cell of the world grid.

The chain, in the code:

    0x10CB4  the cell carries kind 0x0800 -> test the spawn id's flag
    0x127FB  save section 5, bit `id`: set means the monster is gone
    0x1003A  clear -> mark the world cell: `[cell+6] |= 0x400`, `[cell+4] = id`
    0x107B8  the cell comes into view at range >= 0x11 -> find or make a slot
    0x125E6  claim a free slot of the eighty at DS:0x122C, `[slot] = id`
    0x12602  read section 30 record `id`     -> the enemy record's number
    0x1261D  read section 29 record that     -> the monster itself

A spawn id is therefore the monster's identity for the whole game. It names the
enemy record through section 30, and it is its own bit in the save.

`python tools/spawns.py` prints the census by map, `--by-monster` by monster.
"""

from __future__ import annotations

import collections
import struct

import links as K
import sections as S
from registry import map_registry

MONSTER_KIND = "monster"  # links.KINDS' name for the 0x0800 cell event
BANDS, CELLS = K.BANDS, K.CELLS

# Save section 5, one bit per spawn id, most significant bit first within a
# byte. Set means the monster is not on the map. Image 0x127B4 sets it as the
# monster is instantiated and 0x1276B clears it when the monster drifts out of
# the window. Nothing clears it on a death.
GONE_FLAGS = 5


def spawn_table(d: S.Directory) -> list[int]:
    """Spawn id -> enemy record number, for the 1,862 ids the maps use.

    The section is 10,000 bytes and only the head of it is this table; what
    follows the last id is other data, section sizes among them.
    """
    section = d.sections[S.SPAWN_TABLE]
    words = struct.unpack_from(f"<{section.size // 2}H", d.world, section.offset)
    return list(words)


def placements(d: S.Directory) -> list[dict]:
    """Every monster the maps place, in the cell-event table's own order."""
    table = spawn_table(d)
    out = []
    for e in K.events(d):
        if e["kind"] != MONSTER_KIND:
            continue
        out.append({"id": e["arg"], "enemy": table[e["arg"]],
                    "x": e["x"], "y": e["y"],
                    "area": e["y"] // BANDS, "level": e["x"] // CELLS,
                    "cell": e["x"] % CELLS, "band": e["y"] % BANDS})
    return out


def census(d: S.Directory, enemies: list[dict]) -> dict:
    """Per map: how many of each monster stand on it, and what they pay."""
    names = {e["index"]: e["name"] for e in enemies}
    by_index = {e["index"]: e for e in enemies}
    titles = map_registry(d.world)
    pages: dict[str, dict] = {}
    for p in placements(d):
        slot = (p["area"], p["level"])
        title = titles.get(slot) or f"area {p['area']} level {p['level']}"
        page = pages.setdefault(title, {"area": p["area"], "level": p["level"],
                                        "monsters": collections.Counter(),
                                        "experience": 0, "gold": 0, "nuore": 0})
        e = by_index[p["enemy"]]
        page["monsters"][names[p["enemy"]]] += 1
        for reward in ("experience", "gold", "nuore"):
            page[reward] += e[reward]
    for page in pages.values():
        page["monsters"] = dict(page["monsters"].most_common())
        page["total"] = sum(page["monsters"].values())
    return pages


def gone(save) -> list[int]:
    """The spawn ids a `saves.Save` records as no longer on the map."""
    return save.bits_set(GONE_FLAGS)


def main(argv: list[str]) -> int:
    # Imported here rather than at the top: extract imports this module, so a
    # module-level import back into it would be a cycle.
    import extract

    d = S.load()
    enemies = extract.extract_enemies(d)
    by_index = {e["index"]: e for e in enemies}
    names = {e["index"]: e["name"] for e in enemies}
    place = placements(d)

    if "--by-monster" in argv:
        count = collections.Counter(p["enemy"] for p in place)
        print(f"{'monster':<20}{'lvl':>4}{'n':>5}{'xp each':>9}{'xp total':>10}")
        for index, n in sorted(count.items(),
                               key=lambda kv: (by_index[kv[0]]["level"], -kv[1])):
            e = by_index[index]
            print(f"{e['name']:<20}{e['level']:>4}{n:>5}"
                  f"{e['experience']:>9}{n * e['experience']:>10}")
    else:
        for title, page in sorted(census(d, enemies).items(),
                                  key=lambda kv: (kv[1]["area"], kv[1]["level"])):
            print(f"{title} ({page['area']}, {page['level']}): "
                  f"{page['total']} monsters, {page['experience']:,} experience")
            print("   " + ", ".join(f"{n} x{k}"
                                    for n, k in page["monsters"].items()))

    total = collections.Counter()
    for p in place:
        for reward in ("experience", "gold", "nuore"):
            total[reward] += by_index[p["enemy"]][reward]
    print(f"\n{len(place)} monsters, {len(set(p['enemy'] for p in place))} kinds"
          f"\nexperience {total['experience']:,}   gold {total['gold']:,}   "
          f"nuore {total['nuore']:,}")
    listed = {i for i, e in by_index.items() if e["listed"]}
    assert listed == {p["enemy"] for p in place}, \
        "every monster the game lists stands somewhere, and only those do"
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
