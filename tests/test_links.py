"""The map network: where each door goes.

What makes this more than a plausible reading of some bytes is that three of
the links were walked in the game long before the table was found, and that
the doors line up with the clue book's own legend: a door on a page whose
legend line names another map lands on the map the line names. That check
covers a hundred of the 139 doors and is not something a wrong table could
pass by accident.
"""
import json
from pathlib import Path

import links as K
import markers
import registry as R
import sections as S

ROOT = Path(__file__).resolve().parent.parent
PAGES = json.loads((ROOT / "data" / "map_pages.json").read_text())


def test_the_destination_table_ends_where_the_gate_table_begins():
    """139 records of eighteen bytes, and the count is not a guess: the table
    runs from DS:0xBA95 to DS:0xC45B, which is the flag-gate table the door
    handler walks."""
    assert (K.DESTINATIONS + K.DESTINATION_COUNT * K.DESTINATION_RECORD
            == K.GATE_TABLE)


def test_every_cell_event_is_one_of_six_kinds(directory):
    events = K.events(directory)
    assert len(events) == 2597
    counts = {}
    for e in events:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    assert counts == {"monster": 1862, "treasure": 380, "person": 139,
                      "door": 139, "container": 71, "script": 6}
    # The arguments of each kind are a dense 1-based run, which is what says
    # the kind bit has been read right: a mis-split would leave gaps.
    for kind in ("door", "person", "monster"):
        args = sorted(e["arg"] for e in events if e["kind"] == kind)
        assert args == list(range(1, len(args) + 1)), kind


def test_every_door_uses_its_own_destination_record(directory):
    """139 doors and 139 records, one each, so nothing in the table is
    spare and no door shares a destination with another."""
    doors = [e for e in K.events(directory) if e["kind"] == "door"]
    assert sorted(e["arg"] for e in doors) == list(range(1, 140))


def test_every_door_lands_on_a_map(directory):
    registry = R.map_registry(directory.world)
    for door in K.doors(directory):
        assert registry.get(K.page_of(door["to_x"], door["to_y"])), door
        assert door["facing"], door


def test_the_walked_links_come_out_of_the_table(directory):
    """Two of the three doors that were walked in the game before any of this
    was decoded. The third is Saxon's ship, which is not a door: its cell is
    one of the six script events, and no destination record carries it."""
    marks = markers.by_page(directory.world, PAGES)
    got = K.by_label(directory, PAGES, marks)
    assert got["ATHANEUM|EXIT TO YENDOR"] == "YENDOR"
    assert got["THAINE MAP 10|PORTAL TO BARIAG"] == "KINGDOM OF BARIAG"
    assert "YENDOR|SAXON'S SHIP TO THAINE" not in got


def test_a_legend_line_that_names_a_map_leads_to_that_map(directory):
    """The independent check. A legend line and the destination table are
    different data written by different hands; where the line names a place,
    the door under it goes there."""
    marks = markers.by_page(directory.world, PAGES)
    titles = {p["title"] for p in PAGES} | set(
        R.map_registry(directory.world).values())
    agree = disagree = 0
    for key, destination in K.by_label(directory, PAGES, marks).items():
        line = key.split("|", 1)[1]
        named = [t for t in titles if t and t in line]
        if not named:
            continue
        # "PORTAL TO SLATOR" names a region, not a map; "SHIP TO HOMELAND
        # MAP 3" names the map with words in front of it. Either way the
        # destination's title has to be the thing the line names.
        if max(named, key=len) in destination or destination in line:
            agree += 1
        else:
            disagree += 1
    assert agree >= 60 and disagree == 0, (agree, disagree)


def test_a_door_lands_on_a_cell_the_party_may_stand_on(directory):
    """The strongest independent check there is: the destination table is in
    the executable and the terrain is in WORLD.DAT, and every door in the one
    puts the party on a cell the other calls walkable."""
    import pack_maps

    blocked = []
    for door in K.doors(directory):
        area, level = K.page_of(door["to_x"], door["to_y"])
        if not pack_maps.walkable(directory.world, area, level,
                                  door["to_y"] % K.BANDS, door["to_x"] % K.CELLS):
            blocked.append(door)
    assert not blocked, blocked


def test_most_doors_have_a_door_back(directory):
    """Most, not all: a few are one-way, the way out of a stronghold, and
    the portals, which land you somewhere with no portal on it."""
    named = K.named(directory, PAGES)
    pairs = {(d["from"], d["to"]) for d in named if d["from"] and d["to"]
             and d["from"] != d["to"]}
    both = [p for p in pairs if (p[1], p[0]) in pairs]
    assert len(both) / len(pairs) > 0.7


def test_a_stat_marker_names_the_npc_standing_on_it(directory):
    """`SLASHING = 160` is a person, and the record says so.

    Every one of the fourteen `STAT = N` legend squares carries a person
    event, and that person's `+0x14` is the stat's offset in the character
    record's maximum block while `+0x16` is N. Fourteen captions written by
    hand agreeing with fourteen pairs of words is also what says the person
    argument indexes the NPC table directly rather than one off it.
    """
    import re
    import struct

    import saves

    NPCS, NPC_RECORD = 0x3D8EB9, 40
    STAT_AT, CEILING_AT = 0x14, 0x16
    names = {}
    for group, first in ((saves.ATTRIBUTES, saves.OFF_ATTRIBUTES),
                         (saves.COMBAT, saves.OFF_COMBAT),
                         (saves.SKILLS, saves.OFF_SKILLS)):
        for k, name in enumerate(group):
            names[saves.MAXIMUM + first + k * 2] = name.upper()

    people = {(e["x"], e["y"]): e["arg"]
              for e in K.events(directory) if e["kind"] == "person"}
    marks = markers.by_page(directory.world, PAGES)
    checked = 0
    for title, rows in marks.items():
        page = next((p for p in PAGES if p["title"] == title), None)
        if page is None:
            continue
        for m in rows:
            if not re.fullmatch(r"[A-Z ]+ = \d+", m["label"]):
                continue
            cell = (page["level"] * K.CELLS + m["cell"],
                    page["area"] * K.BANDS + m["row"])
            npc = next((people[(cell[0] + dx, cell[1] + dy)]
                        for dx, dy in K.NEIGHBORS
                        if (cell[0] + dx, cell[1] + dy) in people), None)
            assert npc is not None, m["label"]
            at = NPCS + npc * NPC_RECORD
            stat, = struct.unpack_from("<H", directory.world, at + STAT_AT)
            ceiling, = struct.unpack_from("<H", directory.world, at + CEILING_AT)
            assert f"{names[stat]} = {ceiling}" == m["label"], (m["label"], npc)
            checked += 1
    assert checked == 14
