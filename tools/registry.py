"""The map registry: which of the 140 slots hold a map, and what each is called.

Its own module because both `pack_maps` and `markers` need it, and having
either import the other makes a cycle.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import solve_maps as S


# The map registry: which slots hold a map, and what each one is called.
#
# `WORLD.DAT 0x83400` is 840 bytes, **6 per slot for all 140**, sitting
# immediately after the map region (7 areas x 76,800 ends exactly there). Each
# record is four ASCII characters and a uint16:
#
#     bytes 0..3   the title's suffix, space padded
#     bytes 4..5   high byte a flag, low byte an index into the name table
#
# The low byte is the authority. Slot (2, 1) reads 10 = YENDOR, which is where
# walking through Athaneum's Exit to Yendor door lands; the two levels of
# Castle of Bariag share index 9, and Vishan's Stronghold's two share 23.
#
# The suffix says how the place's name is qualified:
#
#     "0"      no suffix          ATHANEUM
#     "1".."9" LEVEL n            CASTLE OF BARIAG LEVEL 2
#     "01".."010" MAP n           THAINE MAP 10
#
# A zero name index means the slot holds no map, which is how the registry
# settles what the variety heuristic could only guess at: **54 slots hold a
# map**, and areas 0 and 6 hold none at all.
REGISTRY = 0x83400
REGISTRY_RECORD = 6
NAME_TABLE = 0x83748
NAME_RECORD = 20
SLOTS_PER_AREA = 20


def map_names(world) -> dict[str, str]:
    """Name-table index -> place name."""
    out = {}
    for i in range(38):
        at = NAME_TABLE + i * NAME_RECORD
        name = world[at:at + NAME_RECORD].split(b"\x00")[0].decode("latin1")
        out[i] = name.strip().replace("~", "'")
    return out


def map_registry(world) -> dict[tuple[int, int], str]:
    """(area, level) -> the game's own title for that map."""
    names = map_names(world)
    out = {}
    for area in range(S.AREAS):
        for level in range(SLOTS_PER_AREA):
            at = REGISTRY + (area * SLOTS_PER_AREA + level) * REGISTRY_RECORD
            suffix = world[at:at + 4].decode("latin1").strip()
            index = struct.unpack_from("<H", world, at + 4)[0] & 0xFF
            if not index:
                continue
            title = names[index]
            if suffix.startswith("0") and len(suffix) > 1:
                title += f" MAP {int(suffix)}"
            elif suffix != "0":
                title += f" LEVEL {int(suffix)}"
            out[(area, level)] = title
    return out




# Where each clue-book page was photographed. `map_locations.json` records
# which capture shows which map. The registry above contains the slot a page
# occupies,  which is read out of the game rather than fitted by a search.
#
# The file used to carry the slot as well, from the search that produced it.
# That search put two captures on one slot, and readers that trusted the file
# drew one map's grid against another's photograph. Deriving the slot here
# leaves nothing to fall out of step.
INDEX = Path("tests/fixtures/map_locations.json")


def captures(world: bytes) -> list[dict]:
    """The clue book's pages: title, the capture that shows it, and its slot.

    Nothing the panel draws comes from here. The pages are packed from the
    game's own files either way, and this only says which photograph a page
    may be measured against.
    """
    shots = json.loads(INDEX.read_text())
    slot_of = {name: slot for slot, name in map_registry(world).items()}
    out = []
    for entry in shots:
        slot = slot_of.get(entry["title"])
        if slot is None:
            raise KeyError(f"{entry['title']} is not a map the registry names")
        area, level = slot
        out.append({**entry, "area": area, "level": level,
                    "base": area * S.AREA_STRIDE})
    return out
